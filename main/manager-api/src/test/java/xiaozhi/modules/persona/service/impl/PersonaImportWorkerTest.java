package xiaozhi.modules.persona.service.impl;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;

import org.junit.jupiter.api.Test;

import xiaozhi.common.exception.RenException;

class PersonaImportWorkerTest {
    @Test
    void upgradeAcceptsTheResolvedTargetPersonaId() {
        assertDoesNotThrow(() -> PersonaImportWorker.requireExpectedPersonaId(
                "persona.test.u7", "persona.test.u7"));
    }

    @Test
    void upgradeRejectsAnArtifactForAnotherPersona() {
        RenException error = assertThrows(RenException.class,
                () -> PersonaImportWorker.requireExpectedPersonaId("persona.test", "persona.other"));

        assertTrue(error.getMessage().contains("Persona ID 与目标人物不一致"));
    }

    @Test
    void revisionNamesAlwaysUseTheOriginalVersionAsTheirRoot() {
        assertEquals("v1-c8dd3774", PersonaImportWorker.revisionRoot("v1-c8dd3774"));
        assertEquals("v1-c8dd3774", PersonaImportWorker.revisionRoot("v1-c8dd3774-r2"));
        assertEquals(64, PersonaImportWorker.revisionVersion("v".repeat(64), 12).length());
        assertTrue(PersonaImportWorker.revisionVersion("v".repeat(64), 12).endsWith("-r12"));
    }

    @Test
    void sameSourceCreatesARevisionOnlyWhenTheCurrentCompilerOutputChanged() {
        Map<String, Object> oldVersion = Map.of(
                "artifactHash", "a".repeat(64),
                "compiledHash", "1".repeat(64));

        assertTrue(PersonaImportWorker.sameSourceCompilerOutputChanged(
                "a".repeat(64), "2".repeat(64), oldVersion));
        assertEquals(false, PersonaImportWorker.sameSourceCompilerOutputChanged(
                "a".repeat(64), "1".repeat(64), oldVersion));
        assertEquals(false, PersonaImportWorker.sameSourceCompilerOutputChanged(
                "b".repeat(64), "2".repeat(64), oldVersion));
    }
}
