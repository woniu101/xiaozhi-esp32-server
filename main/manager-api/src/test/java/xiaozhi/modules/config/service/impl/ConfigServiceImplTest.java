package xiaozhi.modules.config.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import xiaozhi.common.redis.RedisKeys;
import xiaozhi.common.redis.RedisUtils;
import xiaozhi.modules.agent.dao.AgentVoicePrintDao;
import xiaozhi.modules.agent.entity.AgentEntity;
import xiaozhi.modules.agent.service.AgentContextProviderService;
import xiaozhi.modules.agent.service.AgentMcpAccessPointService;
import xiaozhi.modules.agent.service.AgentPluginMappingService;
import xiaozhi.modules.agent.service.AgentService;
import xiaozhi.modules.agent.service.AgentTemplateService;
import xiaozhi.modules.correctword.service.CorrectWordFileService;
import xiaozhi.modules.characterstyle.service.CharacterStyleService;
import xiaozhi.modules.characterstyle.entity.CharacterStyleEntity;
import xiaozhi.modules.device.service.DeviceService;
import xiaozhi.modules.model.service.ModelConfigService;
import xiaozhi.modules.sys.dto.SysParamsDTO;
import xiaozhi.modules.sys.service.SysParamsService;
import xiaozhi.modules.timbre.service.TimbreService;
import xiaozhi.modules.voiceclone.service.VoiceCloneService;

class ConfigServiceImplTest {

    @Test
    void cachedServerConfigIsCheckedAsAStringKeyedMapWithoutChangingNestedValues() {
        RedisUtils redisUtils = mock(RedisUtils.class);
        Map<String, Object> nested = new HashMap<>();
        nested.put("enabled", true);
        Map<String, Object> cached = new HashMap<>();
        cached.put("features", nested);
        when(redisUtils.get(RedisKeys.getServerConfigKey())).thenReturn(cached);

        ConfigServiceImpl service = newService(mock(SysParamsService.class), redisUtils);

        Map<String, Object> result = service.getConfig(true);

        assertNotSame(cached, result);
        assertSame(nested, result.get("features"));
        assertEquals(true, ((Map<?, ?>) result.get("features")).get("enabled"));
    }

    @Test
    void nestedSystemParametersStillShareAndPopulateTheSameConfigBranch() {
        SysParamsService sysParamsService = mock(SysParamsService.class);
        SysParamsDTO enabled = parameter("server.features.enabled", "true", "boolean");
        SysParamsDTO labels = parameter("server.features.labels", "first;second", "array");
        when(sysParamsService.list(anyMap())).thenReturn(List.of(enabled, labels));
        ConfigServiceImpl service = newService(sysParamsService, mock(RedisUtils.class));
        Map<String, Object> config = new HashMap<>();

        Object returned = ReflectionTestUtils.invokeMethod(service, "buildConfig", config);

        assertSame(config, returned);
        Map<?, ?> server = assertInstanceOf(Map.class, config.get("server"));
        Map<?, ?> features = assertInstanceOf(Map.class, server.get("features"));
        assertEquals(true, features.get("enabled"));
        assertEquals(List.of("first", "second"), features.get("labels"));
    }

    @Test
    void boundCharacterStyleIsExposedAsAnIndependentRuntimeBlock() {
        CharacterStyleService characterStyleService = mock(CharacterStyleService.class);
        CharacterStyleEntity style = new CharacterStyleEntity();
        style.setId("rabbit");
        style.setName("兔娘");
        style.setSourceHash("abc123");
        style.setResolvedPrompt("你是 {{assistant_name}}。\n# 原始章节");
        style.setSignatureConfig("{\"enabled\":false,\"items\":[]}");
        when(characterStyleService.getOwned(7L, "rabbit")).thenReturn(style);
        ConfigServiceImpl service = newService(
                mock(SysParamsService.class), mock(RedisUtils.class), characterStyleService);
        AgentEntity agent = new AgentEntity();
        agent.setId("agent-1");
        agent.setUserId(7L);
        agent.setAgentName("小兔");
        agent.setCharacterStyleId("rabbit");
        Map<String, Object> result = new HashMap<>();

        ReflectionTestUtils.invokeMethod(service, "buildCharacterStyleConfig", agent, result);

        Map<?, ?> runtime = assertInstanceOf(Map.class, result.get("character_style"));
        assertEquals(true, runtime.get("active"));
        assertEquals("你是 小兔。\n# 原始章节", runtime.get("resolved_prompt"));
        assertEquals("character_styles/rabbit", runtime.get("asset_root"));
        assertEquals("abc123", runtime.get("source_hash"));
        Map<?, ?> signatures = assertInstanceOf(Map.class, runtime.get("signature_config"));
        assertEquals(false, signatures.get("enabled"));
    }

    private static SysParamsDTO parameter(String code, String value, String type) {
        SysParamsDTO parameter = new SysParamsDTO();
        parameter.setParamCode(code);
        parameter.setParamValue(value);
        parameter.setValueType(type);
        return parameter;
    }

    private static ConfigServiceImpl newService(SysParamsService sysParamsService, RedisUtils redisUtils) {
        return newService(sysParamsService, redisUtils, mock(CharacterStyleService.class));
    }

    private static ConfigServiceImpl newService(
            SysParamsService sysParamsService,
            RedisUtils redisUtils,
            CharacterStyleService characterStyleService) {
        return new ConfigServiceImpl(
                sysParamsService,
                mock(DeviceService.class),
                mock(ModelConfigService.class),
                mock(AgentService.class),
                mock(AgentTemplateService.class),
                redisUtils,
                mock(TimbreService.class),
                mock(AgentPluginMappingService.class),
                mock(AgentMcpAccessPointService.class),
                mock(AgentContextProviderService.class),
                mock(VoiceCloneService.class),
                mock(AgentVoicePrintDao.class),
                mock(CorrectWordFileService.class),
                characterStyleService);
    }
}
