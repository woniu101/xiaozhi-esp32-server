package xiaozhi.modules.timbre.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class IndexTtsPreviewDTO {

    @NotBlank
    @Size(max = 80)
    @Pattern(regexp = "^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    private String voiceId;

    @NotBlank
    @Size(max = 300)
    private String text;
}
