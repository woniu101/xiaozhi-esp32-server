package xiaozhi.modules.persona.service.impl;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.persona.client.PersonaCompilerClient;
import xiaozhi.modules.persona.dao.PersonaDao;
import xiaozhi.modules.persona.metrics.PersonaMetrics;
import xiaozhi.modules.persona.service.PersonaSignatureService;
import xiaozhi.modules.persona.source.GitHubSourceDownloader;

@Service
@RequiredArgsConstructor
@Slf4j
public class PersonaImportWorker {
    private static final List<String> STAGES = List.of("stranger", "familiar", "friend", "ambiguous", "lover", "intimate");

    private final PersonaDao personaDao;
    private final PersonaCompilerClient compilerClient;
    private final GitHubSourceDownloader sourceDownloader;
    private final PlatformTransactionManager transactionManager;
    private final PersonaMetrics metrics;
    private final PersonaSignatureService signatureService;

    @Value("${companion.artifact-dir:uploadfile/personas}")
    private String artifactDirectory;

    @Async
    public void inspect(String jobId) {
        String provider = "unknown";
        try {
            Map<String, Object> job = requireJob(jobId);
            requireActive(jobId);
            provider = string(job.get("sourceType"));
            personaDao.updateImportJob(jobId, "resolving_source", 5, null, null, null, null, null, null, null);
            byte[] artifact;
            String path = string(job.get("artifactPath"));
            String commit = null;
            if ("github".equals(job.get("sourceType"))) {
                personaDao.updateImportJob(jobId, "downloading", 10, null, null, null, null, null, null, null);
                long downloadStarted = System.nanoTime();
                GitHubSourceDownloader.DownloadedSource source = sourceDownloader.download(
                        string(job.get("sourceUrl")), string(job.get("sourceRef")));
                metrics.observeMillis("companion_persona_download_duration_ms", elapsedMillis(downloadStarted),
                        "provider", "github");
                artifact = source.artifact();
                commit = source.commit();
                path = saveDownloadedArtifact(longValue(job.get("ownerUserId")), jobId, artifact).toString();
            } else {
                artifact = Files.readAllBytes(Path.of(path));
            }
            personaDao.updateImportJob(jobId, "inspecting", 25, commit, null, path, null, null, null, null);
            Map<String, Object> inspection = compilerClient.inspect(Map.of(
                    "artifactBase64", Base64.getEncoder().encodeToString(artifact)));
            requireActive(jobId);
            if (!Boolean.TRUE.equals(inspection.get("detected"))) {
                throw new RenException("上传内容不是受支持的 dot-skill Persona");
            }
            if (bool(job.get("forceRevision"))) {
                Map<String, Object> base = personaDao.selectVersion(
                        longValue(job.get("ownerUserId")),
                        string(job.get("expectedPersonaId")),
                        string(job.get("baseVersion")));
                if (base == null) {
                    throw new RenException("重新解析的目标 Persona 版本不存在");
                }
                String inspectedHash = string(inspection.get("artifactHash"));
                if (!inspectedHash.equals(string(base.get("artifactHash")))) {
                    throw new RenException("上传或下载的源码与目标版本不一致，请使用“导入新版”处理源码更新");
                }
            }
            personaDao.updateImportJob(
                    jobId,
                    "compiling",
                    45,
                    commit,
                    string(inspection.get("artifactHash")),
                    path,
                    JsonUtils.toJsonString(inspection),
                    null,
                    null,
                    null);
            metrics.increment("companion_persona_import_total", "provider", provider, "status", "inspected");
            compile(jobId);
        } catch (Exception error) {
            if (!"cancelled".equals(personaDao.selectImportJobStatus(jobId))) {
                fail(jobId, "inspection_failed", error);
                metrics.increment("companion_persona_import_total", "provider", provider, "status", "failed");
            }
        }
    }

