package xiaozhi.modules.agent.controller;

import java.util.List;
import java.util.Map;
import java.util.UUID;

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

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.Parameters;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.AllArgsConstructor;
import xiaozhi.common.constant.Constant;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.page.PageData;
import xiaozhi.common.redis.RedisKeys;
import xiaozhi.common.redis.RedisUtils;
import xiaozhi.common.user.UserDetail;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.common.utils.Result;
import xiaozhi.common.utils.ResultUtils;
import xiaozhi.modules.agent.dto.AgentChatHistoryDTO;
import xiaozhi.modules.agent.dto.AgentChatSessionDTO;
import xiaozhi.modules.agent.dto.AgentCreateDTO;
import xiaozhi.modules.agent.dto.AgentDTO;
import xiaozhi.modules.agent.dto.AgentMemoryDTO;
import xiaozhi.modules.agent.dto.AgentUpdateDTO;
import xiaozhi.modules.agent.entity.AgentEntity;
import xiaozhi.modules.agent.entity.AgentTemplateEntity;
import xiaozhi.modules.agent.dto.AgentTagDTO;
import xiaozhi.modules.agent.entity.AgentTagEntity;
import xiaozhi.modules.agent.service.AgentTagService;
import xiaozhi.modules.agent.service.AgentChatAudioService;
import xiaozhi.modules.agent.service.AgentChatHistoryService;
import xiaozhi.modules.agent.service.AgentChatSummaryService;
import xiaozhi.modules.agent.service.AgentService;
import xiaozhi.modules.agent.service.AgentTemplateService;
import xiaozhi.modules.agent.vo.AgentChatHistoryUserVO;
import xiaozhi.modules.agent.vo.AgentInfoVO;
import xiaozhi.modules.security.user.SecurityUser;
import xiaozhi.modules.config.service.CompanionRuntimeService;
import xiaozhi.modules.config.dto.CompanionRuntimeDTO.MemoryUpdateRequest;

@Tag(name = "智能体管理")
@AllArgsConstructor
@RestController
@RequestMapping("/agent")
public class AgentController {
    private static final long AUDIO_PLAY_TOKEN_EXPIRE_SECONDS = 300L;

    private final AgentService agentService;
    private final AgentTemplateService agentTemplateService;
    private final AgentChatHistoryService agentChatHistoryService;
    private final AgentChatAudioService agentChatAudioService;
    private final AgentChatSummaryService agentChatSummaryService;
    private final RedisUtils redisUtils;
    private final AgentTagService agentTagService;
    private final CompanionRuntimeService companionRuntimeService;

    private void requireAgentPermission(String agentId) {
        if (!agentService.checkAgentPermission(agentId, SecurityUser.getUserId())) {
            throw new RenException(ErrorCode.NO_PERMISSION);
        }
    }

    private String requireSessionAgent(String sessionId) {
        String agentId = agentChatHistoryService.getAgentIdBySessionId(sessionId);
        if (StringUtils.isBlank(agentId)) {
            throw new RenException(ErrorCode.AGENT_NOT_FOUND);
        }
        agentService.getAgentById(agentId);
        return agentId;
    }

    private String requireAudioPermission(String audioId) {
        String agentId = agentChatHistoryService.getAgentIdByAudioId(audioId);
        if (StringUtils.isBlank(agentId)) {
            throw new RenException(ErrorCode.NO_PERMISSION);
        }
        requireAgentPermission(agentId);
        return agentId;
    }

    @GetMapping("/list")
    @Operation(summary = "获取用户智能体列表")
    @RequiresPermissions("sys:role:normal")
    public Result<List<AgentDTO>> getUserAgents(
            @RequestParam(value = "keyword", required = false) String keyword,
            @RequestParam(value = "searchType", defaultValue = "name") String searchType) {
        UserDetail user = SecurityUser.getUser();

        // 直接调用整合后的getUserAgents方法，无需再区分搜索和普通查询
        List<AgentDTO> agents = agentService.getUserAgents(user.getId(), keyword, searchType);
        return new Result<List<AgentDTO>>().ok(agents);
    }

