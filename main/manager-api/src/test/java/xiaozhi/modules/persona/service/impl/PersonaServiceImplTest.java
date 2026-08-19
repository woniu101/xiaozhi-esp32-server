package xiaozhi.modules.persona.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.LinkedHashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;

import xiaozhi.common.exception.RenException;
import xiaozhi.modules.persona.dao.PersonaDao;
import xiaozhi.modules.persona.dto.PersonaRuntimeDTO.ResolveRequest;

class PersonaServiceImplTest {
    @Test
    void resolvesPublishedPersonaAndParsesCanonicalSpec() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaServiceImpl service = new PersonaServiceImpl(dao);
        ResolveRequest request = new ResolveRequest();
        request.setAgentId("agent-1");
        request.setPersonaId("persona.test.rabbit");

        Map<String, Object> row = new LinkedHashMap<>();
        row.put("personaId", "persona.test.rabbit");
        row.put("version", "v1");
        row.put("artifactHash", "a".repeat(64));
        row.put("compilerVersion", "compiler/1");
        row.put("canonicalSpec", "{\"id\":\"persona.test.rabbit\"}");
        row.put("runtimePrompt", "prompt");
        row.put("relationshipCeiling", "friend");
        row.put("personaKind", "fictional");
        when(dao.selectRuntimeVersion("agent-1", "persona.test.rabbit", null)).thenReturn(row);

        Map<String, Object> resolved = service.resolveRuntime(request);
        assertEquals(false, resolved.get("notModified"));
        assertEquals("persona.test.rabbit", ((Map<?, ?>) resolved.get("canonicalSpec")).get("id"));
    }

    @Test
    void returnsNotModifiedForMatchingHash() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaServiceImpl service = new PersonaServiceImpl(dao);
        ResolveRequest request = new ResolveRequest();
        request.setAgentId("agent-1");
        request.setPersonaId("persona.test.rabbit");
        request.setKnownArtifactHash("a".repeat(64));
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("personaId", "persona.test.rabbit");
        row.put("version", "v1");
        row.put("artifactHash", "a".repeat(64));
        when(dao.selectRuntimeVersion("agent-1", "persona.test.rabbit", null)).thenReturn(row);

        assertEquals(true, service.resolveRuntime(request).get("notModified"));
    }

    @Test
    void rejectsUnpublishedOrInvisibleBinding() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaServiceImpl service = new PersonaServiceImpl(dao);
        when(dao.countBindableVersion(7L, "persona.private", "v1")).thenReturn(0);
        assertThrows(RenException.class, () -> service.requireBindable(7L, "persona.private", "v1"));
    }
}