    @Async
    public void compile(String jobId) {
        long started = System.nanoTime();
        try {
            Map<String, Object> job = requireJob(jobId);
            byte[] artifact = Files.readAllBytes(Path.of(string(job.get("artifactPath"))));
            Map<String, Object> sourceMetadata = new LinkedHashMap<>();
            Map<String, Object> baseVersion = bool(job.get("forceRevision"))
                    ? personaDao.selectVersion(
                            longValue(job.get("ownerUserId")),
                            string(job.get("expectedPersonaId")),
                            string(job.get("baseVersion")))
                    : Map.of();
            Map<String, Object> persona = bool(job.get("forceRevision"))
                    ? personaDao.selectPersona(
                            longValue(job.get("ownerUserId")),
                            string(job.get("expectedPersonaId")))
                    : Map.of();
            sourceMetadata.put("sourceUrl", firstNonBlank(
                    job.get("sourceUrl"), value(persona, "sourceUrl")));
            sourceMetadata.put("sourceCommit", firstNonBlank(
                    job.get("resolvedCommit"), value(baseVersion, "sourceCommit")));
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("artifactBase64", Base64.getEncoder().encodeToString(artifact));
            payload.put("sourceMetadata", sourceMetadata);
            personaDao.updateImportJob(jobId, "validating", 65, null, null, null, null, null, null, null);
            Map<String, Object> result = compilerClient.compile(payload);
            requireActive(jobId);
            boolean publishable = Boolean.TRUE.equals(result.get("publishable"));
            new TransactionTemplate(transactionManager).executeWithoutResult(status -> {
                Map<String, Object> lockedJob = requireJob(jobId);
                if ("cancelled".equals(lockedJob.get("status"))) {
                    throw new RenException("Persona 导入任务已取消");
                }
                persistDraft(lockedJob, result);
                personaDao.updateImportJob(
                        jobId,
                        publishable ? "ready" : "validation_failed",
                        publishable ? 100 : 90,
                        null,
                        string(result.get("artifactHash")),
                        null,
                        null,
                        JsonUtils.toJsonString(result),
                        publishable ? null : "publish_gate_failed",
                        publishable ? null : "Persona 未通过发布门禁");
            });
            recordValidationFailures(result);
            metrics.observeMillis("companion_persona_compile_duration_ms", elapsedMillis(started),
                    "adapter", "dot-skill", "status", publishable ? "success" : "failed");
        } catch (Exception error) {
            if (!"cancelled".equals(personaDao.selectImportJobStatus(jobId))) {
                fail(jobId, "compile_failed", error);
                metrics.observeMillis("companion_persona_compile_duration_ms", elapsedMillis(started),
                        "adapter", "dot-skill", "status", "failed");
            }
        }
    }

    @SuppressWarnings("unchecked")
    private void recordValidationFailures(Map<String, Object> result) {
        Object rawReport = result.get("validationReport");
        if (!(rawReport instanceof Map<?, ?> report)) return;
        Object rawIssues = report.get("issues");
        if (!(rawIssues instanceof List<?> issues)) return;
        for (Object rawIssue : issues) {
            if (rawIssue instanceof Map<?, ?> issue && "error".equals(String.valueOf(issue.get("severity")))) {
                metrics.increment("companion_persona_validation_fail_total", "code", string(issue.get("code")));
            }
        }
    }

