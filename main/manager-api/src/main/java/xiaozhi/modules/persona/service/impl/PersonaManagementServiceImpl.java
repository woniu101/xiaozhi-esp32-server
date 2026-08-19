package xiaozhi.modules.persona.service.impl;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import lombok.RequiredArgsConstructor;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.persona.dao.PersonaDao;
import xiaozhi.modules.persona.client.PersonaCompilerClient;
import xiaozhi.modules.persona.metrics.PersonaMetrics;
import xiaozhi.modules.persona.service.PersonaManagementService;

@Service
@RequiredArgsConstructor
public class PersonaManagementServiceImpl implements PersonaManagementService {
    private static final Set<String> VISIBILITIES = Set.of("private", "shared", "public");
    private final PersonaDao personaDao;
    private final PersonaCompilerClient compilerClient;
    private final PersonaMetrics metrics;

    @Override
    public List<Map<String, Object>> list(Long userId) {
        return personaDao.selectPersonas(userId);
    }

    @Override
    public Map<String, Object> get(Long userId, String personaId) {
        Map<String, Object> value = personaDao.selectPersona(userId, personaId);
        if (value == null) {
            throw new RenException("Persona 不存在或无权访问");
        }
        return value;
    }

    @Override
    public List<Map<String, Object>> versions(Long userId, String personaId) {
        get(userId, personaId);
        return personaDao.selectVersions(userId, personaId);
    }

    @Override
    public Map<String, Object> version(Long userId, String personaId, String version) {
        Map<String, Object> value = personaDao.selectVersion(userId, personaId, version);
        if (value == null) {
            throw new RenException("Persona 版本不存在或无权访问");
        }
        Map<String, Object> result = new LinkedHashMap<>(value);
        parseJson(result, "canonicalSpec");
        parseJson(result, "validationReport");
        parseJson(result, "testReport");
        return result;
    }

