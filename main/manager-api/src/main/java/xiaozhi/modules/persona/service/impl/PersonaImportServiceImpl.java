package xiaozhi.modules.persona.service.impl;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import lombok.RequiredArgsConstructor;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.persona.dao.PersonaDao;
import xiaozhi.modules.persona.dto.PersonaManagementDTO.UrlImportRequest;
import xiaozhi.modules.persona.metrics.PersonaMetrics;
import xiaozhi.modules.persona.service.PersonaImportService;
import xiaozhi.modules.persona.source.GitHubSourceDownloader;

@Service
@RequiredArgsConstructor
public class PersonaImportServiceImpl implements PersonaImportService {
    private static final int MAX_ARTIFACT_BYTES = 10 * 1024 * 1024;
    private final PersonaDao personaDao;
    private final PersonaImportWorker worker;
    private final GitHubSourceDownloader sourceDownloader;
    private final PersonaMetrics metrics;

    @Value("${companion.artifact-dir:uploadfile/personas}")
    private String artifactDirectory;

    @Override
    public String createUpload(Long userId, MultipartFile artifact) {
        return createUploadJob(userId, null, artifact);
    }

    @Override
    public String createUpgradeUpload(Long userId, String personaId, MultipartFile artifact) {
        requireOwnedPersona(userId, personaId);
        return createUploadJob(userId, personaId, artifact);
    }

    private String createUploadJob(Long userId, String expectedPersonaId, MultipartFile artifact) {
        requireRateLimit(userId);
        if (artifact == null || artifact.isEmpty() || artifact.getSize() > MAX_ARTIFACT_BYTES) {
            throw new RenException("Persona ZIP 为空或超过 10MB 限制");
        }
        String filename = StringUtils.defaultString(artifact.getOriginalFilename()).toLowerCase();
        if (!filename.endsWith(".zip")) {
            throw new RenException("Persona 制品必须是 ZIP 文件");
        }
        String jobId = newId();
        Path target = artifactPath(userId, jobId);
        try {
            Files.createDirectories(target.getParent());
            byte[] bytes = artifact.getBytes();
            requireZip(bytes);
            Files.write(target, bytes, StandardOpenOption.CREATE_NEW);
        } catch (IOException error) {
            throw new RenException("Persona ZIP 保存失败", error);
        }
        personaDao.insertImportJob(
                jobId, userId, expectedPersonaId, "upload", null, null, target.toString(), "queued");
        personaDao.insertAudit(userId, "persona_import_created", "persona_import_job", jobId,
                auditDetails("upload", expectedPersonaId, null));
        worker.inspect(jobId);
        metrics.increment("companion_persona_import_total", "provider", "upload", "status", "queued");
        return jobId;
    }

    @Override
    public String createUrl(Long userId, UrlImportRequest request) {
        return createUrlJob(userId, null, request.getUrl(), request.getRef());
    }

    @Override
    public String createUpgradeFromSource(Long userId, String personaId) {
        Map<String, Object> persona = requireOwnedPersona(userId, personaId);
        String sourceUrl = nullableText(persona.get("sourceUrl"));
        if (sourceUrl == null) {
            throw new RenException("该人物没有可用的 GitHub 来源，请上传新版 ZIP");
        }
        return createUrlJob(userId, personaId, sourceUrl,
                nullableText(persona.get("sourceRef")));
    }

