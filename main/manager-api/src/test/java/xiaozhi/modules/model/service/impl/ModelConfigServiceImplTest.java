package xiaozhi.modules.model.service.impl;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;

import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import cn.hutool.json.JSONObject;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.redis.RedisUtils;
import xiaozhi.modules.agent.dao.AgentDao;
import xiaozhi.modules.model.dao.ModelConfigDao;
import xiaozhi.modules.model.dto.ModelConfigBodyDTO;
import xiaozhi.modules.model.service.ModelProviderService;

class ModelConfigServiceImplTest {

    @Test
    void indexTtsSpeedAcceptsSupportedRange() {
        ModelConfigBodyDTO body = indexTtsBody(0.5);

        assertDoesNotThrow(() -> ReflectionTestUtils.invokeMethod(
                service(), "validateProviderConfiguration", "index_tts_v2_5", body));
    }

    @Test
    void indexTtsSpeedRejectsUnsupportedRange() {
        ModelConfigBodyDTO body = indexTtsBody(0.1);

        assertThrows(RenException.class, () -> ReflectionTestUtils.invokeMethod(
                service(), "validateProviderConfiguration", "index_tts_v2_5", body));
    }

    private ModelConfigBodyDTO indexTtsBody(double speed) {
        JSONObject config = new JSONObject();
        config.set("speed", speed);
        ModelConfigBodyDTO body = new ModelConfigBodyDTO();
        body.setConfigJson(config);
        return body;
    }

    private ModelConfigServiceImpl service() {
        return new ModelConfigServiceImpl(
                mock(ModelConfigDao.class),
                mock(ModelProviderService.class),
                mock(RedisUtils.class),
                mock(AgentDao.class));
    }
}
