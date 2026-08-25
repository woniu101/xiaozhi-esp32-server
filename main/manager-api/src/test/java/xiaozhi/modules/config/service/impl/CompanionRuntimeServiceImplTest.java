package xiaozhi.modules.config.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.anyDouble;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

import xiaozhi.modules.config.dao.CompanionRuntimeDao;
import xiaozhi.modules.config.dto.CompanionRuntimeDTO.CommitRequest;
import xiaozhi.modules.config.dto.CompanionRuntimeDTO.EventItem;
import xiaozhi.modules.config.dto.CompanionRuntimeDTO.MemoryItem;
import xiaozhi.modules.config.dto.CompanionRuntimeDTO.MemoryUpdateRequest;

class CompanionRuntimeServiceImplTest {
    @Test
    void commitUsesRevisionAndPersistsOneIdempotentTurn() {
        CompanionRuntimeDao dao = mock(CompanionRuntimeDao.class);
        when(dao.countRuntimeIdentity("user-1", "agent-1", "persona-1")).thenReturn(1);
        when(dao.countTurn("turn-1")).thenReturn(0);
        when(dao.selectRevisionForUpdate("user-1", "agent-1", "persona-1")).thenReturn(2L);
        when(dao.updateState(anyString(), anyString(), anyString(), anyLong(), anyLong(), anyString(), anyString()))
                .thenReturn(1);
        CompanionRuntimeServiceImpl service = new CompanionRuntimeServiceImpl(dao);

        CommitRequest request = request(2L, 3L);
        assertEquals("committed", service.commit(request));

        verify(dao).insertTurn(eq("turn-1"), eq("user-1"), eq("agent-1"), eq("persona-1"),
                eq(3L), anyString());
        verify(dao).insertEvent(
                anyString(), anyString(), anyString(), anyString(), anyString(), anyString(), anyString(), anyDouble());
        verify(dao).upsertMemory(
                anyString(), anyString(), anyString(), anyString(), any(), anyString(), anyString(),
                anyDouble(), anyDouble(), anyString(), any(), any(), anyString());
    }

    @Test
    void conflictDoesNotWriteEventsOrTurn() {
        CompanionRuntimeDao dao = mock(CompanionRuntimeDao.class);
        when(dao.countRuntimeIdentity("user-1", "agent-1", "persona-1")).thenReturn(1);
        when(dao.countTurn("turn-1")).thenReturn(0);
        when(dao.selectRevisionForUpdate("user-1", "agent-1", "persona-1")).thenReturn(4L);
        CompanionRuntimeServiceImpl service = new CompanionRuntimeServiceImpl(dao);

        assertEquals("conflict", service.commit(request(2L, 3L)));
        verify(dao, never()).insertTurn(
                anyString(), anyString(), anyString(), anyString(), anyLong(), anyString());
        verify(dao, never()).insertEvent(
                anyString(), anyString(), anyString(), anyString(), anyString(), anyString(), anyString(), anyDouble());
    }

    @Test
    void subjectMemorySupersedesOnlyTheSamePersonaSubject() {
        CompanionRuntimeDao dao = mock(CompanionRuntimeDao.class);
        when(dao.countRuntimeIdentity("user-1", "agent-1", "persona-1")).thenReturn(1);
        when(dao.countTurn("turn-1")).thenReturn(0);
        when(dao.selectRevisionForUpdate("user-1", "agent-1", "persona-1")).thenReturn(2L);
        when(dao.updateState(anyString(), anyString(), anyString(), anyLong(), anyLong(), anyString(), anyString()))
                .thenReturn(1);
        CommitRequest request = request(2L, 3L);
        request.getMemories().get(0).setSubjectKey("preference:咖啡");
        when(dao.selectMemoryId(eq("user-1"), eq("agent-1"), eq("persona-1"),
                eq("semantic"), anyString())).thenReturn(12L);

        assertEquals("committed", new CompanionRuntimeServiceImpl(dao).commit(request));

        verify(dao).supersedeMemories(
                eq("user-1"), eq("agent-1"), eq("persona-1"),
                eq("semantic"), eq("preference:咖啡"), anyString());
        verify(dao).linkSupersededMemories(
                eq("user-1"), eq("agent-1"), eq("persona-1"), eq("semantic"),
                eq("preference:咖啡"), anyString(), eq(12L));
    }

    @Test
    void forgetOperationDoesNotInsertANewMemory() {
        CompanionRuntimeDao dao = mock(CompanionRuntimeDao.class);
        when(dao.countRuntimeIdentity("user-1", "agent-1", "persona-1")).thenReturn(1);
        when(dao.countTurn("turn-1")).thenReturn(0);
        when(dao.selectRevisionForUpdate("user-1", "agent-1", "persona-1")).thenReturn(2L);
        when(dao.updateState(anyString(), anyString(), anyString(), anyLong(), anyLong(), anyString(), anyString()))
                .thenReturn(1);
        CommitRequest request = request(2L, 3L);
        request.getMemories().get(0).setSubjectKey("preference:咖啡");
        request.getMemories().get(0).setOperation("forget");

        new CompanionRuntimeServiceImpl(dao).commit(request);

        verify(dao).forgetMemories(
                eq("user-1"), eq("agent-1"), eq("persona-1"), eq("semantic"),
                eq("preference:咖啡"), anyString());
        verify(dao, never()).upsertMemory(
                anyString(), anyString(), anyString(), anyString(), any(), anyString(), anyString(),
                anyDouble(), anyDouble(), anyString(), any(), any(), anyString());
    }

