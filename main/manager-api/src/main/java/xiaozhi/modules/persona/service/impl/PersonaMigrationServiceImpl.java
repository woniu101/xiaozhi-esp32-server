package xiaozhi.modules.persona.service.impl;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import lombok.RequiredArgsConstructor;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.persona.client.PersonaCompilerClient;
import xiaozhi.modules.persona.dao.PersonaDao;
import xiaozhi.modules.persona.dto.PersonaManagementDTO.FilesystemMigrationRequest;
import xiaozhi.modules.persona.service.PersonaManagementService;
import xiaozhi.modules.persona.service.PersonaMigrationService;

@Service
@RequiredArgsConstructor
public class PersonaMigrationServiceImpl implements PersonaMigrationService {
    private static final List<String> STAGES = List.of("stranger", "familiar", "friend", "ambiguous", "lover", "intimate");

    private final PersonaDao personaDao;
    private final PersonaCompilerClient compilerClient;
    private final PersonaManagementService managementService;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Map<String, Object> migrate(Long userId, FilesystemMigrationRequest request) {
        if (!request.getArtifactHash().matches("^[a-fA-F0-9]{64}$")) {
            throw new RenException("迁移制品 Hash 不合法");
        }
        if (!request.getPersonaId().equals(String.valueOf(request.getCanonicalSpec().get("id")))) {
            throw new RenException("迁移 Persona ID 与标准规格不一致");
        }
        Map<String, Object> sourceIdentity = personaDao.selectSourceIdentity(request.getPersonaId());
        Long existingOwner = sourceIdentity == null ? null : nullableLong(sourceIdentity.get("ownerUserId"));
        if (sourceIdentity != null && !Objects.equals(existingOwner, userId)) {
            throw new RenException("相同 Persona ID 已属于其他用户，请先重命名本地人物");
        }
        Map<String, Object> existing = personaDao.selectVersionByHash(request.getPersonaId(), request.getVersion());
        if (existing != null) {
            if (!request.getArtifactHash().equals(String.valueOf(existing.get("artifactHash")))) {
                throw new RenException("目标版本已存在但 Hash 不同");
            }
            return Map.of("personaId", request.getPersonaId(), "version", request.getVersion(), "status", "unchanged");
        }

        Map<String, Object> spec = request.getCanonicalSpec();
        Map<String, Object> source = map(spec.get("source"));
        Map<String, Object> identity = map(spec.get("identity"));
        Map<String, Object> policy = map(spec.get("relationship_policy"));
        Map<String, Object> sourceParams = new LinkedHashMap<>();
        sourceParams.put("personaId", request.getPersonaId());
        sourceParams.put("ownerUserId", userId);
        sourceParams.put("visibility", "private");
        sourceParams.put("adapterType", string(source.get("adapter"), "filesystem-migration"));
        sourceParams.put("displayName", abbreviate(string(spec.get("display_name"), request.getPersonaId()), 100));
        sourceParams.put("personaKind", personaKind(source));
        sourceParams.put("description", abbreviate(string(identity.get("summary"), ""), 1000));
        sourceParams.put("sourceUrl", string(source.get("source_url"), ""));
        sourceParams.put("sourceRef", "filesystem");
        sourceParams.put("sourceCommit", string(source.get("source_commit"), ""));
        sourceParams.put("artifactHash", request.getArtifactHash());
        sourceParams.put("upstreamSchemaVersion", abbreviate(string(source.get("upstream_schema_version"), ""), 32));
        sourceParams.put("artifactPath", null);
        sourceParams.put("realPerson", bool(source.get("is_real_person")));
        sourceParams.put("publicFigure", bool(source.get("is_public_figure")));
        sourceParams.put("relationshipCeiling", ceiling(policy));
        personaDao.upsertPersonaSource(sourceParams);

        Map<String, Object> testReport = compilerClient.test(Map.of(
                "canonicalSpec", spec, "runtimePrompt", request.getRuntimePrompt()));
        Map<String, Object> validationReport = map(testReport.get("validationReport"));
        boolean valid = Boolean.TRUE.equals(validationReport.get("valid"));
        String normalizedPrompt = string(testReport.get("normalizedRuntimePrompt"), request.getRuntimePrompt());
        String testStatus = "passed".equals(testReport.get("status")) ? "passed" : "failed";
        Map<String, Object> versionParams = new LinkedHashMap<>();
        versionParams.put("id", UUID.randomUUID().toString().replace("-", ""));
        versionParams.put("personaId", request.getPersonaId());
        versionParams.put("version", request.getVersion());
        versionParams.put("artifactHash", request.getArtifactHash());
        versionParams.put("sourceCommit", string(source.get("source_commit"), ""));
        versionParams.put("canonicalSpecJson", JsonUtils.toJsonString(spec));
        versionParams.put("runtimePrompt", normalizedPrompt);
        versionParams.put("compilerVersion", "filesystem-migration/1");
        versionParams.put("tokenCount", Math.max(1, request.getRuntimePrompt().length() / 4));
        versionParams.put("qualityScore", testReport.get("score"));
        versionParams.put("testStatus", testStatus);
        versionParams.put("testReport", JsonUtils.toJsonString(testReport));
        versionParams.put("validationReport", JsonUtils.toJsonString(validationReport));
        personaDao.insertPersonaVersion(versionParams);
        personaDao.insertAudit(userId, "persona_filesystem_migrated", "persona_version",
                request.getPersonaId() + "@" + request.getVersion(),
                JsonUtils.toJsonString(Map.of("artifactHash", request.getArtifactHash())));
        boolean publish = "published".equals(request.getSourceStatus()) && valid && "passed".equals(testStatus);
        if (publish) {
            managementService.applyUpdate(userId, request.getPersonaId(), request.getVersion());
        }
        return Map.of(
                "personaId", request.getPersonaId(),
                "version", request.getVersion(),
                "status", publish ? "published" : "draft",
                "testStatus", testStatus);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> map(Object value) {
        return value instanceof Map<?, ?> ? (Map<String, Object>) value : Map.of();
    }

    private static boolean bool(Object value) {
        return Boolean.TRUE.equals(value) || "true".equalsIgnoreCase(String.valueOf(value));
    }

    private static String string(Object value, String fallback) {
        return value == null || String.valueOf(value).isBlank() ? fallback : String.valueOf(value);
    }

    private static Long nullableLong(Object value) {
        if (value == null || String.valueOf(value).isBlank()) return null;
        return value instanceof Number number ? number.longValue() : Long.valueOf(String.valueOf(value));
    }

    private static String abbreviate(String value, int max) {
        return StringUtils.abbreviate(StringUtils.defaultString(value), max);
    }

    private static String personaKind(Map<String, Object> source) {
        if (bool(source.get("is_fictional"))) return "fictional";
        if (bool(source.get("is_public_figure"))) return "public_figure";
        return bool(source.get("is_real_person")) ? "real_person" : "unverified";
    }

    private static String ceiling(Map<String, Object> policy) {
        Object raw = policy.get("allowed_stages");
        if (!(raw instanceof List<?> values)) return "friend";
        String ceiling = "familiar";
        for (Object value : values) {
            String stage = String.valueOf(value);
            if (STAGES.indexOf(stage) > STAGES.indexOf(ceiling)) ceiling = stage;
        }
        return ceiling;
    }
}
