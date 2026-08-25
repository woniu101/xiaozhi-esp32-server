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
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.persona.dao.PersonaDao;
import xiaozhi.modules.persona.client.PersonaCompilerClient;
import xiaozhi.modules.persona.metrics.PersonaMetrics;
import xiaozhi.modules.persona.service.PersonaManagementService;

@Service
@RequiredArgsConstructor
@Slf4j
public class PersonaManagementServiceImpl implements PersonaManagementService {
    private final PersonaDao personaDao;
    private final PersonaCompilerClient compilerClient;
    private final PersonaMetrics metrics;

    @Value("${companion.artifact-dir:uploadfile/personas}")
    private String artifactDirectory;

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
        return new LinkedHashMap<>(value);
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
    public Map<String, Object> usage(Long userId, String personaId) {
        requireOwner(userId, personaId);
        int bindingCount = personaDao.countPersonaBindings(personaId);
        List<Map<String, Object>> ownBindings = personaDao.selectOwnedPersonaBindings(personaId, userId);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("bindingCount", bindingCount);
        result.put("ownBindings", ownBindings);
        result.put("externalBindingCount", Math.max(0, bindingCount - ownBindings.size()));
        result.put("deletable", true);
        result.put("willUnbind", bindingCount);
        return result;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void delete(Long userId, String personaId, String confirmation) {
        String expected = personaId;
        if (!expected.equals(StringUtils.trimToEmpty(confirmation))) {
            throw new RenException("删除确认文本不匹配");
        }
        requireOwner(userId, personaId);
        List<String> artifactPaths = personaDao.selectPersonaArtifactPaths(personaId, userId);

        personaDao.clearPersonaBindings(personaId);
        personaDao.deletePersonaMemories(personaId);
        personaDao.deletePersonaEvents(personaId);
        personaDao.deletePersonaTurns(personaId);
        personaDao.deletePersonaStates(personaId);
        personaDao.deletePersonaImportJobs(personaId, userId);
        personaDao.deletePersonaAudit(personaId, userId);
        if (personaDao.hardDeletePersonaSource(personaId, userId) != 1) {
            throw new RenException("人物状态已变化，请刷新后重试");
        }
        afterCommit(() -> {
            cleanupArtifactFiles(artifactPaths);
            try {
                compilerClient.evictPersonaCache(personaId);
            } catch (RuntimeException error) {
                log.warn("Persona {} 已清除，但运行时缓存通知失败，新会话将在缓存过期后生效", personaId);
            }
        });
        metrics.increment("companion_persona_delete_total", "status", "success");
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void applyUpdate(Long userId, String personaId, String version) {
        try {
            Map<String, Object> persona = requireOwner(userId, personaId);
            if (version.equals(text(persona.get("publishedVersion")))) {
                throw new RenException("该版本已经是当前使用版本");
            }
            Map<String, Object> target = version(userId, personaId, version);
            if (!"draft".equals(target.get("status"))) {
                throw new RenException("只能应用待更新版本");
            }
            if (!Boolean.TRUE.equals(castMap(target.get("validationReport")).get("valid"))) {
                throw new RenException("人物更新未通过结构校验，不能应用");
            }
            if (!"passed".equals(target.get("testStatus"))) {
                throw new RenException("人物更新测试尚未通过，不能应用");
            }
            if (personaDao.publishVersion(personaId, version, userId) != 1) {
                throw new RenException("人物更新状态已变化，请刷新后重试");
            }
            if (personaDao.applySourceVersion(personaId, version, userId) != 1) {
                throw new RenException("人物更新应用失败，请刷新后重试");
            }
            personaDao.clearPinnedPersonaVersions(personaId);
            pruneVersions(personaId);
            audit(userId, "persona_update_applied", personaId + "@" + version, Map.of());
            afterCommit(() -> evictRuntimeCache(personaId));
            metrics.increment("companion_persona_apply_total", "status", "success");
        } catch (RuntimeException error) {
            metrics.increment("companion_persona_apply_total", "status", "failed");
            throw error;
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void restorePrevious(Long userId, String personaId) {
        Map<String, Object> persona = requireOwner(userId, personaId);
        String current = text(persona.get("publishedVersion"));
        String previous = text(persona.get("previousVersion"));
        if (current.isBlank() || previous.isBlank()
                || personaDao.restorePreviousVersion(personaId, userId, current, previous) != 1) {
            throw new RenException("没有可恢复的上一版，或人物状态已经变化");
        }
        personaDao.clearPinnedPersonaVersions(personaId);
        audit(userId, "persona_previous_restored", personaId + "@" + previous,
                Map.of("replacedVersion", current));
        afterCommit(() -> evictRuntimeCache(personaId));
    }

    @Override
    public Map<String, Object> rerunTest(
            Long userId, String personaId, String version,
            List<Map<String, Object>> conversationSamples) {
        long started = System.nanoTime();
        requireOwner(userId, personaId);
        Map<String, Object> target = version(userId, personaId, version);
        List<Map<String, Object>> samples = conversationSamples == null
                ? List.of()
                : conversationSamples.subList(0, Math.min(500, conversationSamples.size()));
        String runId = UUID.randomUUID().toString().replace("-", "");
        Map<String, Object> pending = new LinkedHashMap<>();
        pending.put("id", runId);
        pending.put("personaId", personaId);
        pending.put("version", version);
        pending.put("suiteVersion", samples.isEmpty()
                ? "companion-persona-rules/1"
                : "companion-persona-rules/1+conversation-quality/1");
        pending.put("modelConfigId", null);
        pending.put("createdBy", userId);
        personaDao.insertTestRun(pending);
        try {
            Map<String, Object> compilerPayload = new LinkedHashMap<>();
            compilerPayload.put("canonicalSpec", target.get("canonicalSpec"));
            compilerPayload.put("runtimePrompt", String.valueOf(target.get("runtimePrompt")));
            compilerPayload.put("conversationSamples", samples);
            Map<String, Object> report = compilerClient.test(compilerPayload);
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

    private void cleanupArtifactFiles(List<String> artifactPaths) {
        Path root = Path.of(StringUtils.defaultIfBlank(artifactDirectory, "uploadfile/personas"))
                .toAbsolutePath().normalize();
        for (String value : artifactPaths == null ? List.<String>of() : artifactPaths) {
            try {
                Path candidate = Path.of(value).toAbsolutePath().normalize();
                if (candidate.startsWith(root) && Files.isRegularFile(candidate)) {
                    Files.deleteIfExists(candidate);
                }
            } catch (Exception error) {
                log.warn("Persona 清除后无法删除受控源码快照 {}", value);
            }
        }
    }

    private void pruneVersions(String personaId) {
        List<String> retainedVersions = retainedLifecycleVersions(personaId);
        if (retainedVersions.isEmpty()) {
            log.warn("跳过 Persona {} 生命周期清理：未查询到任何应保留版本", personaId);
            return;
        }
        personaDao.deleteSignatureAssetsOutsideLifecycle(personaId, retainedVersions);
        personaDao.deleteSignatureOverridesOutsideLifecycle(personaId, retainedVersions);
        personaDao.deleteTestRunsOutsideLifecycle(personaId, retainedVersions);
        personaDao.deleteVersionsOutsideLifecycle(personaId, retainedVersions);
    }

    private List<String> retainedLifecycleVersions(String personaId) {
        Map<String, Object> lifecycle = personaDao.selectLifecycleVersions(personaId);
        if (lifecycle == null) return List.of();
        return List.of("currentVersion", "previousVersion", "draftVersion").stream()
                .map(lifecycle::get)
                .map(PersonaManagementServiceImpl::text)
                .filter(value -> !value.isBlank())
                .distinct()
                .toList();
    }

    private void evictRuntimeCache(String personaId) {
        try {
            compilerClient.evictPersonaCache(personaId);
        } catch (RuntimeException error) {
            log.warn("Persona {} 当前版本已切换，但运行时缓存通知失败，新会话将在缓存过期后生效", personaId);
        }
    }

    private static void afterCommit(Runnable action) {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            action.run();
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                action.run();
            }
        });
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

    private static String text(Object value) {
        return value == null ? "" : StringUtils.trimToEmpty(String.valueOf(value));
    }
}
