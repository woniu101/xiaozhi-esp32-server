package xiaozhi.modules.characterstyle.entity;

import java.util.Date;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Data
@TableName("ai_character_style")
@Schema(description = "dot-skill 人物风格")
public class CharacterStyleEntity {
    @TableId(type = IdType.INPUT)
    private String id;

    private Long userId;
    private String name;
    private String sourceType;
    private String sourceUrl;
    private String sourceRef;
    private String sourceHash;
    private String rawSkillText;
    private String resolvedPrompt;
    private String signatureConfig;
    private String diagnostics;
    private Date createdAt;
    private Date updatedAt;
}
