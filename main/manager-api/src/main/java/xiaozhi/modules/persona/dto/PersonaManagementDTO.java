package xiaozhi.modules.persona.dto;

import java.util.Map;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

public final class PersonaManagementDTO {
    private PersonaManagementDTO() {
    }

    @Data
    public static class UrlImportRequest {
        @NotBlank
        private String url;
        private String ref;
    }

    @Data
    public static class PublishRequest {
        private String visibility = "private";
    }

    @Data
    public static class TestRequest {
        @NotNull
        private Map<String, Object> canonicalSpec;
        @NotBlank
        private String runtimePrompt;
    }

    @Data
    public static class FilesystemMigrationRequest {
        @NotBlank
        private String personaId;
        @NotBlank
        private String version;
        @NotBlank
        private String artifactHash;
        @NotNull
        private Map<String, Object> canonicalSpec;
        @NotBlank
        private String runtimePrompt;
        @NotNull
        private Map<String, Object> validationReport;
        private String sourceStatus = "draft";
    }
}
