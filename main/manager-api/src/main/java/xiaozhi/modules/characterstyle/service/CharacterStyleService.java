package xiaozhi.modules.characterstyle.service;

import java.util.List;

import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.SignatureConfig;
import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.SignatureTrialRequest;
import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.SignatureTrialResult;
import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.Summary;
import xiaozhi.modules.characterstyle.entity.CharacterStyleEntity;

public interface CharacterStyleService {
    List<Summary> list(Long userId);

    CharacterStyleEntity getOwned(Long userId, String styleId);

    CharacterStyleEntity importZip(Long userId, String styleId, String name, byte[] archive);

    CharacterStyleEntity importGitHub(
            Long userId, String styleId, String name, String sourceUrl, String sourceRef);

    void delete(Long userId, String styleId);

    void bind(Long userId, String agentId, String styleId);

    void unbind(Long userId, String agentId);

    CharacterStyleEntity updateSignatureConfig(
            Long userId, String styleId, SignatureConfig signatureConfig);

    CharacterStyleEntity uploadSignatureAudio(
            Long userId, String styleId, String itemId, byte[] audio);

    CharacterStyleEntity deleteSignatureAudio(Long userId, String styleId, String itemId);

    byte[] readSignatureAudio(Long userId, String styleId, String itemId);

    SignatureTrialResult trialSignatureContext(
            Long userId, String styleId, SignatureTrialRequest request);
}
