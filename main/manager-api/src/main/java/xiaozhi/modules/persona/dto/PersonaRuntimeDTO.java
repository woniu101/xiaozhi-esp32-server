package xiaozhi.modules.persona.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

public final class PersonaRuntimeDTO {
    private PersonaRuntimeDTO() {
    }

    @Data
    public static class ResolveRequest {
        @NotBlank
        private String agentId;
        @NotBlank
        private String personaId;
        private String version;
        private String knownArtifactHash;
    }
}