    @Override
    public String createRecompile(
            Long userId, String personaId, String version, boolean inheritSignatureAudio) {
        Map<String, Object> persona = requireOwnedPersona(userId, personaId);
        Map<String, Object> base = requireVersion(userId, personaId, version);
        requireRateLimit(userId);

        String snapshot = nullableText(base.get("sourceArtifactPath"));
        if (snapshot == null && Objects.equals(base.get("artifactHash"), persona.get("artifactHash"))) {
            snapshot = nullableText(persona.get("rawArtifactPath"));
        }
        if (snapshot != null) {
            Path source = Path.of(snapshot).toAbsolutePath().normalize();
            Path root = Path.of(artifactDirectory).toAbsolutePath().normalize();
            if (source.startsWith(root) && Files.isRegularFile(source)) {
                try {
                    long size = Files.size(source);
                    if (size > 0 && size <= MAX_ARTIFACT_BYTES) {
                        return createRecompileUploadBytes(
                                userId, personaId, version, inheritSignatureAudio,
                                Files.readAllBytes(source), "snapshot");
                    }
                } catch (IOException error) {
                    throw new RenException("历史 Persona 制品快照读取失败", error);
                }
            }
        }

        String sourceUrl = nullableText(persona.get("sourceUrl"));
        String sourceCommit = nullableText(base.get("sourceCommit"));
        if (sourceUrl == null || sourceCommit == null) {
            throw new RenException("该版本缺少可验证的源码快照和 GitHub commit，请上传对应版本 ZIP 重新解析");
        }
        GitHubSourceDownloader.SourceDescriptor source = sourceDownloader.parse(sourceUrl, sourceCommit);
        String jobId = newId();
        personaDao.insertRecompileJob(
                jobId, userId, personaId, version, inheritSignatureAudio,
                "github", source.sourceUrl(), source.ref(), null, "queued");
        personaDao.insertAudit(userId, "persona_recompile_created", "persona_import_job", jobId,
                recompileAuditDetails(personaId, version, "github", inheritSignatureAudio));
        worker.inspect(jobId);
        metrics.increment("companion_persona_import_total", "provider", "recompile-github", "status", "queued");
        return jobId;
    }

    @Override
    public String createRecompileUpload(
            Long userId, String personaId, String version,
            boolean inheritSignatureAudio, MultipartFile artifact) {
        requireOwnedPersona(userId, personaId);
        requireVersion(userId, personaId, version);
        requireRateLimit(userId);
        if (artifact == null || artifact.isEmpty() || artifact.getSize() > MAX_ARTIFACT_BYTES) {
            throw new RenException("Persona ZIP 为空或超过 10MB 限制");
        }
        String filename = StringUtils.defaultString(artifact.getOriginalFilename()).toLowerCase();
        if (!filename.endsWith(".zip")) {
            throw new RenException("Persona 制品必须是 ZIP 文件");
        }
        try {
            return createRecompileUploadBytes(
                    userId, personaId, version, inheritSignatureAudio, artifact.getBytes(), "upload");
        } catch (IOException error) {
            throw new RenException("Persona ZIP 保存失败", error);
        }
    }

    private String createRecompileUploadBytes(
            Long userId, String personaId, String version,
            boolean inheritSignatureAudio, byte[] bytes, String sourceType) {
        requireZip(bytes);
        String jobId = newId();
        Path target = artifactPath(userId, jobId);
        try {
            Files.createDirectories(target.getParent());
            Files.write(target, bytes, StandardOpenOption.CREATE_NEW);
        } catch (IOException error) {
            throw new RenException("Persona ZIP 保存失败", error);
        }
        personaDao.insertRecompileJob(
                jobId, userId, personaId, version, inheritSignatureAudio,
                sourceType, null, null, target.toString(), "queued");
        personaDao.insertAudit(userId, "persona_recompile_created", "persona_import_job", jobId,
                recompileAuditDetails(personaId, version, sourceType, inheritSignatureAudio));
        worker.inspect(jobId);
        metrics.increment("companion_persona_import_total", "provider", "recompile-" + sourceType,
                "status", "queued");
        return jobId;
    }

    private String createUrlJob(Long userId, String expectedPersonaId, String url, String ref) {
        requireRateLimit(userId);
        GitHubSourceDownloader.SourceDescriptor source = sourceDownloader.parse(url, ref);
        String jobId = newId();
        personaDao.insertImportJob(
                jobId, userId, expectedPersonaId, "github", source.sourceUrl(), source.ref(), null, "queued");
        personaDao.insertAudit(userId, "persona_import_created", "persona_import_job", jobId,
                auditDetails("github", expectedPersonaId, source.sourceUrl()));
        worker.inspect(jobId);
        metrics.increment("companion_persona_import_total", "provider", "github", "status", "queued");
        return jobId;
    }

