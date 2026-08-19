package xiaozhi.modules.persona.service.impl;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.LinkedHashMap;
import java.util.Map;
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
        personaDao.insertImportJob(jobId, userId, "upload", null, null, target.toString(), "queued");
        personaDao.insertAudit(userId, "persona_import_created", "persona_import_job", jobId,
                JsonUtils.toJsonString(Map.of("sourceType", "upload")));
        worker.inspect(jobId);
        metrics.increment("companion_persona_import_total", "provider", "upload", "status", "queued");
        return jobId;
    }

    @Override
    public String createUrl(Long userId, UrlImportRequest request) {
        requireRateLimit(userId);
        GitHubSourceDownloader.SourceDescriptor source = sourceDownloader.parse(request.getUrl(), request.getRef());
        String jobId = newId();
        personaDao.insertImportJob(
                jobId, userId, "github", source.sourceUrl(), source.ref(), null, "queued");
        personaDao.insertAudit(userId, "persona_import_created", "persona_import_job", jobId,
                JsonUtils.toJsonString(Map.of("sourceType", "github", "sourceUrl", source.sourceUrl())));
        worker.inspect(jobId);
        metrics.increment("companion_persona_import_total", "provider", "github", "status", "queued");
        return jobId;
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