    @SuppressWarnings("unchecked")
    private void persistDraft(Map<String, Object> job, Map<String, Object> result) {
        Long ownerUserId = longValue(job.get("ownerUserId"));
        Map<String, Object> spec = (Map<String, Object>) result.get("canonicalSpec");
        Map<String, Object> source = (Map<String, Object>) spec.get("source");
        Map<String, Object> identity = (Map<String, Object>) spec.get("identity");
        Map<String, Object> policy = (Map<String, Object>) spec.get("relationship_policy");
        String originalPersonaId = string(result.get("personaId"));
        String personaId = resolveOwnedPersonaId(originalPersonaId, ownerUserId, string(result.get("artifactHash")));
        requireExpectedPersonaId(string(job.get("expectedPersonaId")), personaId);
        if (!originalPersonaId.equals(personaId)) {
            spec.put("id", personaId);
            result.put("personaId", personaId);
            result.put("runtimePrompt", string(result.get("runtimePrompt")).replace(
                    "<companion_persona id=\"" + originalPersonaId + "\"",
                    "<companion_persona id=\"" + personaId + "\""));
        }
        boolean forceRevision = bool(job.get("forceRevision"));
        String baseVersion = string(job.get("baseVersion"));
        String version = abbreviate(string(result.get("suggestedVersion")), 64);
        String artifactHash = string(result.get("artifactHash"));
        String runtimePrompt = string(result.get("runtimePrompt"));
        String canonicalSpecJson = JsonUtils.toJsonString(spec);
        String compiledHash = compiledHash(canonicalSpecJson, runtimePrompt);
        String parentVersion = null;
        int revisionNo = 1;
        Map<String, Object> existing;
        boolean compilerRevision = false;

        if (forceRevision) {
            Map<String, Object> base = personaDao.selectVersion(ownerUserId, personaId, baseVersion);
            if (base == null) {
                throw new RenException("重新解析的目标 Persona 版本不存在");
            }
            String baseCompiledHash = string(base.get("compiledHash"));
            if (baseCompiledHash.isBlank()) {
                baseCompiledHash = compiledHash(
                        normalizedCanonicalJson(base.get("canonicalSpec")),
                        string(base.get("runtimePrompt")));
            }
            result.put("recompiled", true);
            result.put("previousVersion", baseVersion);
            result.put("compiledHash", compiledHash);
            parentVersion = firstNonBlank(base.get("parentVersion"), revisionRoot(baseVersion));
            if (compiledHash.equals(baseCompiledHash)) {
                result.put("version", baseVersion);
                result.put("recompileUnchanged", true);
                personaDao.insertAudit(ownerUserId, "persona_recompile_unchanged", "persona_version",
                        personaId + "@" + baseVersion,
                        JsonUtils.toJsonString(Map.of(
                                "jobId", job.get("id"),
                                "compilerVersion", string(result.get("compilerVersion")),
                                "compiledHash", compiledHash)));
                return;
            }
            Map<String, Object> matchingRevision = personaDao.selectRevisionByCompiledHash(
                    personaId, parentVersion, compiledHash);
            if (matchingRevision != null) {
                String matchingVersion = string(matchingRevision.get("version"));
                result.put("version", matchingVersion);
                result.put("suggestedVersion", matchingVersion);
                result.put("recompileUnchanged", true);
                result.put("existingRevision", true);
                personaDao.insertAudit(ownerUserId, "persona_recompile_unchanged", "persona_version",
                        personaId + "@" + matchingVersion,
                        JsonUtils.toJsonString(Map.of(
                                "jobId", job.get("id"),
                                "requestedBaseVersion", baseVersion,
                                "compilerVersion", string(result.get("compilerVersion")),
                                "compiledHash", compiledHash)));
                return;
            }
            revisionNo = personaDao.selectMaxRevisionNo(personaId, parentVersion) + 1;
            version = revisionVersion(parentVersion, revisionNo);
            while (personaDao.selectVersionByHash(personaId, version) != null) {
                revisionNo++;
                version = revisionVersion(parentVersion, revisionNo);
            }
            existing = null;
            result.put("revisionNo", revisionNo);
            result.put("suggestedVersion", version);
        } else {
            existing = personaDao.selectVersionByHash(personaId, version);
            if (existing != null && !artifactHash.equals(string(existing.get("artifactHash")))) {
                version = abbreviate(version + "-" + artifactHash.substring(0, 8), 64);
                result.put("suggestedVersion", version);
                existing = personaDao.selectVersionByHash(personaId, version);
            }
            if (existing != null && artifactHash.equals(string(existing.get("artifactHash")))) {
                String existingVersion = string(existing.get("version"));
                Map<String, Object> fullExisting = personaDao.selectVersion(
                        ownerUserId, personaId, existingVersion);
                if (sameSourceCompilerOutputChanged(artifactHash, compiledHash, fullExisting)) {
                    compilerRevision = true;
                    baseVersion = existingVersion;
                    parentVersion = firstNonBlank(
                            value(fullExisting, "parentVersion"), revisionRoot(existingVersion));
                    result.put("recompiled", true);
                    result.put("compilerRevision", true);
                    result.put("previousVersion", existingVersion);
                    Map<String, Object> matchingRevision = personaDao.selectRevisionByCompiledHash(
                            personaId, parentVersion, compiledHash);
                    if (matchingRevision != null) {
                        version = string(matchingRevision.get("version"));
                        existing = matchingRevision;
                        result.put("existingRevision", true);
                        result.put("recompileUnchanged", true);
                    } else {
                        revisionNo = personaDao.selectMaxRevisionNo(personaId, parentVersion) + 1;
                        version = revisionVersion(parentVersion, revisionNo);
                        while (personaDao.selectVersionByHash(personaId, version) != null) {
                            revisionNo++;
                            version = revisionVersion(parentVersion, revisionNo);
                        }
                        existing = null;
                        result.put("revisionNo", revisionNo);
                    }
                    result.put("suggestedVersion", version);
                }
            }
        }

        Map<String, Object> currentSource = personaDao.selectPersona(ownerUserId, personaId);
        boolean revisionImport = forceRevision || compilerRevision;
        Map<String, Object> baseSourceVersion = revisionImport
                ? personaDao.selectVersion(ownerUserId, personaId, baseVersion)
                : Map.of();
        Map<String, Object> sourceParams = new LinkedHashMap<>();
        sourceParams.put("personaId", personaId);
        sourceParams.put("ownerUserId", ownerUserId);
        sourceParams.put("visibility", "private");
        sourceParams.put("adapterType", string(source.get("adapter")));
        sourceParams.put("displayName", abbreviate(string(result.get("displayName")), 100));
        sourceParams.put("personaKind", personaKind(source));
        sourceParams.put("description", abbreviate(string(identity.get("summary")), 1000));
        sourceParams.put("sourceUrl", firstNonBlank(job.get("sourceUrl"), value(currentSource, "sourceUrl")));
        sourceParams.put("sourceRef", firstNonBlank(job.get("sourceRef"), value(currentSource, "sourceRef")));
        sourceParams.put("sourceCommit", firstNonBlank(
                job.get("resolvedCommit"), value(baseSourceVersion, "sourceCommit"), value(currentSource, "sourceCommit")));
        sourceParams.put("artifactHash", artifactHash);
        sourceParams.put("upstreamSchemaVersion", abbreviate(string(source.get("upstream_schema_version")), 32));
        sourceParams.put("artifactPath", string(job.get("artifactPath")));
        sourceParams.put("realPerson", bool(source.get("is_real_person")));
        sourceParams.put("publicFigure", bool(source.get("is_public_figure")));
        sourceParams.put("relationshipCeiling", relationshipCeiling(policy));
        personaDao.upsertPersonaSource(sourceParams);

        if (existing == null) {
            Map<String, Object> testReport = new LinkedHashMap<>((Map<String, Object>) result.get("testReport"));
            Object judgeReport = result.get("judgeReport");
            if (judgeReport != null) testReport.put("judgeReport", judgeReport);
            if (judgeReport instanceof Map<?, ?> judge && "failed".equals(string(judge.get("status")))) {
                testReport.put("status", "failed");
            }
            Map<String, Object> versionParams = new LinkedHashMap<>();
            versionParams.put("id", newId());
            versionParams.put("personaId", personaId);
            versionParams.put("version", version);
            versionParams.put("parentVersion", parentVersion);
            versionParams.put("revisionNo", revisionNo);
            versionParams.put("artifactHash", artifactHash);
            versionParams.put("sourceCommit", sourceParams.get("sourceCommit"));
            versionParams.put("sourceArtifactPath", string(job.get("artifactPath")));
            versionParams.put("canonicalSpecJson", canonicalSpecJson);
            versionParams.put("runtimePrompt", runtimePrompt);
            versionParams.put("compilerVersion", string(result.get("compilerVersion")));
            versionParams.put("compiledHash", compiledHash);
            versionParams.put("tokenCount", intValue(result.get("tokenCount")));
            versionParams.put("qualityScore", testReport.get("score"));
            versionParams.put("testStatus", string(testReport.get("status")));
            versionParams.put("testReport", JsonUtils.toJsonString(testReport));
            versionParams.put("validationReport", JsonUtils.toJsonString(result.get("validationReport")));
            personaDao.insertPersonaVersion(versionParams);
            if ((compilerRevision || bool(job.get("inheritSignatureAudio"))) && revisionImport) {
                int inherited = signatureService.inheritMatchingAssets(
                        ownerUserId, personaId, baseVersion, version, spec);
                result.put("inheritedSignatureAudioCount", inherited);
            }
        }
        pruneLifecycleVersions(personaId);
        result.put("version", version);
        if (version.equals(string(value(currentSource, "publishedVersion")))) {
            result.put("alreadyCurrent", true);
            result.put("recompileUnchanged", true);
        }
        result.put("compiledHash", compiledHash);
        personaDao.insertAudit(
                ownerUserId,
                revisionImport ? "persona_recompiled" : "persona_imported",
                "persona_version",
                personaId + "@" + version,
                JsonUtils.toJsonString(Map.of(
                        "jobId", job.get("id"),
                        "artifactHash", artifactHash,
                        "compiledHash", compiledHash,
                        "baseVersion", baseVersion)));
    }

