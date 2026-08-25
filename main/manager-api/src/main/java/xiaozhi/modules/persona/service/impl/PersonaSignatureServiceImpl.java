package xiaozhi.modules.persona.service.impl;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import lombok.RequiredArgsConstructor;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.persona.dao.PersonaDao;
import xiaozhi.modules.persona.dto.PersonaRuntimeDTO.SignatureAssetRequest;
import xiaozhi.modules.persona.service.PersonaSignatureService;

@Service
@RequiredArgsConstructor
public class PersonaSignatureServiceImpl implements PersonaSignatureService {
    private static final Pattern SAFE_KEY = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");
    private static final Pattern SAFE_VARIANT = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,31}");
    private static final Set<String> AUDIO_EXTENSIONS = Set.of("wav", "mp3", "ogg");
    private static final int MAX_AUDIO_BYTES = 5 * 1024 * 1024;

    private final PersonaDao personaDao;

    @Override
    public List<Map<String, Object>> list(Long userId, String personaId, String version) {
        Map<String, Object> row = requireVersion(userId, personaId, version, false);
        Map<String, Object> canonical = parseMapValue(row.get("canonicalSpec"));
        return mergeSignatures(personaId, version, canonical, true);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> upsertDefinition(
            Long userId, String personaId, String version, String signatureKey,
            Map<String, Object> request) {
        requireVersion(userId, personaId, version, true);
        validateKey(signatureKey, "招牌表达 ID");
        Map<String, Object> value = request == null ? Map.of() : request;
        String displayText = StringUtils.trimToEmpty(String.valueOf(value.getOrDefault("displayText", "")));
        String semanticRule = StringUtils.trimToEmpty(String.valueOf(value.getOrDefault("semanticRule", "")));
        if (displayText.isEmpty() || displayText.length() > 160) {
            throw new RenException("招牌表达文本不能为空且不能超过 160 字符");
        }
        if (semanticRule.isEmpty() || semanticRule.length() > 2000) {
            throw new RenException("语义触发规则不能为空且不能超过 2000 字符");
        }
        String fallback = "silence".equals(value.get("fallback")) ? "silence" : "tts";
        Map<String, Object> params = new LinkedHashMap<>();
        params.put("id", UUID.randomUUID().toString().replace("-", ""));
        params.put("personaId", personaId);
        params.put("version", version);
        params.put("signatureKey", signatureKey);
        params.put("displayText", displayText);
        params.put("semanticRule", semanticRule);
        params.put("explicitAliasesJson", JsonUtils.toJsonString(safeStringList(value.get("explicitAliases"), 16, 80)));
        params.put("positiveExamplesJson", JsonUtils.toJsonString(safeStringList(value.get("positiveExamples"), 20, 180)));
        params.put("ambiguityPolicy", StringUtils.abbreviate(
                String.valueOf(value.getOrDefault("ambiguityPolicy", "上下文不能唯一确定时不触发")), 300));
        params.put("fallbackMode", fallback);
        params.put("styleMapJson", JsonUtils.toJsonString(safeStyleMap(value.get("styleMap"))));
        params.put("disabled", false);
        params.put("ownerUserId", userId);
        personaDao.upsertSignatureOverride(params);
        personaDao.insertAudit(userId, "persona_signature_updated", "persona_signature",
                personaId + "@" + version + "#" + signatureKey,
                JsonUtils.toJsonString(Map.of("displayText", displayText, "fallback", fallback)));
        return list(userId, personaId, version).stream()
                .filter(item -> signatureKey.equals(item.get("id")))
                .findFirst()
                .orElseThrow(() -> new RenException("招牌表达保存失败"));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void setEnabled(
            Long userId, String personaId, String version, String signatureKey,
            boolean enabled) {
        requireVersion(userId, personaId, version, true);
        validateKey(signatureKey, "招牌表达 ID");
        Map<String, Object> definition = list(userId, personaId, version).stream()
                .filter(item -> signatureKey.equals(item.get("id")))
                .findFirst()
                .orElseThrow(() -> new RenException("招牌表达不存在"));
        if (enabled) {
            personaDao.setSignatureOverrideDisabled(
                    personaId, version, signatureKey, userId, false);
        } else {
            Map<String, Object> params = new LinkedHashMap<>();
            params.put("id", UUID.randomUUID().toString().replace("-", ""));
            params.put("personaId", personaId);
            params.put("version", version);
            params.put("signatureKey", signatureKey);
            params.put("displayText", String.valueOf(definition.getOrDefault("display_text", "")));
            params.put("semanticRule", String.valueOf(definition.getOrDefault("semantic_rule", "")));
            params.put("explicitAliasesJson", JsonUtils.toJsonString(
                    safeStringList(definition.get("explicit_aliases"), 16, 80)));
            params.put("positiveExamplesJson", JsonUtils.toJsonString(
                    safeStringList(definition.get("positive_examples"), 20, 180)));
            params.put("ambiguityPolicy", StringUtils.abbreviate(
                    String.valueOf(definition.getOrDefault(
                            "ambiguity_policy", "上下文不能唯一确定时不触发")), 300));
            params.put("fallbackMode", "silence".equals(definition.get("fallback")) ? "silence" : "tts");
            params.put("styleMapJson", JsonUtils.toJsonString(safeStyleMap(definition.get("style_map"))));
            params.put("disabled", true);
            params.put("ownerUserId", userId);
            personaDao.upsertSignatureOverride(params);
        }
        personaDao.insertAudit(userId,
                enabled ? "persona_signature_enabled" : "persona_signature_disabled",
                "persona_signature", personaId + "@" + version + "#" + signatureKey,
                JsonUtils.toJsonString(Map.of("enabled", enabled)));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> uploadAsset(
            Long userId, String personaId, String version, String signatureKey,
            String variant, MultipartFile file) {
        requireVersion(userId, personaId, version, true);
        validateKey(signatureKey, "招牌表达 ID");
        if (!SAFE_VARIANT.matcher(StringUtils.defaultString(variant)).matches()) {
            throw new RenException("语气变体 ID 不合法");
        }
        boolean exists = list(userId, personaId, version).stream()
                .anyMatch(item -> signatureKey.equals(item.get("id"))
                        && !Boolean.FALSE.equals(item.get("enabled")));
        if (!exists) {
            throw new RenException("请先保存招牌表达定义，再上传语音");
        }
        if (file == null || file.isEmpty() || file.getSize() > MAX_AUDIO_BYTES) {
            throw new RenException("招牌语音不能为空且不能超过 5MB");
        }
        String filename = StringUtils.defaultString(file.getOriginalFilename());
        String extension = filename.contains(".")
                ? filename.substring(filename.lastIndexOf('.') + 1).toLowerCase()
                : "";
        if (!AUDIO_EXTENSIONS.contains(extension)) {
            throw new RenException("招牌语音只支持 WAV、MP3 或 OGG");
        }
        String defaultContentType = switch (extension) {
            case "wav" -> "audio/wav";
            case "ogg" -> "audio/ogg";
            default -> "audio/mpeg";
        };
        String contentType = StringUtils.defaultIfBlank(file.getContentType(), defaultContentType);
        if (!contentType.startsWith("audio/")) {
            throw new RenException("上传内容不是音频文件");
        }
        try {
            byte[] audio = file.getBytes();
            String assetId = UUID.randomUUID().toString().replace("-", "");
            Map<String, Object> params = new LinkedHashMap<>();
            params.put("id", assetId);
            params.put("personaId", personaId);
            params.put("version", version);
            params.put("signatureKey", signatureKey);
            params.put("variant", variant);
            params.put("contentType", contentType);
            params.put("originalFilename", StringUtils.abbreviate(filename, 255));
            params.put("audioData", audio);
            params.put("byteSize", audio.length);
            params.put("sha256", sha256(audio));
            params.put("ownerUserId", userId);
            personaDao.upsertSignatureAsset(params);
            personaDao.insertAudit(userId, "persona_signature_asset_upserted", "persona_signature_asset",
                    personaId + "@" + version + "#" + signatureKey + ":" + variant,
                    JsonUtils.toJsonString(Map.of(
                            "assetId", assetId,
                            "variant", variant,
                            "sha256", params.get("sha256"),
                            "byteSize", audio.length)));
            return list(userId, personaId, version).stream()
                    .filter(item -> signatureKey.equals(item.get("id")))
                    .findFirst()
                    .orElseThrow(() -> new RenException("招牌语音保存失败"));
        } catch (RenException error) {
            throw error;
        } catch (Exception error) {
            throw new RenException("招牌语音读取失败", error);
        }
    }

    @Override
    public Map<String, Object> playback(Long userId, String assetId) {
        Map<String, Object> asset = personaDao.selectSignatureAsset(assetId);
        if (asset == null) {
            throw new RenException("招牌语音不存在");
        }
        requirePersonaAccess(userId, String.valueOf(asset.get("personaId")), false);
        return asset;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteAsset(Long userId, String assetId) {
        Map<String, Object> asset = personaDao.selectSignatureAsset(assetId);
        if (asset == null) {
            throw new RenException("招牌语音不存在");
        }
        requirePersonaAccess(userId, String.valueOf(asset.get("personaId")), true);
        if (personaDao.deleteSignatureAsset(assetId, userId) != 1) {
            throw new RenException("招牌语音删除失败，请刷新后重试");
        }
        personaDao.insertAudit(userId, "persona_signature_asset_deleted", "persona_signature_asset",
                assetId, JsonUtils.toJsonString(Map.of(
                        "personaId", asset.get("personaId"),
                        "version", asset.get("version"),
                        "signatureKey", asset.get("signatureKey"),
                        "variant", asset.get("variant"))));
    }

    @Override
    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> mergeRuntimeSignatures(
            String personaId, String version, Map<String, Object> canonicalSpec) {
        return mergeSignatures(personaId, version, canonicalSpec, false);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> mergeSignatures(
            String personaId, String version, Map<String, Object> canonicalSpec,
            boolean includeDisabled) {
        Map<String, Map<String, Object>> merged = new LinkedHashMap<>();
        Object raw = canonicalSpec == null ? null : canonicalSpec.get("signature_utterances");
        if (raw instanceof List<?> items) {
            for (Object item : items) {
                if (!(item instanceof Map<?, ?> map)) continue;
                Map<String, Object> copy = new LinkedHashMap<>((Map<String, Object>) map);
                String key = String.valueOf(copy.getOrDefault("id", ""));
                if (!key.isBlank()) {
                    copy.put("origin", "skill");
                    copy.put("enabled", true);
                    merged.put(key, copy);
                }
            }
        }
        for (Map<String, Object> row : personaDao.selectSignatureOverrides(personaId, version)) {
            String key = String.valueOf(row.get("signatureKey"));
            boolean disabled = Boolean.TRUE.equals(row.get("disabled"))
                    || "1".equals(String.valueOf(row.get("disabled")));
            if (disabled && !includeDisabled) {
                merged.remove(key);
                continue;
            }
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", key);
            item.put("display_text", row.get("displayText"));
            item.put("semantic_rule", row.get("semanticRule"));
            item.put("explicit_aliases", parseListValue(row.get("explicitAliasesJson")));
            item.put("positive_examples", parseListValue(row.get("positiveExamplesJson")));
            item.put("ambiguity_policy", row.get("ambiguityPolicy"));
            item.put("fallback", row.get("fallbackMode"));
            item.put("style_map", parseMapValue(row.get("styleMapJson")));
            item.put("assets", new LinkedHashMap<>());
            item.put("origin", merged.containsKey(key) ? "override" : "custom");
            item.put("enabled", !disabled);
            merged.put(key, item);
        }
        for (Map<String, Object> asset : personaDao.selectSignatureAssets(personaId, version)) {
            Map<String, Object> item = merged.get(String.valueOf(asset.get("signatureKey")));
            if (item == null) continue;
            Map<String, Object> assets = item.get("assets") instanceof Map<?, ?> map
                    ? new LinkedHashMap<>((Map<String, Object>) map)
                    : new LinkedHashMap<>();
            String variant = String.valueOf(asset.get("variant"));
            assets.put(variant, "asset://persona-signature/" + asset.get("assetId"));
            item.put("assets", assets);
            List<Map<String, Object>> metadata = item.get("asset_metadata") instanceof List<?> list
                    ? new ArrayList<>((List<Map<String, Object>>) list)
                    : new ArrayList<>();
            metadata.add(new LinkedHashMap<>(asset));
            item.put("asset_metadata", metadata);
        }
        return new ArrayList<>(merged.values());
    }

    @Override
    public String runtimeArtifactHash(String artifactHash, String personaId, String version) {
        List<Map<String, Object>> overrides = personaDao.selectSignatureOverrides(personaId, version);
        List<Map<String, Object>> assets = personaDao.selectSignatureAssets(personaId, version);
        if (overrides.isEmpty() && assets.isEmpty()) return artifactHash;
        String material = artifactHash + "\n"
                + JsonUtils.toJsonString(runtimeOverrideHashMaterial(overrides)) + "\n"
                + JsonUtils.toJsonString(runtimeAssetHashMaterial(assets));
        return sha256(material.getBytes(StandardCharsets.UTF_8));
    }

    private List<Map<String, Object>> runtimeOverrideHashMaterial(List<Map<String, Object>> overrides) {
        return overrides.stream().map(override -> {
            Map<String, Object> material = new LinkedHashMap<>();
            material.put("signatureKey", override.get("signatureKey"));
            material.put("displayText", override.get("displayText"));
            material.put("semanticRule", override.get("semanticRule"));
            material.put("explicitAliasesJson", override.get("explicitAliasesJson"));
            material.put("positiveExamplesJson", override.get("positiveExamplesJson"));
            material.put("ambiguityPolicy", override.get("ambiguityPolicy"));
            material.put("fallbackMode", override.get("fallbackMode"));
            material.put("styleMapJson", override.get("styleMapJson"));
            material.put("disabled", override.get("disabled"));
            return material;
        }).toList();
    }

    private List<Map<String, Object>> runtimeAssetHashMaterial(List<Map<String, Object>> assets) {
        return assets.stream().map(asset -> {
            Map<String, Object> material = new LinkedHashMap<>();
            material.put("assetId", asset.get("assetId"));
            material.put("signatureKey", asset.get("signatureKey"));
            material.put("variant", asset.get("variant"));
            material.put("contentType", asset.get("contentType"));
            material.put("sha256", asset.get("sha256"));
            return material;
        }).toList();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    @SuppressWarnings("unchecked")
    public int inheritMatchingAssets(
            Long userId, String personaId, String fromVersion, String toVersion,
            Map<String, Object> newCanonicalSpec) {
        requireVersion(userId, personaId, fromVersion, true);

        Map<String, String> newDisplayTexts = new LinkedHashMap<>();
        Object rawDefinitions = newCanonicalSpec == null ? null : newCanonicalSpec.get("signature_utterances");
        if (rawDefinitions instanceof List<?> definitions) {
            for (Object definition : definitions) {
                if (!(definition instanceof Map<?, ?> raw)) continue;
                Map<String, Object> item = (Map<String, Object>) raw;
                String key = StringUtils.trimToEmpty(String.valueOf(item.getOrDefault("id", "")));
                String displayText = StringUtils.trimToEmpty(
                        String.valueOf(item.getOrDefault("display_text", "")));
                if (!key.isEmpty() && !displayText.isEmpty()) newDisplayTexts.put(key, displayText);
            }
        }
        if (newDisplayTexts.isEmpty()) return 0;

        Map<String, String> compatibleDefinitions = new LinkedHashMap<>();
        for (Map<String, Object> oldDefinition : list(userId, personaId, fromVersion)) {
            if (Boolean.FALSE.equals(oldDefinition.get("enabled"))) continue;
            String key = StringUtils.trimToEmpty(String.valueOf(oldDefinition.getOrDefault("id", "")));
            String oldText = StringUtils.trimToEmpty(
                    String.valueOf(oldDefinition.getOrDefault("display_text", "")));
            if (oldText.equals(newDisplayTexts.get(key))) compatibleDefinitions.put(key, oldText);
        }

        int inherited = 0;
        for (Map<String, Object> metadata : personaDao.selectSignatureAssets(personaId, fromVersion)) {
            String signatureKey = String.valueOf(metadata.get("signatureKey"));
            if (!compatibleDefinitions.containsKey(signatureKey)) continue;
            Map<String, Object> sourceAsset = personaDao.selectSignatureAsset(String.valueOf(metadata.get("assetId")));
            if (sourceAsset == null || !(sourceAsset.get("audioData") instanceof byte[] audioData)) continue;
            Map<String, Object> params = new LinkedHashMap<>();
            params.put("id", UUID.randomUUID().toString().replace("-", ""));
            params.put("personaId", personaId);
            params.put("version", toVersion);
            params.put("signatureKey", signatureKey);
            params.put("variant", sourceAsset.get("variant"));
            params.put("contentType", sourceAsset.get("contentType"));
            params.put("originalFilename", sourceAsset.get("originalFilename"));
            params.put("audioData", audioData);
            params.put("byteSize", audioData.length);
            params.put("sha256", sourceAsset.get("sha256"));
            params.put("ownerUserId", userId);
            personaDao.upsertSignatureAsset(params);
            inherited++;
        }
        if (inherited > 0) {
            personaDao.insertAudit(userId, "persona_signature_assets_inherited", "persona_version",
                    personaId + "@" + toVersion,
                    JsonUtils.toJsonString(Map.of(
                            "fromVersion", fromVersion,
                            "toVersion", toVersion,
                            "assetCount", inherited,
                            "rule", "same-signature-id-and-display-text")));
        }
        return inherited;
    }

    @Override
    public Map<String, Object> resolveRuntimeAsset(SignatureAssetRequest request) {
        Map<String, Object> runtime = personaDao.selectRuntimeVersion(
                request.getAgentId(), request.getPersonaId(), request.getVersion());
        if (runtime == null) {
            throw new RenException("Persona 未绑定或版本未发布");
        }
        Map<String, Object> asset = personaDao.selectSignatureAsset(request.getAssetId());
        if (asset == null
                || !Objects.equals(String.valueOf(asset.get("personaId")), request.getPersonaId())
                || !Objects.equals(String.valueOf(asset.get("version")), String.valueOf(runtime.get("version")))) {
            throw new RenException("招牌语音不存在或不属于当前人物版本");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("assetId", asset.get("assetId"));
        result.put("sha256", asset.get("sha256"));
        result.put("contentType", asset.get("contentType"));
        result.put("originalFilename", asset.get("originalFilename"));
        result.put("audioBase64", Base64.getEncoder().encodeToString((byte[]) asset.get("audioData")));
        return result;
    }

    private Map<String, Object> requireVersion(Long userId, String personaId, String version, boolean owner) {
        requirePersonaAccess(userId, personaId, owner);
        Map<String, Object> row = personaDao.selectVersion(userId, personaId, version);
        if (row == null) throw new RenException("Persona 版本不存在或无权访问");
        return row;
    }

    private Map<String, Object> requirePersonaAccess(Long userId, String personaId, boolean ownerRequired) {
        Map<String, Object> persona = personaDao.selectPersona(userId, personaId);
        if (persona == null) throw new RenException("Persona 不存在或无权访问");
        if (ownerRequired) {
            Object owner = persona.get("ownerUserId");
            long ownerId = owner instanceof Number number ? number.longValue() : Long.parseLong(String.valueOf(owner));
            if (!Objects.equals(userId, ownerId)) throw new RenException("只有 Persona 所有者可以执行该操作");
        }
        return persona;
    }

    private static void validateKey(String value, String label) {
        if (!SAFE_KEY.matcher(StringUtils.defaultString(value)).matches()) {
            throw new RenException(label + " 不合法");
        }
    }

    private static List<String> safeStringList(Object value, int maxItems, int maxChars) {
        List<String> result = new ArrayList<>();
        if (!(value instanceof List<?> values)) return result;
        for (Object item : values) {
            String text = StringUtils.abbreviate(StringUtils.trimToEmpty(String.valueOf(item)), maxChars);
            if (!text.isEmpty() && !result.contains(text)) result.add(text);
            if (result.size() >= maxItems) break;
        }
        return result;
    }

    private static Map<String, String> safeStyleMap(Object value) {
        Map<String, String> result = new LinkedHashMap<>();
        if (!(value instanceof Map<?, ?> map)) return result;
        for (Map.Entry<?, ?> entry : map.entrySet()) {
            String key = StringUtils.abbreviate(String.valueOf(entry.getKey()), 32);
            String variant = StringUtils.abbreviate(String.valueOf(entry.getValue()), 32);
            if (SAFE_VARIANT.matcher(key).matches() && SAFE_VARIANT.matcher(variant).matches()) {
                result.put(key, variant);
            }
        }
        return result;
    }

    private static Map<String, Object> parseMapValue(Object value) {
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> result = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : map.entrySet()) result.put(String.valueOf(entry.getKey()), entry.getValue());
            return result;
        }
        if (value instanceof String text && StringUtils.isNotBlank(text)) return JsonUtils.parseMap(text);
        return new LinkedHashMap<>();
    }

    private static List<Object> parseListValue(Object value) {
        if (value instanceof List<?> list) return new ArrayList<>(list);
        if (value instanceof String text && StringUtils.isNotBlank(text)) return JsonUtils.parseArray(text, Object.class);
        return new ArrayList<>();
    }

    private static String sha256(byte[] value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
        } catch (Exception error) {
            throw new IllegalStateException("SHA-256 不可用", error);
        }
    }
}
