package xiaozhi.modules.persona.controller;

import java.util.List;
import java.util.Map;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.multipart.MultipartFile;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.persona.dto.PersonaManagementDTO.PublishRequest;
import xiaozhi.modules.persona.dto.PersonaManagementDTO.UrlImportRequest;
import xiaozhi.modules.persona.dto.PersonaManagementDTO.FilesystemMigrationRequest;
import xiaozhi.modules.persona.service.PersonaImportService;
import xiaozhi.modules.persona.service.PersonaGalleryService;
import xiaozhi.modules.persona.service.PersonaManagementService;
import xiaozhi.modules.persona.service.PersonaMigrationService;
import xiaozhi.modules.persona.service.PersonaService;
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

    @PostMapping("/{personaId}/versions/{version}/publish")
    public Result<Void> publish(
            @PathVariable("personaId") String personaId,
            @PathVariable("version") String version,
            @RequestBody(required = false) PublishRequest request) {
        String visibility = request == null ? "private" : request.getVisibility();
        if ("public".equals(visibility)
                && !Integer.valueOf(SuperAdminEnum.YES.value()).equals(SecurityUser.getUser().getSuperAdmin())) {
            throw new RenException("只有超级管理员可以发布全局公开 Persona");
        }
        managementService.publish(SecurityUser.getUserId(), personaId, version, visibility);
        return new Result<Void>().ok(null);
    }

    @PostMapping("/{personaId}/versions/{version}/rollback")
    public Result<Void> rollback(
            @PathVariable("personaId") String personaId,
            @PathVariable("version") String version) {
        managementService.rollback(SecurityUser.getUserId(), personaId, version);
        return new Result<Void>().ok(null);
    }

    @PostMapping("/{personaId}/versions/{version}/archive")
    public Result<Void> archive(
            @PathVariable("personaId") String personaId,
            @PathVariable("version") String version) {
        managementService.archive(SecurityUser.getUserId(), personaId, version);
        return new Result<Void>().ok(null);
    }

    @PostMapping("/{personaId}/versions/{version}/test")
    public Result<Map<String, Object>> rerunTest(
            @PathVariable("personaId") String personaId,
            @PathVariable("version") String version) {
        return new Result<Map<String, Object>>().ok(
                managementService.rerunTest(SecurityUser.getUserId(), personaId, version));
    }

    @GetMapping("/{personaId}/versions/{version}/tests")
    public Result<List<Map<String, Object>>> testRuns(
            @PathVariable("personaId") String personaId,
            @PathVariable("version") String version) {
        return new Result<List<Map<String, Object>>>().ok(
                managementService.testRuns(SecurityUser.getUserId(), personaId, version));
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
