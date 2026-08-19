package xiaozhi.modules.persona.service;

import java.util.List;
import java.util.Map;

public interface PersonaManagementService {
    List<Map<String, Object>> list(Long userId);

    Map<String, Object> get(Long userId, String personaId);

    List<Map<String, Object>> versions(Long userId, String personaId);

    Map<String, Object> version(Long userId, String personaId, String version);

    Map<String, Object> diff(Long userId, String personaId, String from, String to);

    void publish(Long userId, String personaId, String version, String visibility);

    void rollback(Long userId, String personaId, String version);

    void archive(Long userId, String personaId, String version);

    Map<String, Object> rerunTest(Long userId, String personaId, String version);

    List<Map<String, Object>> testRuns(Long userId, String personaId, String version);

    byte[] exportFilesystemPackage(Long userId, String personaId, String version);

    List<Map<String, Object>> auditTrail(Long userId, String personaId);
}
