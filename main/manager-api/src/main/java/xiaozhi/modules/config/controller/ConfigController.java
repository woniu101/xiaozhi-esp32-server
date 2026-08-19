package xiaozhi.modules.config.controller;

import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.AllArgsConstructor;
import xiaozhi.common.utils.Result;
import xiaozhi.common.validator.ValidatorUtils;
import xiaozhi.modules.config.dto.AgentModelsDTO;
import xiaozhi.modules.config.dto.CorrectWordsDTO;
import xiaozhi.modules.config.dto.CompanionRuntimeDTO.CommitRequest;
import xiaozhi.modules.config.dto.CompanionRuntimeDTO.IdentityRequest;
import xiaozhi.modules.config.dto.CompanionRuntimeDTO.MemorySearchRequest;
import xiaozhi.modules.config.service.CompanionRuntimeService;
import xiaozhi.modules.config.service.ConfigService;
import xiaozhi.modules.persona.dto.PersonaRuntimeDTO.ResolveRequest;
import xiaozhi.modules.persona.service.PersonaService;

/**
 * xiaozhi-server 配置获取
 *
 * @since 1.0.0
 */
@RestController
@RequestMapping("config")
@Tag(name = "参数管理")
@AllArgsConstructor
public class ConfigController {
    private final ConfigService configService;
    private final CompanionRuntimeService companionRuntimeService;
    private final PersonaService personaService;

    @PostMapping("server-base")
    @Operation(summary = "服务端获取配置接口")
    public Result<Object> getConfig() {
        Object config = configService.getConfig(true);
        return new Result<Object>().ok(config);
    }

    @PostMapping("agent-models")
    @Operation(summary = "获取智能体模型")
    public Result<Object> getAgentModels(@Valid @RequestBody AgentModelsDTO dto) {
        // 效验数据
        ValidatorUtils.validateEntity(dto);
        Object models = configService.getAgentModels(dto.getMacAddress(), dto.getSelectedModule());
        return new Result<Object>().ok(models);
    }

    @PostMapping("correct-words")
    @Operation(summary = "获取智能体替换词")
    public Result<Object> getCorrectWords(@Valid @RequestBody CorrectWordsDTO dto) {
        ValidatorUtils.validateEntity(dto);
        List<String> list = configService.getCorrectWords(dto.getMacAddress());
        return new Result<Object>().ok(list);
    }

    @PostMapping("companion/state")
    @Operation(summary = "服务端读取 Companion 状态")
    public Result<Map<String, Object>> getCompanionState(@Valid @RequestBody IdentityRequest dto) {
        return new Result<Map<String, Object>>().ok(
                companionRuntimeService.getState(dto.getUserId(), dto.getAgentId(), dto.getPersonaId()));
    }

    @PostMapping("companion/commit")
    @Operation(summary = "服务端原子提交 Companion 轮次")
    public Result<String> commitCompanionTurn(@Valid @RequestBody CommitRequest dto) {
        return new Result<String>().ok(companionRuntimeService.commit(dto));
    }

    @PostMapping("companion/memories/search")
    @Operation(summary = "服务端读取 Companion 候选记忆")
    public Result<List<Map<String, Object>>> searchCompanionMemories(
            @Valid @RequestBody MemorySearchRequest dto) {
        return new Result<List<Map<String, Object>>>().ok(
                companionRuntimeService.getMemories(
                        dto.getUserId(), dto.getAgentId(), dto.getPersonaId(), dto.getLimit()));
    }

    @PostMapping("companion/persona/resolve")
    @Operation(summary = "服务端解析已绑定并发布的 Persona")
    public Result<Map<String, Object>> resolveCompanionPersona(@Valid @RequestBody ResolveRequest dto) {
        return new Result<Map<String, Object>>().ok(personaService.resolveRuntime(dto));
    }
}
