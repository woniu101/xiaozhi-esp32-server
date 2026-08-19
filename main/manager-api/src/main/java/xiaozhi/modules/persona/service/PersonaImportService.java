package xiaozhi.modules.persona.service;

import java.util.Map;

import org.springframework.web.multipart.MultipartFile;

import xiaozhi.modules.persona.dto.PersonaManagementDTO.UrlImportRequest;

public interface PersonaImportService {
    String createUpload(Long userId, MultipartFile artifact);

    String createUrl(Long userId, UrlImportRequest request);

    Map<String, Object> getJob(Long userId, String jobId);

    void cancel(Long userId, String jobId);
}
