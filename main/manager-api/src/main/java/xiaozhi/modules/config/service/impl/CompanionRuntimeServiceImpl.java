package xiaozhi.modules.config.service.impl;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import lombok.AllArgsConstructor;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.config.dao.CompanionRuntimeDao;
import xiaozhi.modules.config.dto.CompanionRuntimeDTO.CommitRequest;
import xiaozhi.modules.config.dto.CompanionRuntimeDTO.EventItem;
import xiaozhi.modules.config.dto.CompanionRuntimeDTO.MemoryItem;
import xiaozhi.modules.config.dto.CompanionRuntimeDTO.MemoryUpdateRequest;
import xiaozhi.modules.config.service.CompanionRuntimeService;

@Service
@AllArgsConstructor
public class CompanionRuntimeServiceImpl implements CompanionRuntimeService {
    private final CompanionRuntimeDao companionRuntimeDao;

    @Override
    public Map<String, Object> getState(String userId, String agentId, String personaId) {
        requireRuntimeIdentity(userId, agentId, personaId);
        Map<String, Object> row = companionRuntimeDao.selectState(userId, agentId, personaId);
        Map<String, Object> state = new HashMap<>();
        if (row == null) {
            state.put("emotion", new HashMap<>());
            state.put("relationship", new HashMap<>());
            state.put("revision", 0L);
            return state;
        }
        state.put("emotion", jsonObject(row.get("emotionJson")));
        state.put("relationship", jsonObject(row.get("relationshipJson")));
        state.put("revision", ((Number) row.getOrDefault("revision", 0L)).longValue());
        return state;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public String commit(CommitRequest request) {
        requireRuntimeIdentity(request.getUserId(), request.getAgentId(), request.getPersonaId());
        companionRuntimeDao.lockAgent(request.getAgentId());
        if (companionRuntimeDao.countTurn(request.getTurnId()) > 0) {
            return "duplicate";
        }
        companionRuntimeDao.ensureState(request.getUserId(), request.getAgentId(), request.getPersonaId());
        long actualRevision = companionRuntimeDao
                .selectRevisionForUpdate(request.getUserId(), request.getAgentId(), request.getPersonaId());
        if (actualRevision != request.getExpectedRevision()) {
            return "conflict";
        }

        Map<String, Object> state = request.getState();
        Object revisionValue = state.get("revision");
        if (!(revisionValue instanceof Number)) {
            throw new RenException(ErrorCode.PARAM_JSON_INVALID);
        }
        long newRevision = ((Number) revisionValue).longValue();
        if (newRevision != actualRevision + 1) {
            throw new RenException(ErrorCode.PARAM_JSON_INVALID);
        }
        int updated = companionRuntimeDao.updateState(
                request.getUserId(),
                request.getAgentId(),
                request.getPersonaId(),
                actualRevision,
                newRevision,
                JsonUtils.toJsonString(mapValue(state.get("emotion"))),
                JsonUtils.toJsonString(mapValue(state.get("relationship"))));
        if (updated != 1) {
            return "conflict";
        }

        for (EventItem event : safeList(request.getEvents())) {
            if (event == null || event.getEventType() == null || event.getEventType().isBlank()) {
                continue;
            }
            Map<String, Object> payload = event.getPayload() == null ? Map.of() : event.getPayload();
            String payloadJson = JsonUtils.toJsonString(payload);
            companionRuntimeDao.insertEvent(
                    request.getTurnId(),
                    request.getUserId(),
                    request.getAgentId(),
                    request.getPersonaId(),
                    event.getEventType().substring(0, Math.min(64, event.getEventType().length())),
                    payloadJson,
                    sha256(payloadJson),
                    clamp(event.getConfidence()));
        }

        for (MemoryItem memory : safeList(request.getMemories())) {
            if (memory == null || memory.getContent() == null || memory.getContent().isBlank()) {
                continue;
            }
            String content = memory.getContent().strip();
            if (content.length() > 1000) {
                content = content.substring(0, 1000);
            }
            String normalized = content.replaceAll("\\s+", "").toLowerCase(Locale.ROOT);
            String normalizedHash = sha256(normalized);
            String memoryType = safeText(memory.getMemoryType(), "semantic", 32);
            String sensitivity = safeText(memory.getSensitivity(), "personal", 32);
            String subjectKey = safeNullableText(memory.getSubjectKey(), 190);
            if ("forget".equalsIgnoreCase(memory.getOperation())) {
                companionRuntimeDao.forgetMemories(
                        request.getUserId(), request.getAgentId(), request.getPersonaId(),
                        memoryType, subjectKey, normalizedHash);
                continue;
            }
            if (subjectKey != null) {
                companionRuntimeDao.supersedeMemories(
                        request.getUserId(), request.getAgentId(), request.getPersonaId(),
                        memoryType, subjectKey, normalizedHash);
            }
            companionRuntimeDao.upsertMemory(
                    request.getUserId(),
                    request.getAgentId(),
                    request.getPersonaId(),
                    memoryType,
                    subjectKey,
                    content,
                    normalizedHash,
                    clamp(memory.getImportance()),
                    clamp(memory.getConfidence()),
                    sensitivity,
                    parseDateTime(memory.getOccurredAt()),
                    parseDateTime(memory.getExpiresAt()),
                    request.getTurnId());
            if (subjectKey != null) {
                Long storedMemoryId = companionRuntimeDao.selectMemoryId(
                        request.getUserId(), request.getAgentId(), request.getPersonaId(),
                        memoryType, normalizedHash);
                if (storedMemoryId != null) {
                    companionRuntimeDao.linkSupersededMemories(
                            request.getUserId(), request.getAgentId(), request.getPersonaId(),
                            memoryType, subjectKey, normalizedHash, storedMemoryId);
                }
            }
        }
        companionRuntimeDao.insertTurn(
                request.getTurnId(), request.getUserId(), request.getAgentId(), request.getPersonaId(), newRevision,
                JsonUtils.toJsonString(request.getDiagnostic() == null ? Map.of() : request.getDiagnostic()));
        return "committed";
    }

    @Override
    public List<Map<String, Object>> getMemories(String userId, String agentId, String personaId, int limit) {
        requireRuntimeIdentity(userId, agentId, personaId);
        int safeLimit = Math.max(1, Math.min(100, limit));
        List<Map<String, Object>> memories = companionRuntimeDao.selectMemories(userId, agentId, personaId, safeLimit);
        List<Long> ids = new ArrayList<>();
        for (Map<String, Object> memory : memories) {
            Object id = memory.get("id");
            if (id instanceof Number) {
                ids.add(((Number) id).longValue());
            }
        }
        if (!ids.isEmpty()) {
            companionRuntimeDao.touchMemories(ids);
        }
        return memories;
    }

    @Override
    public List<Map<String, Object>> getManagedMemories(
            String userId, String agentId, String personaId, int limit) {
        requireRuntimeIdentity(userId, agentId, personaId);
        return companionRuntimeDao.selectManagedMemories(
                userId, agentId, personaId, Math.max(1, Math.min(500, limit)));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateMemory(String userId, String agentId, String personaId, Long memoryId,
            MemoryUpdateRequest request, Long operatorUserId) {
        requireRuntimeIdentity(userId, agentId, personaId);
        String content = request.getContent().strip();
        if (content.length() > 1000) {
            content = content.substring(0, 1000);
        }
        String normalized = content.replaceAll("\\s+", "").toLowerCase(Locale.ROOT);
        double importance = clamp(request.getImportance() == null ? 0.5 : request.getImportance());
        int updated = companionRuntimeDao.updateMemory(
                memoryId, userId, agentId, personaId, content, sha256(normalized), importance,
                parseDateTime(request.getExpiresAt()));
        if (updated != 1) {
            throw new RenException(ErrorCode.RESOURCE_NOT_FOUND);
        }
        companionRuntimeDao.insertAudit(operatorUserId, "companion_memory_update", "memory",
                String.valueOf(memoryId), JsonUtils.toJsonString(Map.of("agentId", agentId, "personaId", personaId)));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteMemory(String userId, String agentId, String personaId, Long memoryId, Long operatorUserId) {
        requireRuntimeIdentity(userId, agentId, personaId);
        if (companionRuntimeDao.deleteMemory(memoryId, userId, agentId, personaId) != 1) {
            throw new RenException(ErrorCode.RESOURCE_NOT_FOUND);
        }
        companionRuntimeDao.insertAudit(operatorUserId, "companion_memory_delete", "memory",
                String.valueOf(memoryId), JsonUtils.toJsonString(Map.of("agentId", agentId, "personaId", personaId)));
    }

    @Override
    public Map<String, Object> getSummary(String userId, String agentId, String personaId) {
        Map<String, Object> state = getState(userId, agentId, personaId);
        Map<String, Object> relationship = mapValue(state.get("relationship"));
        Map<String, Object> summary = new HashMap<>();
        summary.put("stage", relationship.getOrDefault("stage", "familiar"));
        summary.put("meaningfulTurns", relationship.getOrDefault("meaningful_turns", 0));
        summary.put("sharedEventCount", relationship.getOrDefault("shared_event_count", 0));
        summary.put("revision", state.getOrDefault("revision", 0));
        summary.put("memoryCount", companionRuntimeDao.countMemories(userId, agentId, personaId));
        summary.put("personaId", personaId);
        return summary;
    }

    @Override
    public Map<String, Object> getLatestDiagnostic(String userId, String agentId, String personaId) {
        requireRuntimeIdentity(userId, agentId, personaId);
        Map<String, Object> row = companionRuntimeDao.selectLatestDiagnostic(userId, agentId, personaId);
        if (row == null) {
            return Map.of();
        }
        Map<String, Object> result = jsonObject(row.get("diagnosticJson"));
        result.put("turnId", row.get("turnId"));
        result.put("createdAt", row.get("createdAt"));
        return result;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void resetRelationship(
            String userId, String agentId, String personaId, Long operatorUserId) {
        requireRuntimeIdentity(userId, agentId, personaId);
        companionRuntimeDao.lockAgent(agentId);
        companionRuntimeDao.resetRelationship(userId, agentId, personaId);
        companionRuntimeDao.insertAudit(
                operatorUserId,
                "companion_relationship_reset",
                "agent",
                agentId,
                JsonUtils.toJsonString(Map.of("ownerUserId", userId, "personaId", personaId)));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void reset(String userId, String agentId, String personaId, Long operatorUserId) {
        requireRuntimeIdentity(userId, agentId, personaId);
        companionRuntimeDao.lockAgent(agentId);
        int memories = companionRuntimeDao.countMemories(userId, agentId, personaId);
        companionRuntimeDao.deleteMemories(userId, agentId, personaId);
        companionRuntimeDao.deleteEvents(userId, agentId, personaId);
        companionRuntimeDao.deleteTurns(userId, agentId, personaId);
        companionRuntimeDao.deleteState(userId, agentId, personaId);
        companionRuntimeDao.insertAudit(
                operatorUserId,
                "companion_state_reset",
                "agent",
                agentId,
                JsonUtils.toJsonString(Map.of(
                        "ownerUserId", userId,
                        "personaId", personaId,
                        "deletedMemoryCount", memories)));
    }

    private Map<String, Object> jsonObject(Object value) {
        if (value == null) {
            return new HashMap<>();
        }
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> result = new HashMap<>();
            map.forEach((key, item) -> result.put(String.valueOf(key), item));
            return result;
        }
        if (value instanceof byte[] bytes) {
            return JsonUtils.parseMap(new String(bytes, StandardCharsets.UTF_8));
        }
        return JsonUtils.parseMap(String.valueOf(value));
    }

    private void requireRuntimeIdentity(String userId, String agentId, String personaId) {
        if (companionRuntimeDao.countRuntimeIdentity(userId, agentId, personaId) != 1) {
            throw new RenException(ErrorCode.RESOURCE_NOT_FOUND);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mapValue(Object value) {
        if (!(value instanceof Map<?, ?>)) {
            throw new RenException(ErrorCode.PARAM_JSON_INVALID);
        }
        return (Map<String, Object>) value;
    }

    private <T> List<T> safeList(List<T> values) {
        return values == null ? List.of() : values;
    }

    private double clamp(Double value) {
        return Math.max(0.0, Math.min(1.0, value == null ? 0.0 : value));
    }

    private String safeText(String value, String defaultValue, int maxLength) {
        String result = value == null || value.isBlank() ? defaultValue : value.strip();
        return result.substring(0, Math.min(maxLength, result.length()));
    }

    private String safeNullableText(String value, int maxLength) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String result = value.strip();
        return result.substring(0, Math.min(maxLength, result.length()));
    }

    private LocalDateTime parseDateTime(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return OffsetDateTime.parse(value).toLocalDateTime();
        } catch (Exception ignored) {
            try {
                return LocalDateTime.parse(value);
            } catch (Exception invalid) {
                throw new RenException(ErrorCode.PARAM_JSON_INVALID);
            }
        }
    }

    private String sha256(String value) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }
}
