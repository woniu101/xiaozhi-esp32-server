package xiaozhi.modules.persona.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.LinkedHashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;

import xiaozhi.common.exception.RenException;
import xiaozhi.modules.persona.client.PersonaCompilerClient;
import xiaozhi.modules.persona.dao.PersonaDao;
import xiaozhi.modules.persona.metrics.PersonaMetrics;

class PersonaManagementServiceImplTest {
    @Test
    void publishUpdatesVersionAndSourceAsTwoSingleRowOperations() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaManagementServiceImpl service = service(dao);
        stubOwnedPublishableVersion(dao);
        when(dao.publishVersion("persona.test", "v1", 7L)).thenReturn(1);
        when(dao.publishSource("persona.test", "v1", 7L, "private")).thenReturn(1);

        service.publish(7L, "persona.test", "v1", "private");

        verify(dao).publishVersion("persona.test", "v1", 7L);
        verify(dao).publishSource("persona.test", "v1", 7L, "private");
        verify(dao).insertAudit(7L, "persona_published", "persona_version", "persona.test@v1",
                "{\"visibility\":\"private\"}");
    }

    @Test
    void publishReportsValidationFailureBeforeWritingState() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaManagementServiceImpl service = service(dao);
        when(dao.selectPersona(7L, "persona.test")).thenReturn(Map.of("ownerUserId", 7L));
        Map<String, Object> version = publishableVersion();
        version.put("validationReport", "{\"valid\":false}");
        when(dao.selectVersion(7L, "persona.test", "v1")).thenReturn(version);

        RenException error = assertThrows(RenException.class,
                () -> service.publish(7L, "persona.test", "v1", "private"));

        assertEquals("Persona 未通过结构校验，不能发布", error.getMessage());
        verify(dao, never()).publishVersion("persona.test", "v1", 7L);
        verify(dao, never()).publishSource("persona.test", "v1", 7L, "private");
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
