package xiaozhi.modules.persona.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import xiaozhi.modules.persona.dao.PersonaDao;
import xiaozhi.modules.persona.dto.PersonaRuntimeDTO.SignatureAssetRequest;

class PersonaSignatureServiceImplTest {
    @Test
    @SuppressWarnings("unchecked")
    void runtimeMergeKeepsSkillSemanticsAndAddsPortableAssetUri() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaSignatureServiceImpl service = new PersonaSignatureServiceImpl(dao);
        Map<String, Object> signature = Map.of(
                "id", "ciallo",
                "display_text", "Ciallo～(∠・ω< )⌒★",
                "semantic_rule", "直接点名，或兔娘直播语境中的共享指代能唯一指向招牌问候时使用；间接点单可先装作没懂半拍",
                "explicit_aliases", List.of("Ciallo"),
                "assets", Map.of());
        when(dao.selectSignatureOverrides("persona.rabbit", "v1")).thenReturn(List.of());
        when(dao.selectSignatureAssets("persona.rabbit", "v1")).thenReturn(List.of(Map.of(
                "assetId", "asset12345678",
                "signatureKey", "ciallo",
                "variant", "classic",
                "sha256", "a".repeat(64))));

        List<Map<String, Object>> result = service.mergeRuntimeSignatures(
                "persona.rabbit", "v1", Map.of("signature_utterances", List.of(signature)));

