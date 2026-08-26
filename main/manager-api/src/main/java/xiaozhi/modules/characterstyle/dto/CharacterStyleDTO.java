package xiaozhi.modules.characterstyle.dto;

import java.util.Date;
import java.util.ArrayList;
import java.util.List;

import com.fasterxml.jackson.annotation.JsonProperty;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

public final class CharacterStyleDTO {
    private CharacterStyleDTO() {
    }

    @Data
    @Schema(description = "GitHub dot-skill 导入请求")
    public static class GitHubImportRequest {
        @Schema(description = "更新目标人物风格 ID；为空时新建")
        private String styleId;

        @NotBlank(message = "人物风格名称不能为空")
        private String name;

        @NotBlank(message = "GitHub 地址不能为空")
        private String sourceUrl;

        @Schema(description = "分支、标签或 commit；默认 HEAD")
        private String sourceRef;
    }

    @Data
    @Schema(description = "人物风格列表项")
    public static class Summary {
        private String id;
        private String name;
        private String sourceType;
        private String sourceUrl;
        private String sourceRef;
        private String sourceHash;
        private Date createdAt;
        private Date updatedAt;
    }

    @Data
    @Schema(description = "可选招牌语音配置")
    public static class SignatureConfig {
        @Schema(description = "人物级招牌语音替换总开关")
        private boolean enabled;

        @Schema(description = "零个或多个招牌表达")
        private List<SignatureItem> items = new ArrayList<>();
    }

    @Data
    @Schema(description = "单条招牌表达；每条在 MVP 中只有一段主录音")
    public static class SignatureItem {
        @Schema(description = "人物内稳定 ID，只允许字母、数字、下划线和短横线")
        private String id;

        @JsonProperty("display_text")
        @Schema(description = "模型输出原文；命中后完整消费并用于字幕与失败回退")
        private String displayText;

        @Schema(description = "大小写不敏感的识别别名")
        private List<String> aliases = new ArrayList<>();

        @JsonProperty("audio_path")
        @Schema(description = "服务端生成的相对录音路径；客户端提交值会被忽略")
        private String audioPath;

        @Schema(description = "单条表达启用开关")
        private boolean enabled;
    }

    @Data
    @Schema(description = "人物上下文试跑请求；使用智能体当前主语言模型，不保存对话")
    public static class SignatureTrialRequest {
        @NotBlank(message = "智能体 ID 不能为空")
        private String agentId;

        @NotBlank(message = "试跑输入不能为空")
        @Size(max = 1000, message = "试跑输入不能超过 1000 个字符")
        private String userText;

        @Schema(description = "当前页面中的未保存招牌配置；为空时使用已保存配置")
        private SignatureConfig signatureConfig;
    }

    @Data
    @Schema(description = "人物上下文试跑结果")
    public static class SignatureTrialResult {
        private String modelOutput;
        private List<SignatureTrialMatch> matches = new ArrayList<>();
    }

    @Data
    @Schema(description = "模型输出中的招牌录音路由结果")
    public static class SignatureTrialMatch {
        private String itemId;
        private String matchedText;
        private boolean fixedAudio;
    }
}
