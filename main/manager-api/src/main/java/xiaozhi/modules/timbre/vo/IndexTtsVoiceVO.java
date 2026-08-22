package xiaozhi.modules.timbre.vo;

import lombok.Data;

@Data
public class IndexTtsVoiceVO {
    private String localId;
    private String voiceId;
    private String name;
    private String languages;
    private String promptText;
    private Boolean defaultVoice;
    private Boolean synced;
}