        assertEquals(1, result.size());
        assertEquals("skill", result.get(0).get("origin"));
        assertEquals("直接点名，或兔娘直播语境中的共享指代能唯一指向招牌问候时使用；间接点单可先装作没懂半拍",
                result.get(0).get("semantic_rule"));
        assertEquals("asset://persona-signature/asset12345678",
                ((Map<String, Object>) result.get(0).get("assets")).get("classic"));
    }

    @Test
    void runtimeAssetIsScopedToTheBoundPublishedVersion() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaSignatureServiceImpl service = new PersonaSignatureServiceImpl(dao);
        byte[] audio = "RIFF-test".getBytes(StandardCharsets.UTF_8);
        when(dao.selectRuntimeVersion("agent-1", "persona.rabbit", "v1"))
                .thenReturn(Map.of("version", "v1"));
        when(dao.selectSignatureAsset("asset12345678")).thenReturn(Map.of(
                "assetId", "asset12345678",
                "personaId", "persona.rabbit",
                "version", "v1",
                "contentType", "audio/wav",
                "originalFilename", "ciallo.wav",
                "sha256", "a".repeat(64),
                "audioData", audio));
        SignatureAssetRequest request = new SignatureAssetRequest();
        request.setAgentId("agent-1");
        request.setPersonaId("persona.rabbit");
        request.setVersion("v1");
        request.setAssetId("asset12345678");

        Map<String, Object> result = service.resolveRuntimeAsset(request);

        assertEquals("UklGRi10ZXN0", result.get("audioBase64"));
    }

    @Test
    void signatureChangesInvalidateTheRuntimeArtifactHash() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaSignatureServiceImpl service = new PersonaSignatureServiceImpl(dao);
        String original = "0".repeat(64);
        when(dao.selectSignatureOverrides("persona.rabbit", "v1")).thenReturn(List.of(Map.of(
                "signatureKey", "ciallo",
                "displayText", "Ciallo～(∠・ω< )⌒★",
                "updatedAt", LocalDateTime.of(2026, 8, 24, 12, 0))));
        when(dao.selectSignatureAssets("persona.rabbit", "v1")).thenReturn(List.of(Map.of(
                "assetId", "asset12345678",
                "signatureKey", "ciallo",
                "variant", "classic",
                "contentType", "audio/wav",
                "sha256", "a".repeat(64),
                "updatedAt", LocalDateTime.of(2026, 8, 24, 12, 1))));

        assertNotEquals(original, service.runtimeArtifactHash(original, "persona.rabbit", "v1"));
    }

    @Test
    void runtimeArtifactHashIgnoresDatabaseUpdateTimestamps() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaSignatureServiceImpl service = new PersonaSignatureServiceImpl(dao);
        String original = "0".repeat(64);
        Map<String, Object> override = Map.of(
                "signatureKey", "ciallo",
                "displayText", "Ciallo～(∠・ω< )⌒★");
        when(dao.selectSignatureOverrides("persona.rabbit", "v1")).thenReturn(List.of(new java.util.HashMap<>(override)));
        when(dao.selectSignatureAssets("persona.rabbit", "v1")).thenReturn(List.of());
        dao.selectSignatureOverrides("persona.rabbit", "v1").get(0).put(
                "updatedAt", LocalDateTime.of(2026, 8, 24, 12, 0));
        String first = service.runtimeArtifactHash(original, "persona.rabbit", "v1");

        dao.selectSignatureOverrides("persona.rabbit", "v1").get(0).put(
                "updatedAt", LocalDateTime.of(2026, 8, 25, 12, 0));
        String second = service.runtimeArtifactHash(original, "persona.rabbit", "v1");

        assertEquals(first, second);
    }

    @Test
    void disabledSignatureRemainsManageableButIsRemovedFromRuntime() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaSignatureServiceImpl service = new PersonaSignatureServiceImpl(dao);
        Map<String, Object> signature = Map.of(
                "id", "ciallo",
                "display_text", "Ciallo～",
                "semantic_rule", "明确招牌问候时使用",
                "assets", Map.of());
        when(dao.selectSignatureOverrides("persona.rabbit", "v1")).thenReturn(List.of(Map.of(
                "signatureKey", "ciallo",
                "displayText", "Ciallo～",
                "semanticRule", "明确招牌问候时使用",
                "fallbackMode", "tts",
                "disabled", 1)));
        when(dao.selectSignatureAssets("persona.rabbit", "v1")).thenReturn(List.of());

        List<Map<String, Object>> runtime = service.mergeRuntimeSignatures(
                "persona.rabbit", "v1", Map.of("signature_utterances", List.of(signature)));

        assertEquals(List.of(), runtime);
    }

    @Test
    void skillSignatureCanBeExplicitlyDisabledWithoutDeletingTheSourceRule() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaSignatureServiceImpl service = new PersonaSignatureServiceImpl(dao);
        when(dao.selectPersona(7L, "persona.rabbit")).thenReturn(Map.of("ownerUserId", 7L));
        when(dao.selectVersion(7L, "persona.rabbit", "v1")).thenReturn(Map.of(
                "canonicalSpec", Map.of("signature_utterances", List.of(Map.of(
                        "id", "ciallo",
                        "display_text", "Ciallo～",
                        "semantic_rule", "明确招牌问候时使用",
                        "explicit_aliases", List.of("Ciallo"),
                        "positive_examples", List.of("想听那个了"),
                        "fallback", "tts",
                        "assets", Map.of())))));
        when(dao.selectSignatureOverrides("persona.rabbit", "v1")).thenReturn(List.of());
        when(dao.selectSignatureAssets("persona.rabbit", "v1")).thenReturn(List.of());

        service.setEnabled(7L, "persona.rabbit", "v1", "ciallo", false);

        ArgumentCaptor<Map<String, Object>> override = ArgumentCaptor.forClass(Map.class);
        verify(dao).upsertSignatureOverride(override.capture());
        assertEquals(true, override.getValue().get("disabled"));
        assertEquals("Ciallo～", override.getValue().get("displayText"));
    }

    @Test
    void recompileOnlyCarriesAudioWhenTheSignatureIdAndSpokenTextStillMatch() {
        PersonaDao dao = mock(PersonaDao.class);
        PersonaSignatureServiceImpl service = new PersonaSignatureServiceImpl(dao);
        byte[] audio = "RIFF-ciallo".getBytes(StandardCharsets.UTF_8);
        when(dao.selectPersona(7L, "persona.rabbit")).thenReturn(Map.of("ownerUserId", 7L));
        when(dao.selectVersion(7L, "persona.rabbit", "v1")).thenReturn(Map.of(
                "canonicalSpec", Map.of("signature_utterances", List.of(Map.of(
                        "id", "ciallo",
                        "display_text", "Ciallo～(∠・ω< )⌒★")))));
        when(dao.selectSignatureOverrides("persona.rabbit", "v1")).thenReturn(List.of());
        when(dao.selectSignatureAssets("persona.rabbit", "v1")).thenReturn(List.of(Map.of(
                "assetId", "old-asset",
                "signatureKey", "ciallo",
                "variant", "classic")));
        when(dao.selectSignatureAsset("old-asset")).thenReturn(Map.of(
                "assetId", "old-asset",
                "signatureKey", "ciallo",
                "variant", "classic",
                "contentType", "audio/wav",
                "originalFilename", "ciallo.wav",
                "sha256", "a".repeat(64),
                "audioData", audio));

        int count = service.inheritMatchingAssets(7L, "persona.rabbit", "v1", "v1-r2", Map.of(
                "signature_utterances", List.of(Map.of(
                        "id", "ciallo",
                        "display_text", "Ciallo～(∠・ω< )⌒★"))));

        assertEquals(1, count);
        ArgumentCaptor<Map<String, Object>> asset = ArgumentCaptor.forClass(Map.class);
        verify(dao).upsertSignatureAsset(asset.capture());
        assertEquals("v1-r2", asset.getValue().get("version"));
        assertEquals("ciallo", asset.getValue().get("signatureKey"));
        assertEquals("classic", asset.getValue().get("variant"));
        assertNotEquals("old-asset", asset.getValue().get("id"));
        verify(dao).insertAudit(eq(7L), eq("persona_signature_assets_inherited"), eq("persona_version"),
                eq("persona.rabbit@v1-r2"), anyString());
    }
}
