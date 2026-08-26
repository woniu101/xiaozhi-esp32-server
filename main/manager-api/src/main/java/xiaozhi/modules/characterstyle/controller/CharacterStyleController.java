package xiaozhi.modules.characterstyle.controller;

import java.io.IOException;
import java.util.List;

import org.apache.commons.lang3.StringUtils;
import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.GitHubImportRequest;
import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.SignatureConfig;
import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.SignatureTrialRequest;
import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.SignatureTrialResult;
import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.Summary;
import xiaozhi.modules.characterstyle.entity.CharacterStyleEntity;
import xiaozhi.modules.characterstyle.service.CharacterStyleService;
import xiaozhi.modules.security.user.SecurityUser;

@Tag(name = "人物风格", description = "dot-skill 人物风格导入、查看与绑定")
@RestController
@RequiredArgsConstructor
@RequestMapping("/character-style")
@RequiresPermissions("sys:role:normal")
public class CharacterStyleController {
    private final CharacterStyleService characterStyleService;

    @GetMapping
    @Operation(summary = "人物风格列表")
    public Result<List<Summary>> list() {
        return new Result<List<Summary>>().ok(characterStyleService.list(currentUserId()));
    }

    @GetMapping("/{styleId}")
    @Operation(summary = "人物风格详情与导入诊断")
    public Result<CharacterStyleEntity> get(@PathVariable String styleId) {
        return new Result<CharacterStyleEntity>().ok(
                characterStyleService.getOwned(currentUserId(), styleId));
    }

    @PostMapping(value = "/import/zip", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(summary = "从 ZIP 新建或原子更新 dot-skill")
    public Result<CharacterStyleEntity> importZip(
            @RequestParam("name") String name,
            @RequestParam(value = "styleId", required = false) String styleId,
            @RequestParam("file") MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new RenException("dot-skill ZIP 不能为空");
        }
        if (file.getSize() > 10L * 1024 * 1024) {
            throw new RenException("dot-skill ZIP 超过 10MB 限制");
        }
        String filename = StringUtils.defaultString(file.getOriginalFilename()).toLowerCase();
        if (!filename.endsWith(".zip")) {
            throw new RenException("只允许上传 ZIP 文件");
        }
        try {
            CharacterStyleEntity value = characterStyleService.importZip(
                    currentUserId(), styleId, name, file.getBytes());
            return new Result<CharacterStyleEntity>().ok(value);
        } catch (IOException error) {
            throw new RenException("dot-skill ZIP 读取失败", error);
        }
    }

    @PostMapping("/import/github")
    @Operation(summary = "从 GitHub 新建或原子更新 dot-skill")
    public Result<CharacterStyleEntity> importGitHub(
            @RequestBody @Valid GitHubImportRequest request) {
        CharacterStyleEntity value = characterStyleService.importGitHub(
                currentUserId(),
                request.getStyleId(),
                request.getName(),
                request.getSourceUrl(),
                request.getSourceRef());
        return new Result<CharacterStyleEntity>().ok(value);
    }

    @PutMapping("/{styleId}/agents/{agentId}")
    @Operation(summary = "为智能体绑定人物风格")
    public Result<Void> bind(@PathVariable String styleId, @PathVariable String agentId) {
        characterStyleService.bind(currentUserId(), agentId, styleId);
        return new Result<Void>().ok(null);
    }

    @DeleteMapping("/agents/{agentId}")
    @Operation(summary = "解除智能体人物风格绑定")
    public Result<Void> unbind(@PathVariable String agentId) {
        characterStyleService.unbind(currentUserId(), agentId);
        return new Result<Void>().ok(null);
    }

    @PutMapping("/{styleId}/signatures")
    @Operation(summary = "保存可选招牌语音开关与表达配置")
    public Result<CharacterStyleEntity> updateSignatures(
            @PathVariable String styleId,
            @RequestBody SignatureConfig signatureConfig) {
        return new Result<CharacterStyleEntity>().ok(
                characterStyleService.updateSignatureConfig(
                        currentUserId(), styleId, signatureConfig));
    }

    @PostMapping("/{styleId}/signatures/trial")
    @Operation(summary = "使用智能体主语言模型试跑人物上下文并诊断招牌录音路由")
    public Result<SignatureTrialResult> trialSignatureContext(
            @PathVariable String styleId,
            @RequestBody @Valid SignatureTrialRequest request) {
        return new Result<SignatureTrialResult>().ok(
                characterStyleService.trialSignatureContext(
                        currentUserId(), styleId, request));
    }

    @PostMapping(
            value = "/{styleId}/signatures/{itemId}/audio",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(summary = "上传或原子替换单条招牌主录音")
    public Result<CharacterStyleEntity> uploadSignatureAudio(
            @PathVariable String styleId,
            @PathVariable String itemId,
            @RequestParam("file") MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new RenException("招牌录音不能为空");
        }
        if (file.getSize() > 5L * 1024 * 1024) {
            throw new RenException("招牌录音超过 5MB 限制");
        }
        String filename = StringUtils.defaultString(file.getOriginalFilename()).toLowerCase();
        if (!filename.endsWith(".wav")) {
            throw new RenException("招牌录音只允许上传 WAV 文件");
        }
        try {
            return new Result<CharacterStyleEntity>().ok(
                    characterStyleService.uploadSignatureAudio(
                            currentUserId(), styleId, itemId, file.getBytes()));
        } catch (IOException error) {
            throw new RenException("招牌录音读取失败", error);
        }
    }

    @DeleteMapping("/{styleId}/signatures/{itemId}/audio")
    @Operation(summary = "删除单条招牌主录音；表达配置继续保留并回退当前 TTS")
    public Result<CharacterStyleEntity> deleteSignatureAudio(
            @PathVariable String styleId, @PathVariable String itemId) {
        return new Result<CharacterStyleEntity>().ok(
                characterStyleService.deleteSignatureAudio(
                        currentUserId(), styleId, itemId));
    }

    @GetMapping(
            value = "/{styleId}/signatures/{itemId}/audio",
            produces = "audio/wav")
    @Operation(summary = "试听招牌主录音")
    public ResponseEntity<byte[]> playSignatureAudio(
            @PathVariable String styleId, @PathVariable String itemId) {
        byte[] audio = characterStyleService.readSignatureAudio(
                currentUserId(), styleId, itemId);
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("audio/wav"))
                .header(HttpHeaders.CONTENT_DISPOSITION, "inline; filename=signature.wav")
                .body(audio);
    }

    @DeleteMapping("/{styleId}")
    @Operation(summary = "删除未被使用的人物风格")
    public Result<Void> delete(@PathVariable String styleId) {
        characterStyleService.delete(currentUserId(), styleId);
        return new Result<Void>().ok(null);
    }

    private Long currentUserId() {
        return SecurityUser.getUser().getId();
    }
}
