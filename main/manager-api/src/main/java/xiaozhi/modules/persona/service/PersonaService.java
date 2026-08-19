package xiaozhi.modules.persona.service;

import java.util.List;
import java.util.Map;

import xiaozhi.modules.persona.dto.PersonaRuntimeDTO.ResolveRequest;

public interface PersonaService {
    Map<String, Object> resolveRuntime(ResolveRequest request);

    void requireBindable(Long userId, String personaId, String version);

    List<Map<String, Object>> listBindable(Long userId);

    void recordBindingAudit(Long userId, String agentId, boolean enabled, String personaId, String version);
}