    @GetMapping("/all")
    @Operation(summary = "智能体列表（管理员）")
    @RequiresPermissions("sys:role:superAdmin")
    @Parameters({
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true),
    })
    public Result<PageData<AgentEntity>> adminAgentList(
            @Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        PageData<AgentEntity> page = agentService.adminAgentList(params);
        return new Result<PageData<AgentEntity>>().ok(page);
    }

    @GetMapping("/{id}")
    @Operation(summary = "获取智能体详情")
    @RequiresPermissions("sys:role:normal")
    public Result<AgentInfoVO> getAgentById(@PathVariable("id") String id) {
        AgentInfoVO agent = agentService.getAgentById(id, SecurityUser.getUserId());
        return ResultUtils.success(agent);
    }

    @PostMapping
    @Operation(summary = "创建智能体")
    @RequiresPermissions("sys:role:normal")
    public Result<String> save(@RequestBody @Valid AgentCreateDTO dto) {
        String agentId = agentService.createAgent(dto);
        return new Result<String>().ok(agentId);
    }

    @PutMapping("/saveMemory/{macAddress}")
    @Operation(summary = "根据设备id更新智能体")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> updateByDeviceId(@PathVariable("macAddress") String macAddress, @RequestBody @Valid AgentMemoryDTO dto) {
        agentService.updateAgentMemoryByDeviceMacAddress(macAddress, dto, SecurityUser.getUserId());
        return new Result<Void>().ok(null);
    }

    @PostMapping("/chat-summary/{sessionId}/save")
    @Operation(summary = "根据会话ID生成聊天记录总结并保存（异步执行）")
    public Result<Void> generateAndSaveChatSummary(@PathVariable("sessionId") String sessionId) {
        requireSessionAgent(sessionId);
        try {
            // 异步执行总结生成任务，立即返回成功响应
            new Thread(() -> {
                try {
                    agentChatSummaryService.generateAndSaveChatSummary(sessionId);
                    System.out.println("异步执行会话 " + sessionId + " 的聊天记录总结完成");
                } catch (Exception e) {
                    System.err.println("异步执行会话 " + sessionId + " 的聊天记录总结失败: " + e.getMessage());
                }
            }).start();

            // 立即返回成功响应，不等待总结生成完成
            return new Result<Void>().ok(null);
        } catch (Exception e) {
            return new Result<Void>().error("启动异步总结生成任务失败: " + e.getMessage());
        }
    }

    @PostMapping("/chat-title/{sessionId}/generate")
    @Operation(summary = "根据会话ID生成聊天标题")
    public Result<Void> generateAndSaveChatTitle(@PathVariable("sessionId") String sessionId) {
        requireSessionAgent(sessionId);
        agentChatSummaryService.generateAndSaveChatTitle(sessionId);
        return new Result<Void>().ok(null);
    }

    @PutMapping("/{id}")
    @Operation(summary = "更新智能体")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> update(@PathVariable("id") String id, @RequestBody @Valid AgentUpdateDTO dto) {
        agentService.updateAgentById(id, dto, SecurityUser.getUserId());
        return new Result<>();
    }

    @GetMapping("/{id}/companion/summary")
    @Operation(summary = "获取 Companion 非敏感状态摘要")
    @RequiresPermissions("sys:role:normal")
    public Result<Map<String, Object>> getCompanionSummary(@PathVariable("id") String id) {
        requireAgentPermission(id);
        AgentInfoVO agent = agentService.getAgentById(id);
        if (StringUtils.isBlank(agent.getPersonaId())) {
            return new Result<Map<String, Object>>().ok(Map.of(
                    "stage", "familiar",
                    "meaningfulTurns", 0,
                    "sharedEventCount", 0,
                    "revision", 0,
                    "memoryCount", 0,
                    "personaId", ""));
        }
        return new Result<Map<String, Object>>().ok(
                companionRuntimeService.getSummary(
                        String.valueOf(agent.getUserId()), id, agent.getPersonaId()));
    }

    @GetMapping("/{id}/companion/diagnostic")
    @Operation(summary = "获取 Companion 最近一轮非敏感诊断")
    @RequiresPermissions("sys:role:normal")
    public Result<Map<String, Object>> getCompanionDiagnostic(@PathVariable("id") String id) {
        requireAgentPermission(id);
        AgentInfoVO agent = agentService.getAgentById(id);
        if (StringUtils.isBlank(agent.getPersonaId())) {
            return new Result<Map<String, Object>>().ok(Map.of());
        }
        return new Result<Map<String, Object>>().ok(
                companionRuntimeService.getLatestDiagnostic(
                        String.valueOf(agent.getUserId()), id, agent.getPersonaId()));
    }

    @GetMapping("/{id}/companion/memories")
    @Operation(summary = "查看当前 Persona 的 Companion 记忆")
    @RequiresPermissions("sys:role:normal")
    public Result<List<Map<String, Object>>> getCompanionMemories(
            @PathVariable("id") String id,
            @RequestParam(value = "limit", defaultValue = "200") int limit) {
        requireAgentPermission(id);
        AgentInfoVO agent = agentService.getAgentById(id);
        if (StringUtils.isBlank(agent.getPersonaId())) {
            return new Result<List<Map<String, Object>>>().ok(List.of());
        }
        return new Result<List<Map<String, Object>>>().ok(
                companionRuntimeService.getManagedMemories(
                        String.valueOf(agent.getUserId()), id, agent.getPersonaId(), limit));
    }

    @PutMapping("/{id}/companion/memories/{memoryId}")
    @Operation(summary = "编辑当前 Persona 的 Companion 记忆")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> updateCompanionMemory(
            @PathVariable("id") String id,
            @PathVariable("memoryId") Long memoryId,
            @RequestBody @Valid MemoryUpdateRequest request) {
        requireAgentPermission(id);
        AgentInfoVO agent = agentService.getAgentById(id);
        if (StringUtils.isBlank(agent.getPersonaId())) {
            throw new RenException(ErrorCode.RESOURCE_NOT_FOUND);
        }
        companionRuntimeService.updateMemory(
                String.valueOf(agent.getUserId()), id, agent.getPersonaId(), memoryId,
                request, SecurityUser.getUserId());
        return new Result<Void>().ok(null);
    }

    @DeleteMapping("/{id}/companion/memories/{memoryId}")
    @Operation(summary = "删除当前 Persona 的 Companion 记忆")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> deleteCompanionMemory(
            @PathVariable("id") String id,
            @PathVariable("memoryId") Long memoryId) {
        requireAgentPermission(id);
        AgentInfoVO agent = agentService.getAgentById(id);
        if (StringUtils.isBlank(agent.getPersonaId())) {
            throw new RenException(ErrorCode.RESOURCE_NOT_FOUND);
        }
        companionRuntimeService.deleteMemory(
                String.valueOf(agent.getUserId()), id, agent.getPersonaId(), memoryId,
                SecurityUser.getUserId());
        return new Result<Void>().ok(null);
    }

    @DeleteMapping("/{id}/companion/state")
    @Operation(summary = "重置 Companion 状态和记忆")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> resetCompanionState(
            @PathVariable("id") String id,
            @RequestParam("confirmAgentId") String confirmAgentId) {
        requireAgentPermission(id);
        if (!id.equals(confirmAgentId)) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        Long operatorUserId = SecurityUser.getUserId();
        AgentInfoVO agent = agentService.getAgentById(id);
        if (StringUtils.isNotBlank(agent.getPersonaId())) {
            companionRuntimeService.reset(
                    String.valueOf(agent.getUserId()), id, agent.getPersonaId(), operatorUserId);
        }
        return new Result<Void>().ok(null);
    }

    @DeleteMapping("/{id}/companion/relationship")
    @Operation(summary = "仅重置 Companion 关系状态，保留人物记忆")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> resetCompanionRelationship(
            @PathVariable("id") String id,
            @RequestParam("confirmAgentId") String confirmAgentId) {
        requireAgentPermission(id);
        if (!id.equals(confirmAgentId)) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        AgentInfoVO agent = agentService.getAgentById(id);
        if (StringUtils.isNotBlank(agent.getPersonaId())) {
            companionRuntimeService.resetRelationship(
                    String.valueOf(agent.getUserId()), id, agent.getPersonaId(), SecurityUser.getUserId());
        }
        return new Result<Void>().ok(null);
    }

    @DeleteMapping("/{id}/legacy-memory")
    @Operation(summary = "显式清除旧版记忆摘要和聊天记录")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> clearLegacyMemory(
            @PathVariable("id") String id,
            @RequestParam("confirmAgentId") String confirmAgentId) {
        requireAgentPermission(id);
        if (!id.equals(confirmAgentId)) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        agentService.clearLegacyMemory(id, SecurityUser.getUserId());
        return new Result<Void>().ok(null);
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "删除智能体")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> delete(@PathVariable("id") String id) {
        agentService.deleteAgentById(id, SecurityUser.getUserId());
        return new Result<>();
    }

    @GetMapping("/template")
    @Operation(summary = "智能体模板模板列表")
    @RequiresPermissions("sys:role:normal")
    public Result<List<AgentTemplateEntity>> templateList() {
        List<AgentTemplateEntity> list = agentTemplateService
                .list(new QueryWrapper<AgentTemplateEntity>().orderByAsc("sort"));
        return new Result<List<AgentTemplateEntity>>().ok(list);
    }

    @GetMapping("/{id}/sessions")
    @Operation(summary = "获取智能体会话列表")
    @RequiresPermissions("sys:role:normal")
    @Parameters({
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true),
    })
    public Result<PageData<AgentChatSessionDTO>> getAgentSessions(
            @PathVariable("id") String id,
            @Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        requireAgentPermission(id);
        params.put("agentId", id);
        PageData<AgentChatSessionDTO> page = agentChatHistoryService.getSessionListByAgentId(params);
        return new Result<PageData<AgentChatSessionDTO>>().ok(page);
    }

    @GetMapping("/{id}/chat-history/{sessionId}")
    @Operation(summary = "获取智能体聊天记录")
    @RequiresPermissions("sys:role:normal")
    public Result<List<AgentChatHistoryDTO>> getAgentChatHistory(
            @PathVariable("id") String id,
            @PathVariable("sessionId") String sessionId) {
        // 获取当前用户
        UserDetail user = SecurityUser.getUser();

        // 检查权限
        if (!agentService.checkAgentPermission(id, user.getId())) {
            return new Result<List<AgentChatHistoryDTO>>().error("没有权限查看该智能体的聊天记录");
        }

        // 查询聊天记录
        List<AgentChatHistoryDTO> result = agentChatHistoryService.getChatHistoryBySessionId(id, sessionId);
        return new Result<List<AgentChatHistoryDTO>>().ok(result);
    }

    @GetMapping("/{id}/chat-history/user")
    @Operation(summary = "获取智能体聊天记录（用户）")
    @RequiresPermissions("sys:role:normal")
    public Result<List<AgentChatHistoryUserVO>> getRecentlyFiftyByAgentId(
            @PathVariable("id") String id) {
        // 获取当前用户
        UserDetail user = SecurityUser.getUser();

        // 检查权限
        if (!agentService.checkAgentPermission(id, user.getId())) {
            return new Result<List<AgentChatHistoryUserVO>>().error("没有权限查看该智能体的聊天记录");
        }

        // 查询聊天记录
        List<AgentChatHistoryUserVO> data = agentChatHistoryService.getRecentlyFiftyByAgentId(id);
        return new Result<List<AgentChatHistoryUserVO>>().ok(data);
    }

    @GetMapping("/{id}/chat-history/audio")
    @Operation(summary = "获取音频内容")
    @RequiresPermissions("sys:role:normal")
    public Result<String> getContentByAudioId(
            @PathVariable("id") String id) {
        requireAudioPermission(id);
        // 查询聊天记录
        String data = agentChatHistoryService.getContentByAudioId(id);
        return new Result<String>().ok(data);
    }

    @PostMapping("/audio/{audioId}")
    @Operation(summary = "获取音频下载ID")
    @RequiresPermissions("sys:role:normal")
    public Result<String> getAudioId(@PathVariable("audioId") String audioId) {
        requireAudioPermission(audioId);
        byte[] audioData = agentChatAudioService.getAudio(audioId);
        if (audioData == null) {
            return new Result<String>().error("音频不存在");
        }
        String uuid = UUID.randomUUID().toString();
        redisUtils.set(RedisKeys.getAgentAudioIdKey(uuid), audioId, AUDIO_PLAY_TOKEN_EXPIRE_SECONDS);
        return new Result<String>().ok(uuid);
    }

    @GetMapping("/play/{uuid}")
    @Operation(summary = "播放音频")
    public ResponseEntity<byte[]> playAudio(@PathVariable("uuid") String uuid) {

        String audioId = (String) redisUtils.get(RedisKeys.getAgentAudioIdKey(uuid));
        if (StringUtils.isBlank(audioId)) {
            return ResponseEntity.notFound().build();
        }

        byte[] audioData = agentChatAudioService.getAudio(audioId);
        if (audioData == null) {
            return ResponseEntity.notFound().build();
        }
        redisUtils.delete(RedisKeys.getAgentAudioIdKey(uuid));
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"play.wav\"")
                .body(audioData);
    }

    @PostMapping("/tag")
    @Operation(summary = "创建标签")
    @RequiresPermissions("sys:role:normal")
    public Result<AgentTagEntity> createTag(@RequestBody Map<String, String> params) {
        String tagName = params.get("tagName");
        if (StringUtils.isBlank(tagName)) {
            return new Result<AgentTagEntity>().error("标签名称不能为空");
        }
        AgentTagEntity tag = agentTagService.saveTag(tagName);
        return new Result<AgentTagEntity>().ok(tag);
    }

    @GetMapping("/tag/list")
    @Operation(summary = "获取所有标签列表")
    @RequiresPermissions("sys:role:normal")
    public Result<List<AgentTagDTO>> getAllTags() {
        List<AgentTagDTO> tags = agentTagService.getAllTags();
        return new Result<List<AgentTagDTO>>().ok(tags);
    }

    @DeleteMapping("/tag/{id}")
    @Operation(summary = "删除标签")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> deleteTag(@PathVariable("id") String id) {
        agentTagService.deleteTag(id);
        return new Result<Void>().ok(null);
    }

    @GetMapping("/{id}/tags")
    @Operation(summary = "获取智能体的标签")
    @RequiresPermissions("sys:role:normal")
    public Result<List<AgentTagDTO>> getAgentTags(@PathVariable("id") String id) {
        requireAgentPermission(id);
        List<AgentTagDTO> tags = agentTagService.getTagsByAgentId(id);
        return new Result<List<AgentTagDTO>>().ok(tags);
    }

    @PutMapping("/{id}/tags")
    @Operation(summary = "保存智能体的标签")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> saveAgentTags(@PathVariable("id") String id, @RequestBody Map<String, Object> params) {
        requireAgentPermission(id);
        List<String> tagIds = JsonUtils.toList(params.get("tagIds"), String.class);
        List<String> tagNames = JsonUtils.toList(params.get("tagNames"), String.class);
        AgentUpdateDTO dto = new AgentUpdateDTO();
        dto.setTagIds(tagIds);
        dto.setTagNames(tagNames);
        agentService.updateAgentById(id, dto);
        return new Result<Void>().ok(null);
    }

}
