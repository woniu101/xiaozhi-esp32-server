package xiaozhi.modules.persona.service;

import java.util.List;
import java.util.Map;

import org.springframework.web.multipart.MultipartFile;

import xiaozhi.modules.persona.dto.PersonaRuntimeDTO.SignatureAssetRequest;

public interface PersonaSignatureService {
    List<Map<String, Object>> list(Long userId, String personaId, String version);

    Map<String, Object> upsertDefinition(
            Long userId, String personaId, String version, String signatureKey,
            Map<String, Object> request);

    void setEnabled(
            Long userId, String personaId, String version, String signatureKey,
            boolean enabled);

    Map<String, Object> uploadAsset(
            Long userId, String personaId, String version, String signatureKey,
            String variant, MultipartFile file);

    Map<String, Object> playback(Long userId, String assetId);

    void deleteAsset(Long userId, String assetId);

    List<Map<String, Object>> mergeRuntimeSignatures(
            String personaId, String version, Map<String, Object> canonicalSpec);

    String runtimeArtifactHash(String artifactHash, String personaId, String version);

    int inheritMatchingAssets(
            Long userId, String personaId, String fromVersion, String toVersion,
            Map<String, Object> newCanonicalSpec);

    Map<String, Object> resolveRuntimeAsset(SignatureAssetRequest request);
}