    @Test
    void updateMemoryIsScopedAndAudited() {
        CompanionRuntimeDao dao = mock(CompanionRuntimeDao.class);
        when(dao.countRuntimeIdentity("user-1", "agent-1", "persona-1")).thenReturn(1);
        when(dao.updateMemory(eq(7L), eq("user-1"), eq("agent-1"), eq("persona-1"),
                eq("用户改为喜欢红茶"), anyString(), eq(0.8), any())).thenReturn(1);
        MemoryUpdateRequest request = new MemoryUpdateRequest();
        request.setContent("用户改为喜欢红茶");
        request.setImportance(0.8);

        new CompanionRuntimeServiceImpl(dao).updateMemory(
                "user-1", "agent-1", "persona-1", 7L, request, 9L);

        verify(dao).insertAudit(eq(9L), eq("companion_memory_update"), eq("memory"), eq("7"), anyString());
    }

    @Test
    void deleteMemoryIsScopedAndAudited() {
        CompanionRuntimeDao dao = mock(CompanionRuntimeDao.class);
        when(dao.countRuntimeIdentity("user-1", "agent-1", "persona-1")).thenReturn(1);
        when(dao.deleteMemory(7L, "user-1", "agent-1", "persona-1")).thenReturn(1);

        new CompanionRuntimeServiceImpl(dao).deleteMemory(
                "user-1", "agent-1", "persona-1", 7L, 9L);

        verify(dao).insertAudit(eq(9L), eq("companion_memory_delete"), eq("memory"), eq("7"), anyString());
    }

    @Test
    void resetRelationshipKeepsMemoriesAndAuditsTheChange() {
        CompanionRuntimeDao dao = mock(CompanionRuntimeDao.class);
        when(dao.countRuntimeIdentity("user-1", "agent-1", "persona-1")).thenReturn(1);

        new CompanionRuntimeServiceImpl(dao).resetRelationship(
                "user-1", "agent-1", "persona-1", 9L);

        verify(dao).resetRelationship("user-1", "agent-1", "persona-1");
        verify(dao, never()).deleteMemories(anyString(), anyString(), anyString());
        verify(dao).insertAudit(eq(9L), eq("companion_relationship_reset"), eq("agent"),
                eq("agent-1"), anyString());
    }

    @Test
    void latestDiagnosticReturnsDecodedNonSensitiveTrace() {
        CompanionRuntimeDao dao = mock(CompanionRuntimeDao.class);
        when(dao.countRuntimeIdentity("user-1", "agent-1", "persona-1")).thenReturn(1);
        when(dao.selectLatestDiagnostic("user-1", "agent-1", "persona-1")).thenReturn(Map.of(
                "turnId", "turn-9",
                "diagnosticJson", "{\"eventTypes\":[\"user_showed_care\"]}",
                "createdAt", "2026-08-20T12:00:00"));

        Map<String, Object> result = new CompanionRuntimeServiceImpl(dao)
                .getLatestDiagnostic("user-1", "agent-1", "persona-1");

        assertEquals("turn-9", result.get("turnId"));
        assertEquals(List.of("user_showed_care"), result.get("eventTypes"));
    }

    @Test
    void unboundRuntimeIdentityIsBlockedBeforeStateRead() {
        CompanionRuntimeDao dao = mock(CompanionRuntimeDao.class);
        when(dao.countRuntimeIdentity("user-1", "agent-1", "persona-other")).thenReturn(0);

        assertThrows(RuntimeException.class, () -> new CompanionRuntimeServiceImpl(dao)
                .getState("user-1", "agent-1", "persona-other"));

        verify(dao, never()).selectState(anyString(), anyString(), anyString());
    }

    private CommitRequest request(long expectedRevision, long newRevision) {
        EventItem event = new EventItem();
        event.setEventType("user_showed_care");
        event.setConfidence(0.8);
        event.setPayload(Map.of());

        MemoryItem memory = new MemoryItem();
        memory.setMemoryType("semantic");
        memory.setContent("用户喜欢咖啡");
        memory.setImportance(0.7);
        memory.setConfidence(0.8);
        memory.setSensitivity("personal");

        CommitRequest request = new CommitRequest();
        request.setUserId("user-1");
        request.setAgentId("agent-1");
        request.setPersonaId("persona-1");
        request.setTurnId("turn-1");
        request.setExpectedRevision(expectedRevision);
        request.setState(Map.of(
                "emotion", Map.of("warmth", 0.6),
                "relationship", Map.of("stage", "familiar"),
                "revision", newRevision));
        request.setEvents(List.of(event));
        request.setMemories(List.of(memory));
        return request;
    }
}
