package xiaozhi.modules.persona.controller;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ContentDisposition;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.web.multipart.MultipartFile;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.persona.dto.PersonaManagementDTO.RecompileRequest;
import xiaozhi.modules.persona.dto.PersonaManagementDTO.UrlImportRequest;
import xiaozhi.modules.persona.dto.PersonaManagementDTO.FilesystemMigrationRequest;
import xiaozhi.modules.persona.dto.PersonaManagementDTO.ConversationTestRequest;
import xiaozhi.modules.persona.service.PersonaImportService;
import xiaozhi.modules.persona.service.PersonaGalleryService;
import xiaozhi.modules.persona.service.PersonaManagementService;
import xiaozhi.modules.persona.service.PersonaMigrationService;
import xiaozhi.modules.persona.service.PersonaService;
import xiaozhi.modules.persona.service.PersonaSignatureService;
import xiaozhi.modules.security.user.SecurityUser;
import xiaozhi.modules.sys.enums.SuperAdminEnum;

@Tag(name = "Persona 人物库")
@RestController
@RequiredArgsConstructor
@RequestMapping("/persona")
@RequiresPermissions("sys:role:normal")
public class PersonaController {
    private final PersonaImportService importService;
    private final PersonaManagementService managementService;
    private final PersonaService personaService;
    private final PersonaGalleryService galleryService;
    private final PersonaMigrationService migrationService;
    private final PersonaSignatureService signatureService;

    @GetMapping("/gallery")
    @Operation(summary = "浏览在线 Persona 画廊")
    public Result<List<Map<String, Object>>> gallery(
            @RequestParam(value = "keyword", required = false) String keyword) {
        return new Result<List<Map<String, Object>>>().ok(galleryService.list(keyword));
    }

    @GetMapping("/gallery/{provider}/{externalId}")
    @Operation(summary = "查看 Persona 画廊条目")
    public Result<Map<String, Object>> galleryDetail(
            @PathVariable("provider") String provider,
            @PathVariable("externalId") String externalId) {
        return new Result<Map<String, Object>>().ok(galleryService.detail(provider, externalId));
    }

    @PostMapping("/gallery/refresh")
    @Operation(summary = "刷新在线 Persona 画廊")
    public Result<List<Map<String, Object>>> refreshGallery() {
        if (!Integer.valueOf(SuperAdminEnum.YES.value()).equals(SecurityUser.getUser().getSuperAdmin())) {
            throw new RenException("只有超级管理员可以刷新 Persona 画廊");
        }
        return new Result<List<Map<String, Object>>>().ok(galleryService.refresh());
    }

    @GetMapping
    @Operation(summary = "列出可见 Persona")
    public Result<List<Map<String, Object>>> list() {
        return new Result<List<Map<String, Object>>>().ok(managementService.list(SecurityUser.getUserId()));
    }

    @GetMapping("/options")
    @Operation(summary = "列出可绑定的已发布 Persona")
    public Result<List<Map<String, Object>>> options() {
        return new Result<List<Map<String, Object>>>().ok(personaService.listBindable(SecurityUser.getUserId()));
    }

    @GetMapping("/{personaId}")
    public Result<Map<String, Object>> get(@PathVariable("personaId") String personaId) {
        return new Result<Map<String, Object>>().ok(managementService.get(SecurityUser.getUserId(), personaId));
    }

    @GetMapping("/{personaId}/versions")
    public Result<List<Map<String, Object>>> versions(@PathVariable("personaId") String personaId) {
        return new Result<List<Map<String, Object>>>().ok(
                managementService.versions(SecurityUser.getUserId(), personaId));
    }

    @GetMapping("/{personaId}/versions/{version}")
    public Result<Map<String, Object>> version(
            @PathVariable("personaId") String personaId,
            @PathVariable("version") String version) {
        return new Result<Map<String, Object>>().ok(
                managementService.version(SecurityUser.getUserId(), personaId, version));
    }

    @GetMapping("/{personaId}/diff")
    public Result<Map<String, Object>> diff(
            @PathVariable("personaId") String personaId,
            @RequestParam("from") String from,
            @RequestParam("to") String to) {
        return new Result<Map<String, Object>>().ok(
                managementService.diff(SecurityUser.getUserId(), personaId, from, to));
    }

    @PostMapping("/import/url")
    @Operation(summary = "从 GitHub URL 创建 Persona 导入任务")
    public Result<String> importUrl(@Valid @RequestBody UrlImportRequest request) {
        return new Result<String>().ok(importService.createUrl(SecurityUser.getUserId(), request));
    }