    @Override
    public Map<String, Object> diff(Long userId, String personaId, String from, String to) {
        Map<String, Object> left = version(userId, personaId, from);
        Map<String, Object> right = version(userId, personaId, to);
        Map<String, Object> leftSpec = castMap(left.get("canonicalSpec"));
        Map<String, Object> rightSpec = castMap(right.get("canonicalSpec"));
        Set<String> keys = new LinkedHashSet<>();
        keys.addAll(leftSpec.keySet());
        keys.addAll(rightSpec.keySet());
        List<Map<String, Object>> changes = new ArrayList<>();
        for (String key : keys) {
            Object before = leftSpec.get(key);
            Object after = rightSpec.get(key);
            if (!Objects.equals(before, after)) {
                Map<String, Object> change = new LinkedHashMap<>();
                change.put("path", key);
                change.put("before", before);
                change.put("after", after);
                changes.add(change);
            }
        }
        return Map.of("from", from, "to", to, "changes", changes);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void publish(Long userId, String personaId, String version, String visibility) {
        String safeVisibility = StringUtils.defaultIfBlank(visibility, "private");
        try {
            requireOwner(userId, personaId);
            if (!VISIBILITIES.contains(safeVisibility)) {
                throw new RenException("Persona 可见性不合法");
            }
            Map<String, Object> target = version(userId, personaId, version);
            if ("archived".equals(target.get("status"))) {
                throw new RenException("归档版本不能发布");
            }
            if (!Boolean.TRUE.equals(castMap(target.get("validationReport")).get("valid"))) {
                throw new RenException("Persona 未通过结构校验，不能发布");
            }
            if (!"passed".equals(target.get("testStatus"))) {
                throw new RenException("Persona 测试尚未通过，不能发布");
            }
            if (personaDao.publishVersion(personaId, version, userId) != 1) {
                throw new RenException("Persona 版本状态已变化，请刷新后重试");
            }
            if (personaDao.publishSource(personaId, version, userId, safeVisibility) != 1) {
                throw new RenException("Persona 发布状态更新失败，请刷新后重试");
            }
            audit(userId, "persona_published", personaId + "@" + version,
                    Map.of("visibility", safeVisibility));
            metrics.increment("companion_persona_publish_total", "kind", safeVisibility, "status", "success");
        } catch (RuntimeException error) {
            metrics.increment("companion_persona_publish_total", "kind", safeVisibility, "status", "failed");
            throw error;
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void rollback(Long userId, String personaId, String version) {
        requireOwner(userId, personaId);
        Map<String, Object> target = version(userId, personaId, version);
        if (!"published".equals(target.get("status")) || personaDao.setPublishedPointer(personaId, version) != 1) {
            throw new RenException("只能回滚到已经发布的 Persona 版本");
        }
        audit(userId, "persona_rolled_back", personaId + "@" + version, Map.of());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void archive(Long userId, String personaId, String version) {
        requireOwner(userId, personaId);
        if (personaDao.archiveVersion(personaId, version) != 1) {
            throw new RenException("当前发布版本不能归档，请先发布或回滚到其他版本");
        }
        audit(userId, "persona_archived", personaId + "@" + version, Map.of());
    }

    @Override
    public Map<String, Object> rerunTest(Long userId, String personaId, String version) {
        long started = System.nanoTime();
        requireOwner(userId, personaId);
        Map<String, Object> target = version(userId, personaId, version);
        if ("archived".equals(target.get("status"))) {
            throw new RenException("归档版本不能重新测试");
        }
        String runId = UUID.randomUUID().toString().replace("-", "");
        Map<String, Object> pending = new LinkedHashMap<>();
        pending.put("id", runId);
        pending.put("personaId", personaId);
        pending.put("version", version);
        pending.put("suiteVersion", "companion-persona-rules/1");
        pending.put("modelConfigId", null);
        pending.put("createdBy", userId);
        personaDao.insertTestRun(pending);
        try {
            Map<String, Object> report = compilerClient.test(Map.of(
                    "canonicalSpec", target.get("canonicalSpec"),
                    "runtimePrompt", String.valueOf(target.get("runtimePrompt"))));
            String status = "passed".equals(report.get("status")) ? "passed" : "failed";
            Object score = report.get("score");
            String json = JsonUtils.toJsonString(report);
            personaDao.updateVersionTest(personaId, version, status, score, json);
            Map<String, Object> scoreValue = new LinkedHashMap<>();
            scoreValue.put("score", score);
            personaDao.completeTestRun(runId, status, JsonUtils.toJsonString(scoreValue), json);
            audit(userId, "persona_test_rerun", personaId + "@" + version,
                    Map.of("runId", runId, "status", status));
            Map<String, Object> result = new LinkedHashMap<>(report);
            result.put("runId", runId);
            metrics.observeMillis("companion_persona_test_duration_ms",
                    (System.nanoTime() - started) / 1_000_000L, "status", status);
            return result;
        } catch (RuntimeException error) {
            personaDao.completeTestRun(runId, "failed", null,
                    JsonUtils.toJsonString(Map.of("error", "Persona Compiler 不可用")));
            metrics.observeMillis("companion_persona_test_duration_ms",
                    (System.nanoTime() - started) / 1_000_000L, "status", "failed");
            throw error;
        }
    }

    @Override
    public List<Map<String, Object>> testRuns(Long userId, String personaId, String version) {
        version(userId, personaId, version);
        List<Map<String, Object>> runs = personaDao.selectTestRuns(userId, personaId, version);
        for (Map<String, Object> run : runs) {
            parseJson(run, "scoreJson");
            parseJson(run, "reportJson");
        }
        return runs;
    }

    @Override
    public byte[] exportFilesystemPackage(Long userId, String personaId, String version) {
        requireOwner(userId, personaId);
        Map<String, Object> target = version(userId, personaId, version);
        String safePersona = personaId.replaceAll("[^A-Za-z0-9._-]", "_");
        String safeVersion = version.replaceAll("[^A-Za-z0-9._-]", "_");
        String root = safePersona + "/versions/" + safeVersion + "/";
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("persona_id", personaId);
        metadata.put("version", version);
        metadata.put("status", target.get("status"));
        metadata.put("artifact_sha256", target.get("artifactHash"));
        metadata.put("compiler_version", target.get("compilerVersion"));
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                ZipOutputStream zip = new ZipOutputStream(bytes, StandardCharsets.UTF_8)) {
            zipEntry(zip, root + "persona.json", JsonUtils.toJsonString(target.get("canonicalSpec")));
            zipEntry(zip, root + "runtime_prompt.txt", String.valueOf(target.get("runtimePrompt")));
            zipEntry(zip, root + "validation.json", JsonUtils.toJsonString(target.get("validationReport")));
            zipEntry(zip, root + "version.json", JsonUtils.toJsonString(metadata));
            if ("published".equals(target.get("status"))) {
                zipEntry(zip, safePersona + "/published.json", JsonUtils.toJsonString(Map.of(
                        "persona_id", personaId,
                        "version", version,
                        "artifact_sha256", String.valueOf(target.get("artifactHash")))));
            }
            zip.finish();
            return bytes.toByteArray();
        } catch (Exception error) {
            throw new RenException("导出 Filesystem Persona 包失败", error);
        }
    }

    private static void zipEntry(ZipOutputStream zip, String name, String value) throws Exception {
        zip.putNextEntry(new ZipEntry(name));
        zip.write(value.getBytes(StandardCharsets.UTF_8));
        zip.closeEntry();
    }

    @Override
    public List<Map<String, Object>> auditTrail(Long userId, String personaId) {
        requireOwner(userId, personaId);
        List<Map<String, Object>> items = personaDao.selectPersonaAudit(userId, personaId);
        for (Map<String, Object> item : items) parseJson(item, "detailsJson");
        return items;
    }

    private Map<String, Object> requireOwner(Long userId, String personaId) {
        Map<String, Object> persona = get(userId, personaId);
        Object owner = persona.get("ownerUserId");
        if (owner == null) {
            throw new RenException("系统 Persona 不允许由普通用户执行此操作");
        }
        long ownerId = owner instanceof Number number ? number.longValue() : Long.parseLong(String.valueOf(owner));
        if (!Objects.equals(userId, ownerId)) {
            throw new RenException("只有 Persona 所有者可以执行该操作");
        }
        return persona;
    }

    private void audit(Long userId, String action, String target, Map<String, Object> details) {
        personaDao.insertAudit(userId, action, "persona_version", target, JsonUtils.toJsonString(details));
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> castMap(Object value) {
        return value instanceof Map<?, ?> ? (Map<String, Object>) value : Map.of();
    }

    private static void parseJson(Map<String, Object> value, String key) {
        Object raw = value.get(key);
        if (raw instanceof String text && StringUtils.isNotBlank(text)) {
            value.put(key, JsonUtils.parseMap(text));
        }
    }
}