    private Map<String, Object> requireOwnedPersona(Long userId, String personaId) {
        Map<String, Object> persona = personaDao.selectPersona(userId, personaId);
        if (persona == null || !userId.equals(nullableLong(persona.get("ownerUserId")))) {
            throw new RenException("Persona 不存在或只有所有者可以升级");
        }
        return persona;
    }

    private Map<String, Object> requireVersion(Long userId, String personaId, String version) {
        Map<String, Object> value = personaDao.selectVersion(userId, personaId, version);
        if (value == null) {
            throw new RenException("Persona 版本不存在或不可访问");
        }
        return value;
    }

    private static String auditDetails(String sourceType, String expectedPersonaId, String sourceUrl) {
        Map<String, Object> details = new LinkedHashMap<>();
        details.put("sourceType", sourceType);
        if (StringUtils.isNotBlank(expectedPersonaId)) details.put("expectedPersonaId", expectedPersonaId);
        if (StringUtils.isNotBlank(sourceUrl)) details.put("sourceUrl", sourceUrl);
        return JsonUtils.toJsonString(details);
    }

    private static String recompileAuditDetails(
            String personaId, String version, String sourceType, boolean inheritSignatureAudio) {
        Map<String, Object> details = new LinkedHashMap<>();
        details.put("personaId", personaId);
        details.put("baseVersion", version);
        details.put("sourceType", sourceType);
        details.put("inheritSignatureAudio", inheritSignatureAudio);
        details.put("inheritSignatureOverrides", false);
        return JsonUtils.toJsonString(details);
    }

    private static Long nullableLong(Object value) {
        if (value == null) return null;
        return value instanceof Number number ? number.longValue() : Long.valueOf(String.valueOf(value));
    }

    private static String nullableText(Object value) {
        return value == null ? null : StringUtils.trimToNull(String.valueOf(value));
    }

    @Override
    public Map<String, Object> getJob(Long userId, String jobId) {
        Map<String, Object> job = personaDao.selectImportJob(jobId, userId);
        if (job == null) {
            throw new RenException("Persona 导入任务不存在");
        }
        Map<String, Object> result = new LinkedHashMap<>(job);
        parseJsonField(result, "inspectionJson", "inspection");
        parseJsonField(result, "compileResultJson", "compileResult");
        result.remove("artifactPath");
        return result;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void cancel(Long userId, String jobId) {
        Map<String, Object> job = personaDao.selectImportJob(jobId, userId);
        if (job == null || personaDao.cancelImportJob(jobId, userId) != 1) {
            throw new RenException("Persona 导入任务不存在或当前状态不能取消");
        }
        personaDao.insertAudit(userId, "persona_import_cancelled", "persona_import_job", jobId, "{}");
        metrics.increment("companion_persona_import_total", "provider", String.valueOf(job.get("sourceType")),
                "status", "cancelled");
    }

    private Path artifactPath(Long userId, String jobId) {
        Path root = Path.of(artifactDirectory).toAbsolutePath().normalize();
        Path target = root.resolve(String.valueOf(userId)).resolve(jobId + ".zip").normalize();
        if (!target.startsWith(root)) {
            throw new RenException("Persona 制品路径不合法");
        }
        return target;
    }

    private void requireRateLimit(Long userId) {
        if (personaDao.countRecentImports(userId) >= 10) {
            throw new RenException("Persona 导入过于频繁，请十分钟后重试");
        }
    }

    private static void requireZip(byte[] bytes) {
        if (bytes.length < 4 || bytes[0] != 'P' || bytes[1] != 'K'
                || bytes[2] != 3 || bytes[3] != 4) {
            throw new RenException("Persona 制品不是合法 ZIP");
        }
    }

    private static String newId() {
        return UUID.randomUUID().toString().replace("-", "");
    }

    private static void parseJsonField(Map<String, Object> value, String field, String outputField) {
        Object raw = value.remove(field);
        if (raw instanceof String text && StringUtils.isNotBlank(text)) {
            value.put(outputField, JsonUtils.parseMap(text));
        }
    }
}