    @PostMapping("/import/upload")
    @Operation(summary = "上传 dot-skill ZIP 并创建 Persona 导入任务")
    public Result<String> importUpload(@RequestParam("file") MultipartFile file) {
        return new Result<String>().ok(importService.createUpload(SecurityUser.getUserId(), file));
    }

    @PostMapping("/{personaId}/upgrade/source")
    @Operation(summary = "从原 GitHub 来源创建受目标 Persona 保护的升级任务")
    public Result<String> upgradeFromSource(@PathVariable("personaId") String personaId) {
        return new Result<String>().ok(
                importService.createUpgradeFromSource(SecurityUser.getUserId(), personaId));
    }

    @PostMapping("/{personaId}/upgrade/upload")
    @Operation(summary = "上传新版 ZIP 并校验其 Persona ID")
    public Result<String> upgradeUpload(
            @PathVariable("personaId") String personaId,
            @RequestParam("file") MultipartFile file) {
        return new Result<String>().ok(
                importService.createUpgradeUpload(SecurityUser.getUserId(), personaId, file));
    }

    @PostMapping("/{personaId}/versions/{version}/recompile")
    @Operation(summary = "使用当前编译器重新解析历史 Persona 版本")
    public Result<String> recompile(
            @PathVariable("personaId") String personaId,
            @PathVariable("version") String version,
            @RequestBody(required = false) RecompileRequest request) {
        boolean inheritAudio = request == null || request.isInheritSignatureAudio();
        return new Result<String>().ok(importService.createRecompile(
                SecurityUser.getUserId(), personaId, version, inheritAudio));
    }

    @PostMapping("/{personaId}/versions/{version}/recompile/upload")
    @Operation(summary = "上传历史源码快照并使用当前编译器重新解析")
    public Result<String> recompileUpload(
            @PathVariable("personaId") String personaId,
            @PathVariable("version") String version,
            @RequestParam(value = "inheritSignatureAudio", defaultValue = "true") boolean inheritSignatureAudio,
            @RequestParam("file") MultipartFile file) {
        return new Result<String>().ok(importService.createRecompileUpload(
                SecurityUser.getUserId(), personaId, version, inheritSignatureAudio, file));
    }

    @GetMapping("/import/jobs/{jobId}")
    public Result<Map<String, Object>> importJob(@PathVariable("jobId") String jobId) {
        return new Result<Map<String, Object>>().ok(importService.getJob(SecurityUser.getUserId(), jobId));
    }

    @PostMapping("/import/jobs/{jobId}/cancel")
    public Result<Void> cancelImport(@PathVariable("jobId") String jobId) {
        importService.cancel(SecurityUser.getUserId(), jobId);
        return new Result<Void>().ok(null);
    }

    @PostMapping("/migrate/filesystem")
    @Operation(summary = "迁移一个 FilesystemPersonaRegistry 版本")
    public Result<Map<String, Object>> migrateFilesystem(@Valid @RequestBody FilesystemMigrationRequest request) {
        return new Result<Map<String, Object>>().ok(migrationService.migrate(SecurityUser.getUserId(), request));
    }

    @PostMapping("/{personaId}/versions/{version}/apply")
    @Operation(summary = "应用已通过测试的人物更新")
    public Result<Void> applyUpdate(
            @PathVariable("personaId") String personaId,
            @PathVariable("version") String version) {
        managementService.applyUpdate(SecurityUser.getUserId(), personaId, version);
        return new Result<Void>().ok(null);
    }

    @PostMapping("/{personaId}/restore-previous")
    @Operation(summary = "恢复人物上一版")
    public Result<Void> restorePrevious(@PathVariable("personaId") String personaId) {
        managementService.restorePrevious(SecurityUser.getUserId(), personaId);
        return new Result<Void>().ok(null);
    }

    @GetMapping("/{personaId}/usage")
    @Operation(summary = "查询 Persona 的智能体绑定占用")
    public Result<Map<String, Object>> usage(@PathVariable("personaId") String personaId) {
        return new Result<Map<String, Object>>().ok(
                managementService.usage(SecurityUser.getUserId(), personaId));
    }

    @DeleteMapping("/{personaId}")
    @Operation(summary = "永久删除人物、自动解绑并清除其全部数据")
    public Result<Void> delete(
            @PathVariable("personaId") String personaId,
            @RequestParam("confirmation") String confirmation) {
        managementService.delete(SecurityUser.getUserId(), personaId, confirmation);
        return new Result<Void>().ok(null);
    }

    @PostMapping("/{personaId}/versions/{version}/test")
    public Result<Map<String, Object>> rerunTest(
            @PathVariable("personaId") String personaId,
            @PathVariable("version") String version,
            @RequestBody(required = false) ConversationTestRequest request) {
        return new Result<Map<String, Object>>().ok(
                managementService.rerunTest(
                        SecurityUser.getUserId(), personaId, version,
                        request == null ? List.of() : request.getConversationSamples()));
    }

