package xiaozhi.modules.config.dto;

import java.util.List;
import java.util.Map;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;
import lombok.EqualsAndHashCode;

public final class CompanionRuntimeDTO {
    private CompanionRuntimeDTO() {
    }

    @Data
    public static class IdentityRequest {
        @NotBlank
        private String userId;
        @NotBlank
        private String agentId;
        @NotBlank
        private String personaId;
    }

    @Data
    @EqualsAndHashCode(callSuper = true)
    public static class CommitRequest extends IdentityRequest {
        @NotBlank
        private String turnId;
        @NotNull
        private Long expectedRevision;
        @NotNull
        private Map<String, Object> state;
        private List<EventItem> events;
        private List<MemoryItem> memories;
        private Map<String, Object> diagnostic;
    }

    @Data
    public static class EventItem {
        @NotBlank
        private String eventType;
        @NotNull
        private Double confidence;
        private Map<String, Object> payload;
    }

    @Data
    public static class MemoryItem {
        @NotBlank
        private String memoryType;
        private String subjectKey;
        @NotBlank
        private String content;
        @NotNull
        private Double importance;
        @NotNull
        private Double confidence;
        private String sensitivity;
        private String occurredAt;
        private String expiresAt;
        private String operation;
    }

    @Data
    public static class MemoryUpdateRequest {
        @NotBlank
        private String content;
        @Min(0)
        @Max(1)
        private Double importance;
        private String expiresAt;
    }

    @Data
    @EqualsAndHashCode(callSuper = true)
    public static class MemorySearchRequest extends IdentityRequest {
        private String query;
        @Min(1)
        @Max(100)
        private Integer limit = 100;
    }
}
