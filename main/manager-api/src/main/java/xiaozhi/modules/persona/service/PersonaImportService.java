package xiaozhi.modules.persona.service;

import java.util.Map;

import org.springframework.web.multipart.MultipartFile;

import xiaozhi.modules.persona.dto.PersonaManagementDTO.UrlImportRequest;

public interface PersonaImportService {
    String createUpload(Long userId, MultipartFile artifact);

    String createUrl(Long userId, UrlImportRequest request);

    String createUpgradeUpload(Long userId, String personaId, MultipartFile artifact);

    String createUpgradeFromSource(Long userId, String personaId);

    String createRecompile(Long userId, String personaId, String version, boolean inheritSignatureAudio);

    String createRecompileUpload(
            Long userId, String personaId, String version,
            boolean inheritSignatureAudio, MultipartFile artifact);

    Map<String, Object> getJob(Long userId, String jobId);

    void cancel(Long userId, String jobId);
}
