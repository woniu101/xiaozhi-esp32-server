package xiaozhi.modules.config.service;

import java.util.List;
import java.util.Map;

import xiaozhi.modules.config.dto.CompanionRuntimeDTO.CommitRequest;
import xiaozhi.modules.config.dto.CompanionRuntimeDTO.MemoryUpdateRequest;

public interface CompanionRuntimeService {
    Map<String, Object> getState(String userId, String agentId, String personaId);

    String commit(CommitRequest request);

    List<Map<String, Object>> getMemories(String userId, String agentId, String personaId, int limit);

    List<Map<String, Object>> getManagedMemories(String userId, String agentId, String personaId, int limit);

    void updateMemory(String userId, String agentId, String personaId, Long memoryId,
            MemoryUpdateRequest request, Long operatorUserId);

    void deleteMemory(String userId, String agentId, String personaId, Long memoryId, Long operatorUserId);

    Map<String, Object> getSummary(String userId, String agentId, String personaId);

    Map<String, Object> getLatestDiagnostic(String userId, String agentId, String personaId);

    void resetRelationship(String userId, String agentId, String personaId, Long operatorUserId);

    void reset(String userId, String agentId, String personaId, Long operatorUserId);
}
