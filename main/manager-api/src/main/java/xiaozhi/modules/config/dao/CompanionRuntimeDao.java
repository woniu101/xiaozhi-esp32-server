package xiaozhi.modules.config.dao;

import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface CompanionRuntimeDao {
    int countRuntimeIdentity(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId);

    String lockAgent(@Param("agentId") String agentId);

    Map<String, Object> selectState(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId);

    int ensureState(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId);

    Long selectRevisionForUpdate(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId);

    int updateState(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId,
            @Param("expectedRevision") long expectedRevision,
            @Param("revision") long revision,
            @Param("emotionJson") String emotionJson,
            @Param("relationshipJson") String relationshipJson);

    int countTurn(@Param("turnId") String turnId);

    int insertTurn(
            @Param("turnId") String turnId,
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId,
            @Param("revision") long revision,
            @Param("diagnosticJson") String diagnosticJson);

    Map<String, Object> selectLatestDiagnostic(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId);

    int insertEvent(
            @Param("turnId") String turnId,
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId,
            @Param("eventType") String eventType,
            @Param("payloadJson") String payloadJson,
            @Param("payloadHash") String payloadHash,
            @Param("confidence") double confidence);

    int upsertMemory(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId,
            @Param("memoryType") String memoryType,
            @Param("subjectKey") String subjectKey,
            @Param("content") String content,
            @Param("normalizedHash") String normalizedHash,
            @Param("importance") double importance,
            @Param("confidence") double confidence,
            @Param("sensitivity") String sensitivity,
            @Param("occurredAt") java.time.LocalDateTime occurredAt,
            @Param("expiresAt") java.time.LocalDateTime expiresAt,
            @Param("sourceTurnId") String sourceTurnId);

    int supersedeMemories(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId,
            @Param("memoryType") String memoryType,
            @Param("subjectKey") String subjectKey,
            @Param("normalizedHash") String normalizedHash);

    int forgetMemories(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId,
            @Param("memoryType") String memoryType,
            @Param("subjectKey") String subjectKey,
            @Param("normalizedHash") String normalizedHash);

    Long selectMemoryId(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId,
            @Param("memoryType") String memoryType,
            @Param("normalizedHash") String normalizedHash);

    int linkSupersededMemories(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId,
            @Param("memoryType") String memoryType,
            @Param("subjectKey") String subjectKey,
            @Param("normalizedHash") String normalizedHash,
            @Param("supersededBy") Long supersededBy);

    List<Map<String, Object>> selectMemories(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId,
            @Param("limit") int limit);

    List<Map<String, Object>> selectManagedMemories(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId,
            @Param("limit") int limit);

    int updateMemory(
            @Param("id") Long id,
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId,
            @Param("content") String content,
            @Param("normalizedHash") String normalizedHash,
            @Param("importance") double importance,
            @Param("expiresAt") java.time.LocalDateTime expiresAt);

    int deleteMemory(
            @Param("id") Long id,
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId);

    int touchMemories(@Param("ids") List<Long> ids);

    int countMemories(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId);

    int deleteMemories(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId);

    int deleteEvents(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId);

    int deleteTurns(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId);

    int deleteState(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId);

    int resetRelationship(
            @Param("userId") String userId,
            @Param("agentId") String agentId,
            @Param("personaId") String personaId);

    int insertAudit(
            @Param("operatorUserId") Long operatorUserId,
            @Param("action") String action,
            @Param("targetType") String targetType,
            @Param("targetId") String targetId,
            @Param("detailsJson") String detailsJson);
}
