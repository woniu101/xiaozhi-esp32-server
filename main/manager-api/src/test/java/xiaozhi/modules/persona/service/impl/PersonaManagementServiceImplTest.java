package xiaozhi.modules.persona.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import xiaozhi.common.exception.RenException;
import xiaozhi.modules.persona.client.PersonaCompilerClient;
import xiaozhi.modules.persona.dao.PersonaDao;
import xiaozhi.modules.persona.metrics.PersonaMetrics;

class PersonaManagementServiceImplTest {
    @Test
    void applyUpdateMovesTheCandidateToCurrentAndPrunesOldArtifacts() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaManagementServiceImpl service = service(dao);
        stubOwnedPublishableVersion(dao);
        when(dao.publishVersion("persona.test", "v1", 7L)).thenReturn(1);
        when(dao.applySourceVersion("persona.test", "v1", 7L)).thenReturn(1);
        when(dao.selectLifecycleVersions("persona.test")).thenReturn(Map.of(
                "currentVersion", "v1",
                "previousVersion", "v0"));

        service.applyUpdate(7L, "persona.test", "v1");

        verify(dao).publishVersion("persona.test", "v1", 7L);
        verify(dao).applySourceVersion("persona.test", "v1", 7L);
        verify(dao).deleteVersionsOutsideLifecycle("persona.test", List.of("v1", "v0"));
        verify(dao).insertAudit(7L, "persona_update_applied", "persona_version", "persona.test@v1", "{}");
    }

    @Test
    void applyUpdateReportsValidationFailureBeforeWritingState() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaManagementServiceImpl service = service(dao);
        when(dao.selectPersona(7L, "persona.test")).thenReturn(Map.of("ownerUserId", 7L));
        Map<String, Object> version = publishableVersion();
        version.put("validationReport", "{\"valid\":false}");
        when(dao.selectVersion(7L, "persona.test", "v1")).thenReturn(version);

        RenException error = assertThrows(RenException.class,
                () -> service.applyUpdate(7L, "persona.test", "v1"));

        assertEquals("人物更新未通过结构校验，不能应用", error.getMessage());
        verify(dao, never()).publishVersion("persona.test", "v1", 7L);
        verify(dao, never()).applySourceVersion("persona.test", "v1", 7L);
    }

    @Test
    @SuppressWarnings({ "rawtypes", "unchecked" })
    void conversationSamplesAreForwardedToTheCompiler() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaCompilerClient compiler = mock(PersonaCompilerClient.class);
        when(dao.selectPersona(7L, "persona.test")).thenReturn(Map.of("ownerUserId", 7L));
        Map<String, Object> version = publishableVersion();
        version.put("runtimePrompt", "<companion_persona>test</companion_persona>");
        when(dao.selectVersion(7L, "persona.test", "v1")).thenReturn(version);
        when(compiler.test(anyMap())).thenReturn(Map.of("status", "passed", "score", 100));
        PersonaManagementServiceImpl service = new PersonaManagementServiceImpl(
                dao, compiler, mock(PersonaMetrics.class));
        List<Map<String, Object>> samples = List.of(Map.of(
                "scene", "comfort", "assistant", "先休息一下。"));

        service.rerunTest(7L, "persona.test", "v1", samples);

        ArgumentCaptor<Map> captor = ArgumentCaptor.forClass(Map.class);
        verify(compiler).test(captor.capture());
        assertEquals(samples, captor.getValue().get("conversationSamples"));
    }

    @Test
    void usageReportsOwnedAndExternalBindings() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaManagementServiceImpl service = service(dao);
        when(dao.selectPersona(7L, "persona.test")).thenReturn(Map.of("ownerUserId", 7L));
        when(dao.countPersonaBindings("persona.test")).thenReturn(3);
        when(dao.selectOwnedPersonaBindings("persona.test", 7L)).thenReturn(List.of(
                Map.of("agentId", "agent-1", "agentName", "测试智能体")));

        Map<String, Object> usage = service.usage(7L, "persona.test");

        assertEquals(3, usage.get("bindingCount"));
        assertEquals(2, usage.get("externalBindingCount"));
        assertEquals(true, usage.get("deletable"));
        assertEquals(3, usage.get("willUnbind"));
    }

    @Test
    void deletePermanentlyClearsBindingsRuntimeDataAndSource() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaManagementServiceImpl service = service(dao);
        when(dao.selectPersona(7L, "persona.test")).thenReturn(Map.of("ownerUserId", 7L));
        when(dao.selectPersonaArtifactPaths("persona.test", 7L)).thenReturn(List.of());
        when(dao.hardDeletePersonaSource("persona.test", 7L)).thenReturn(1);

        service.delete(7L, "persona.test", "persona.test");

        verify(dao).clearPersonaBindings("persona.test");
        verify(dao).deletePersonaMemories("persona.test");
        verify(dao).deletePersonaEvents("persona.test");
        verify(dao).deletePersonaTurns("persona.test");
        verify(dao).deletePersonaStates("persona.test");
        verify(dao).hardDeletePersonaSource("persona.test", 7L);
    }

    @Test
    void deleteRequiresExactPersonaIdConfirmation() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaManagementServiceImpl service = service(dao);
        when(dao.selectPersona(7L, "persona.test")).thenReturn(Map.of("ownerUserId", 7L));

        RenException error = assertThrows(RenException.class,
                () -> service.delete(7L, "persona.test", "wrong"));

        assertTrue(error.getMessage().contains("确认文本不匹配"));
        verify(dao, never()).hardDeletePersonaSource("persona.test", 7L);
    }

    @Test
    void restorePreviousSwapsOnlyTheTwoLifecyclePointers() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaManagementServiceImpl service = service(dao);
        when(dao.selectPersona(7L, "persona.test")).thenReturn(Map.of(
                "ownerUserId", 7L,
                "publishedVersion", "v2",
                "previousVersion", "v1"));
        when(dao.restorePreviousVersion("persona.test", 7L, "v2", "v1")).thenReturn(1);

        service.restorePrevious(7L, "persona.test");

        verify(dao).restorePreviousVersion("persona.test", 7L, "v2", "v1");
        verify(dao).insertAudit(eq(7L), eq("persona_previous_restored"), eq("persona_version"),
                eq("persona.test@v1"), anyString());
    }

    private static PersonaManagementServiceImpl service(PersonaDao dao) {
        return new PersonaManagementServiceImpl(
                dao, mock(PersonaCompilerClient.class), mock(PersonaMetrics.class));
    }

    private static void stubOwnedPublishableVersion(PersonaDao dao) {
        when(dao.selectPersona(7L, "persona.test")).thenReturn(Map.of("ownerUserId", 7L));
        when(dao.selectVersion(7L, "persona.test", "v1")).thenReturn(publishableVersion());
    }

    private static Map<String, Object> publishableVersion() {
        Map<String, Object> version = new LinkedHashMap<>();
        version.put("version", "v1");
        version.put("status", "draft");
        version.put("testStatus", "passed");
        version.put("validationReport", "{\"valid\":true}");
        version.put("canonicalSpec", "{}");
        return version;
    }
}