    private void pruneLifecycleVersions(String personaId) {
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
                .map(PersonaImportWorker::string)
                .filter(value -> !value.isBlank())
                .distinct()
                .toList();
    }

    private String resolveOwnedPersonaId(String requestedId, Long ownerUserId, String artifactHash) {
        String hash = artifactHash.length() >= 12 ? artifactHash.substring(0, 12) : artifactHash;
        for (int attempt = -1; attempt < 100; attempt++) {
            String suffix = attempt < 0 ? "" : attempt == 0
                    ? ".u" + ownerUserId
                    : ".u" + ownerUserId + "." + hash + (attempt == 1 ? "" : "-" + attempt);
            String candidate = suffix.isEmpty() ? requestedId : abbreviate(requestedId, 160 - suffix.length()) + suffix;
            Map<String, Object> existing = personaDao.selectSourceIdentity(candidate);
            if (existing == null || Objects.equals(ownerUserId, nullableLong(existing.get("ownerUserId")))) {
                return candidate;
            }
        }
        throw new RenException("Persona ID 冲突过多，请修改上游 slug 后重试");
    }

    static void requireExpectedPersonaId(String expectedPersonaId, String resolvedPersonaId) {
        if (StringUtils.isNotBlank(expectedPersonaId) && !expectedPersonaId.equals(resolvedPersonaId)) {
            throw new RenException("新版 Persona ID 与目标人物不一致：期望 "
                    + expectedPersonaId + "，实际 " + resolvedPersonaId);
        }
    }

