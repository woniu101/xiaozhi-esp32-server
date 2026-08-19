package xiaozhi.modules.persona.service;

import java.util.Map;

import xiaozhi.modules.persona.dto.PersonaManagementDTO.FilesystemMigrationRequest;

public interface PersonaMigrationService {
    Map<String, Object> migrate(Long userId, FilesystemMigrationRequest request);
}
