package xiaozhi.modules.timbre.controller;

import java.util.List;
import java.util.Map;

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
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.Parameters;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.AllArgsConstructor;
import xiaozhi.common.constant.Constant;
import xiaozhi.common.page.PageData;
import xiaozhi.common.utils.Result;
import xiaozhi.common.validator.ValidatorUtils;
import xiaozhi.modules.timbre.dto.TimbreDataDTO;
import xiaozhi.modules.timbre.dto.IndexTtsPreviewDTO;
import xiaozhi.modules.timbre.dto.TimbrePageDTO;
import xiaozhi.modules.timbre.service.TimbreService;
import xiaozhi.modules.timbre.vo.TimbreDetailsVO;
import xiaozhi.modules.timbre.vo.IndexTtsVoiceVO;

/**
 * 音色控制层
 *
 * @author zjy
 * @since 2025-3-21
 */
@AllArgsConstructor
@RestController
@RequestMapping("/ttsVoice")
@Tag(name = "音色管理")
public class TimbreController {
    private final TimbreService timbreService;

    @GetMapping
    @Operation(summary = "分页查找")
    @RequiresPermissions("sys:role:superAdmin")
    @Parameters({
            @Parameter(name = "ttsModelId", description = "对应 TTS 模型主键", required = true),
            @Parameter(name = "name", description = "音色名称"),
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true),
    })
    public Result<PageData<TimbreDetailsVO>> page(
            @Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        TimbrePageDTO dto = new TimbrePageDTO();
        dto.setTtsModelId((String) params.get("ttsModelId"));
        dto.setName((String) params.get("name"));
        dto.setLimit((String) params.get(Constant.LIMIT));
        dto.setPage((String) params.get(Constant.PAGE));

        ValidatorUtils.validateEntity(dto);
        PageData<TimbreDetailsVO> page = timbreService.page(dto);
        return new Result<PageData<TimbreDetailsVO>>().ok(page);
    }

    @PostMapping
    @Operation(summary = "音色保存")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> save(@RequestBody TimbreDataDTO dto) {
        ValidatorUtils.validateEntity(dto);
        timbreService.save(dto);
        return new Result<>();
    }

    @PutMapping("/{id}")
    @Operation(summary = "音色修改")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> update(
            @PathVariable String id,
            @RequestBody TimbreDataDTO dto) {
        ValidatorUtils.validateEntity(dto);
        timbreService.update(id, dto);
        return new Result<>();
    }

    @PostMapping("/delete")
    @Operation(summary = "音色删除")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> delete(@RequestBody String[] ids) {
        timbreService.delete(ids);
        return new Result<>();
    }

    @GetMapping("/indexTts/{ttsModelId}/voices")
    @Operation(summary = "读取 IndexTTS2.5 远端音色")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<List<IndexTtsVoiceVO>> getIndexTtsVoices(@PathVariable String ttsModelId) {
        return new Result<List<IndexTtsVoiceVO>>().ok(
                timbreService.getIndexTtsRemoteVoices(ttsModelId));
    }

    @PostMapping("/indexTts/{ttsModelId}/sync")
    @Operation(summary = "同步 IndexTTS2.5 远端音色到本地目录")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<List<IndexTtsVoiceVO>> syncIndexTtsVoices(@PathVariable String ttsModelId) {
        return new Result<List<IndexTtsVoiceVO>>().ok(
                timbreService.syncIndexTtsRemoteVoices(ttsModelId));
    }

    @PostMapping(
            value = "/indexTts/{ttsModelId}/voices",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(summary = "上传并注册 IndexTTS2.5 音色")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<IndexTtsVoiceVO> registerIndexTtsVoice(
            @PathVariable String ttsModelId,
            @RequestParam String voiceId,
            @RequestParam String name,
            @RequestParam(defaultValue = "普通话") String languages,
            @RequestParam(defaultValue = "") String promptText,
            @RequestParam("audio") MultipartFile audio) {
        return new Result<IndexTtsVoiceVO>().ok(
                timbreService.registerIndexTtsVoice(
                        ttsModelId,
                        voiceId,
                        name,
                        languages,
                        promptText,
                        audio));
    }

    @DeleteMapping("/indexTts/{ttsModelId}/voices/{voiceId}")
    @Operation(summary = "删除 IndexTTS2.5 远端音色")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> deleteIndexTtsVoice(
            @PathVariable String ttsModelId,
            @PathVariable String voiceId) {
        timbreService.deleteIndexTtsVoice(ttsModelId, voiceId);
        return new Result<>();
    }

    @PostMapping(
            value = "/indexTts/{ttsModelId}/preview",
            produces = "audio/wav")
    @Operation(summary = "试听 IndexTTS2.5 音色")
    @RequiresPermissions("sys:role:superAdmin")
    public ResponseEntity<byte[]> previewIndexTtsVoice(
            @PathVariable String ttsModelId,
            @RequestBody IndexTtsPreviewDTO dto) {
        ValidatorUtils.validateEntity(dto);
        byte[] audio = timbreService.previewIndexTtsVoice(
                ttsModelId,
                dto.getVoiceId(),
                dto.getText());
        return ResponseEntity.ok()
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .contentType(MediaType.parseMediaType("audio/wav"))
                .body(audio);
    }

}