    private Map<String, Object> requireJob(String jobId) {
        Map<String, Object> job = personaDao.selectImportJobForUpdate(jobId);
        if (job == null) {
            throw new RenException("Persona 导入任务不存在");
        }
        return job;
    }

    private void requireActive(String jobId) {
        if ("cancelled".equals(personaDao.selectImportJobStatus(jobId))) {
            throw new RenException("Persona 导入任务已取消");
        }
    }

    private Path saveDownloadedArtifact(Long ownerUserId, String jobId, byte[] artifact) throws Exception {
        Path root = Path.of(artifactDirectory).toAbsolutePath().normalize();
        Path target = root.resolve(String.valueOf(ownerUserId)).resolve(jobId + ".zip").normalize();
        if (!target.startsWith(root)) {
            throw new RenException("Persona 制品路径不合法");
        }
        Files.createDirectories(target.getParent());
        Files.write(target, artifact);
        return target;
    }

    private void fail(String jobId, String code, Exception error) {
        String message = abbreviate(error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage(), 1000);
        personaDao.updateImportJob(jobId, "failed", 100, null, null, null, null, null, code, message);
    }

    @SuppressWarnings("unchecked")
    private static String relationshipCeiling(Map<String, Object> policy) {
        Object raw = policy == null ? null : policy.get("allowed_stages");
        if (!(raw instanceof List<?> values)) {
            return "friend";
        }
        String ceiling = "familiar";
        for (Object value : values) {
            String stage = string(value);
            if (STAGES.indexOf(stage) > STAGES.indexOf(ceiling)) {
                ceiling = stage;
            }
        }
        return ceiling;
    }