    @GetMapping("/{personaId}/versions/{version}/tests")
    public Result<List<Map<String, Object>>> testRuns(
            @PathVariable("personaId") String personaId,
            @PathVariable("version") String version) {
        return new Result<List<Map<String, Object>>>().ok(
                managementService.testRuns(SecurityUser.getUserId(), personaId, version));
    }

    @GetMapping("/{personaId}/versions/{version}/signatures")
    @Operation(summary = "列出人物版本的招牌表达和语音资产")
    public Result<List<Map<String, Object>>> signatures(
            @PathVariable("personaId") String personaId,
            @PathVariable("version") String version) {
        return new Result<List<Map<String, Object>>>().ok(
                signatureService.list(SecurityUser.getUserId(), personaId, version));
    }

    @PostMapping("/{personaId}/versions/{version}/signatures/{signatureKey}")
    @Operation(summary = "新增或覆盖招牌表达定义")
    public Result<Map<String, Object>> upsertSignature(
            @PathVariable("personaId") String personaId,
            @PathVariable("version") String version,
            @PathVariable("signatureKey") String signatureKey,
            @RequestBody Map<String, Object> request) {
        return new Result<Map<String, Object>>().ok(signatureService.upsertDefinition(
                SecurityUser.getUserId(), personaId, version, signatureKey, request));
    }

    @PostMapping("/{personaId}/versions/{version}/signatures/{signatureKey}/enabled")
    @Operation(summary = "启用或禁用一条招牌表达")
    public Result<Void> setSignatureEnabled(
            @PathVariable("personaId") String personaId,
            @PathVariable("version") String version,
            @PathVariable("signatureKey") String signatureKey,
            @RequestBody Map<String, Object> request) {
        boolean enabled = request != null && Boolean.TRUE.equals(request.get("enabled"));
        signatureService.setEnabled(
                SecurityUser.getUserId(), personaId, version, signatureKey, enabled);
        return new Result<Void>().ok(null);
    }

    @PostMapping("/{personaId}/versions/{version}/signatures/{signatureKey}/assets/{variant}")
    @Operation(summary = "上传或替换招牌语音变体")
    public Result<Map<String, Object>> uploadSignatureAsset(
            @PathVariable("personaId") String personaId,
            @PathVariable("version") String version,
            @PathVariable("signatureKey") String signatureKey,
            @PathVariable("variant") String variant,
            @RequestParam("file") MultipartFile file) {
        return new Result<Map<String, Object>>().ok(signatureService.uploadAsset(
                SecurityUser.getUserId(), personaId, version, signatureKey, variant, file));
    }

    @GetMapping("/signature-assets/{assetId}/play")
    @Operation(summary = "试听招牌语音")
    public ResponseEntity<byte[]> playSignatureAsset(@PathVariable("assetId") String assetId) {
        Map<String, Object> asset = signatureService.playback(SecurityUser.getUserId(), assetId);
        byte[] audio = (byte[]) asset.get("audioData");
        MediaType mediaType;
        try {
            mediaType = MediaType.parseMediaType(String.valueOf(asset.get("contentType")));
        } catch (Exception ignored) {
            mediaType = MediaType.APPLICATION_OCTET_STREAM;
        }
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(mediaType);
        headers.setContentLength(audio.length);
        headers.setContentDisposition(ContentDisposition.inline()
                .filename(String.valueOf(asset.get("originalFilename")), StandardCharsets.UTF_8)
                .build());
        return new ResponseEntity<>(audio, headers, HttpStatus.OK);
    }

    @DeleteMapping("/signature-assets/{assetId}")
    @Operation(summary = "删除招牌语音变体")
    public Result<Void> deleteSignatureAsset(@PathVariable("assetId") String assetId) {
        signatureService.deleteAsset(SecurityUser.getUserId(), assetId);
        return new Result<Void>().ok(null);
    }

    @GetMapping("/{personaId}/versions/{version}/export")
    public ResponseEntity<byte[]> exportVersion(
            @PathVariable("personaId") String personaId,
            @PathVariable("version") String version) {
        byte[] value = managementService.exportFilesystemPackage(SecurityUser.getUserId(), personaId, version);
        String filename = (personaId + "-" + version).replaceAll("[^A-Za-z0-9._-]", "_") + ".zip";
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + filename + "\"")
                .body(value);
    }

    @GetMapping("/{personaId}/audit")
    public Result<List<Map<String, Object>>> auditTrail(@PathVariable("personaId") String personaId) {
        return new Result<List<Map<String, Object>>>().ok(
                managementService.auditTrail(SecurityUser.getUserId(), personaId));
    }

}