    private static String personaKind(Map<String, Object> source) {
        if (bool(source.get("is_fictional"))) {
            return "fictional";
        }
        if (bool(source.get("is_public_figure"))) {
            return "public_figure";
        }
        return bool(source.get("is_real_person")) ? "real_person" : "unverified";
    }

    private static String string(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private static boolean bool(Object value) {
        return Boolean.TRUE.equals(value) || "true".equalsIgnoreCase(string(value)) || "1".equals(string(value));
    }

    private static long longValue(Object value) {
        return value instanceof Number number ? number.longValue() : Long.parseLong(string(value));
    }

    private static Long nullableLong(Object value) {
        if (value == null || string(value).isBlank()) return null;
        return value instanceof Number number ? number.longValue() : Long.valueOf(string(value));
    }

    private static int intValue(Object value) {
        return value instanceof Number number ? number.intValue() : Integer.parseInt(string(value));
    }

    private static String abbreviate(String value, int max) {
        return StringUtils.abbreviate(StringUtils.defaultString(value), max);
    }

    static String revisionRoot(String version) {
        return StringUtils.defaultString(version).replaceFirst("-r[0-9]+$", "");
    }

    static String revisionVersion(String root, int revisionNo) {
        String suffix = "-r" + revisionNo;
        String value = StringUtils.defaultString(root);
        int rootLimit = Math.max(1, 64 - suffix.length());
        return (value.length() > rootLimit ? value.substring(0, rootLimit) : value) + suffix;
    }

    private static String normalizedCanonicalJson(Object value) {
        if (value instanceof String text) {
            Map<String, Object> parsed = JsonUtils.parseMap(text);
            return parsed == null ? text : JsonUtils.toJsonString(parsed);
        }
        return JsonUtils.toJsonString(value);
    }

    private static String storedCompiledHash(Map<String, Object> version) {
        if (version == null) return "";
        String stored = string(version.get("compiledHash"));
        if (StringUtils.isNotBlank(stored)) return stored;
        return compiledHash(
                normalizedCanonicalJson(version.get("canonicalSpec")),
                string(version.get("runtimePrompt")));
    }

    static boolean sameSourceCompilerOutputChanged(
            String artifactHash, String compiledHash, Map<String, Object> storedVersion) {
        return storedVersion != null
                && artifactHash.equals(string(storedVersion.get("artifactHash")))
                && !compiledHash.equals(storedCompiledHash(storedVersion));
    }

    private static String compiledHash(String canonicalSpecJson, String runtimePrompt) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            digest.update(StringUtils.defaultString(canonicalSpecJson).getBytes(StandardCharsets.UTF_8));
            digest.update((byte) 0);
            byte[] value = digest.digest(StringUtils.defaultString(runtimePrompt).getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder(value.length * 2);
            for (byte item : value) result.append(String.format("%02x", item));
            return result.toString();
        } catch (Exception error) {
            throw new IllegalStateException("Persona 编译结果哈希计算失败", error);
        }
    }

    private static Object value(Map<String, Object> values, String key) {
        return values == null ? null : values.get(key);
    }

    private static String firstNonBlank(Object... values) {
        for (Object value : values) {
            String text = string(value);
            if (StringUtils.isNotBlank(text)) return text;
        }
        return "";
    }

    private static String newId() {
        return UUID.randomUUID().toString().replace("-", "");
    }

    private static long elapsedMillis(long startedNanos) {
        return (System.nanoTime() - startedNanos) / 1_000_000L;
    }
}
