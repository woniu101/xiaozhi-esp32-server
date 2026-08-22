package xiaozhi.modules.timbre.service.impl;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import cn.hutool.core.collection.CollectionUtil;
import lombok.AllArgsConstructor;
import xiaozhi.common.constant.Constant;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.page.PageData;
import xiaozhi.common.redis.RedisKeys;
import xiaozhi.common.redis.RedisUtils;
import xiaozhi.common.service.impl.BaseServiceImpl;
import xiaozhi.common.utils.ConvertUtils;
import xiaozhi.common.utils.MessageUtils;
import xiaozhi.modules.model.dto.VoiceDTO;
import xiaozhi.modules.model.entity.ModelConfigEntity;
import xiaozhi.modules.model.service.ModelConfigService;
import xiaozhi.modules.security.user.SecurityUser;
import xiaozhi.modules.timbre.dao.TimbreDao;
import xiaozhi.modules.timbre.dto.TimbreDataDTO;
import xiaozhi.modules.timbre.dto.TimbrePageDTO;
import xiaozhi.modules.timbre.entity.TimbreEntity;
import xiaozhi.modules.timbre.service.TimbreService;
import xiaozhi.modules.timbre.vo.TimbreDetailsVO;
import xiaozhi.modules.timbre.vo.IndexTtsVoiceVO;
import xiaozhi.modules.voiceclone.dao.VoiceCloneDao;
import xiaozhi.modules.voiceclone.entity.VoiceCloneEntity;

/**
 * 音色的业务层的实现
 * 
 * @author zjy
 * @since 2025-3-21
 */
@AllArgsConstructor
@Service
public class TimbreServiceImpl extends BaseServiceImpl<TimbreDao, TimbreEntity> implements TimbreService {

    private static final Pattern LANGUAGE_SEPARATOR = Pattern.compile("[、；;,，]");
    private static final Pattern INDEX_VOICE_ID = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$");
    private static final long INDEX_VOICE_MAX_BYTES = 20L * 1024 * 1024;
    private static final HttpClient INDEX_TTS_HTTP_CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    private final TimbreDao timbreDao;
    private final VoiceCloneDao voiceCloneDao;
    private final RedisUtils redisUtils;
    private final ModelConfigService modelConfigService;
    private final ObjectMapper objectMapper;

    @Override
    public PageData<TimbreDetailsVO> page(TimbrePageDTO dto) {
        Map<String, Object> params = new HashMap<String, Object>();
        params.put(Constant.PAGE, dto.getPage());
        params.put(Constant.LIMIT, dto.getLimit());
        IPage<TimbreEntity> page = baseDao.selectPage(
                getPage(params, null, true),
                // 定义查询条件
                new QueryWrapper<TimbreEntity>()
                        // 必须按照ttsID查找
                        .eq("tts_model_id", dto.getTtsModelId())
                        // 如果有音色名字，按照音色名模糊查找
                        .like(StringUtils.isNotBlank(dto.getName()), "name", dto.getName()));

        return getPageData(page, TimbreDetailsVO.class);
    }

    @Override
    public TimbreDetailsVO get(String timbreId) {
        if (StringUtils.isBlank(timbreId)) {
            return null;
        }

        // 先从Redis获取缓存
        String key = RedisKeys.getTimbreDetailsKey(timbreId);
        TimbreDetailsVO cachedDetails = (TimbreDetailsVO) redisUtils.get(key);
        if (cachedDetails != null) {
            return cachedDetails;
        }

        // 如果缓存中没有，则从数据库获取
        TimbreEntity entity = baseDao.selectById(timbreId);
        if (entity == null) {
            return null;
        }

        // 转换为VO对象
        TimbreDetailsVO details = ConvertUtils.sourceToTarget(entity, TimbreDetailsVO.class);

        // 存入Redis缓存
        if (details != null) {
            redisUtils.set(key, details);
        }

        return details;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void save(TimbreDataDTO dto) {
        isTtsModelId(dto.getTtsModelId());
        if (dto.getSort() == null) {
            dto.setSort(0L);
        }
        TimbreEntity timbreEntity = ConvertUtils.sourceToTarget(dto, TimbreEntity.class);
        baseDao.insert(timbreEntity);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void update(String timbreId, TimbreDataDTO dto) {
        isTtsModelId(dto.getTtsModelId());
        TimbreEntity timbreEntity = ConvertUtils.sourceToTarget(dto, TimbreEntity.class);
        timbreEntity.setId(timbreId);
        baseDao.updateById(timbreEntity);
        // 删除缓存
        redisUtils.delete(RedisKeys.getTimbreDetailsKey(timbreId));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void delete(String[] ids) {
        baseDao.deleteByIds(Arrays.asList(ids));
    }

    @Override
    public List<VoiceDTO> getVoiceNames(String ttsModelId, String voiceName) {
        QueryWrapper<TimbreEntity> queryWrapper = new QueryWrapper<>();
        queryWrapper.eq("tts_model_id", StringUtils.isBlank(ttsModelId) ? "" : ttsModelId);
        if (StringUtils.isNotBlank(voiceName)) {
            queryWrapper.like("name", voiceName);
        }
        List<TimbreEntity> timbreEntities = Optional.ofNullable(timbreDao.selectList(queryWrapper)).orElseGet(ArrayList::new);
        List<VoiceDTO> voiceDTOs = timbreEntities.stream()
                .map(entity -> {
                    VoiceDTO dto = new VoiceDTO(entity.getId(), entity.getName());
                    dto.setVoiceDemo(entity.getVoiceDemo());
                    dto.setLanguages(entity.getLanguages()); // 设置语言类型
                    dto.setIsClone(false); // 设置为普通音色
                    return dto;
                })
                .collect(Collectors.toList());

        // 获取当前登录用户ID
        Long currentUserId = SecurityUser.getUser().getId();
        if (currentUserId != null) {
            // 查询用户的所有克隆音色记录
            List<VoiceDTO> cloneEntities = voiceCloneDao.getTrainSuccess(ttsModelId, currentUserId);
            for (VoiceDTO entity : cloneEntities) {
                // 只添加训练成功的克隆音色，且模型ID匹配
                VoiceDTO voiceDTO = new VoiceDTO();
                voiceDTO.setId(entity.getId());
                voiceDTO.setName(MessageUtils.getMessage(ErrorCode.VOICE_CLONE_PREFIX) + entity.getName());
                // 保留从数据库查询到的voiceDemo字段
                voiceDTO.setVoiceDemo(entity.getVoiceDemo());
                voiceDTO.setLanguages(entity.getLanguages());
                voiceDTO.setIsClone(true); // 设置为克隆音色
                redisUtils.set(RedisKeys.getTimbreNameById(voiceDTO.getId()), voiceDTO.getName(),
                        RedisUtils.NOT_EXPIRE);
                voiceDTOs.add(0, voiceDTO);
            }
        }

        return CollectionUtil.isEmpty(voiceDTOs) ? null : voiceDTOs;
    }

    @Override
    public String getDefaultLanguageById(String id) {
        if (StringUtils.isBlank(id)) {
            return null;
        }

        TimbreEntity timbre = timbreDao.selectById(id);
        if (timbre != null) {
            return firstNonBlankLanguage(timbre.getLanguages());
        }

        VoiceCloneEntity voiceClone = voiceCloneDao.selectById(id);
        return voiceClone == null ? null : firstNonBlankLanguage(voiceClone.getLanguages());
    }

    private String firstNonBlankLanguage(String languages) {
        if (StringUtils.isBlank(languages)) {
            return null;
        }
        return LANGUAGE_SEPARATOR.splitAsStream(languages)
                .map(StringUtils::trimToNull)
                .filter(Objects::nonNull)
                .findFirst()
                .orElse(null);
    }

    /**
     * 处理是不是tts模型的id
     */
    private void isTtsModelId(String ttsModelId) {
        // 等模型配置那边写好调用方法判断
    }

    @Override
    public String getTimbreNameById(String id) {
        if (StringUtils.isBlank(id)) {
            return null;
        }

        String cachedName = (String) redisUtils.get(RedisKeys.getTimbreNameById(id));

        if (StringUtils.isNotBlank(cachedName)) {
            return cachedName;
        }

        TimbreEntity entity = timbreDao.selectById(id);
        if (entity != null) {
            String name = entity.getName();
            if (StringUtils.isNotBlank(name)) {
                redisUtils.set(RedisKeys.getTimbreNameById(id), name);
            }
            return name;
        } else {
            VoiceCloneEntity cloneEntity = voiceCloneDao.selectById(id);
            if (cloneEntity != null) {
                String name = MessageUtils.getMessage(ErrorCode.VOICE_CLONE_PREFIX) + cloneEntity.getName();
                redisUtils.set(RedisKeys.getTimbreNameById(id), name);
                return name;
            }
        }

        return null;
    }

    @Override
    public VoiceDTO getByVoiceCode(String ttsModelId, String voiceCode) {
        if (StringUtils.isBlank(voiceCode)) {
            return null;
        }
        QueryWrapper<TimbreEntity> queryWrapper = new QueryWrapper<>();
        queryWrapper.eq("tts_model_id", ttsModelId);
        queryWrapper.eq("tts_voice", voiceCode);
        List<TimbreEntity> list = timbreDao.selectList(queryWrapper);
        if (list.isEmpty()) {
            return null;
        }
        TimbreEntity entity = list.get(0);
        VoiceDTO dto = new VoiceDTO(entity.getId(), entity.getName());
        dto.setVoiceDemo(entity.getVoiceDemo());
        dto.setIsClone(false); // 设置为普通音色
        return dto;
    }

    @Override
    public List<IndexTtsVoiceVO> getIndexTtsRemoteVoices(String ttsModelId) {
        return decorateRemoteVoices(ttsModelId, fetchIndexTtsRemoteVoices(ttsModelId));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public List<IndexTtsVoiceVO> syncIndexTtsRemoteVoices(String ttsModelId) {
        List<IndexTtsVoiceVO> voices = fetchIndexTtsRemoteVoices(ttsModelId);
        int sort = 1;
        for (IndexTtsVoiceVO voice : voices) {
            TimbreEntity entity = findIndexVoice(ttsModelId, voice.getVoiceId());
            if (entity == null) {
                entity = new TimbreEntity();
                entity.setId(stableIndexVoiceId(ttsModelId, voice.getVoiceId()));
                entity.setTtsModelId(ttsModelId);
                entity.setTtsVoice(voice.getVoiceId());
                entity.setVoiceDemo("");
                entity.setRemark("IndexTTS2.5 远端音色");
                entity.setName(voice.getName());
                entity.setLanguages(StringUtils.defaultIfBlank(voice.getLanguages(), "普通话"));
                entity.setReferenceText(StringUtils.defaultString(voice.getPromptText()));
                entity.setSort((long) sort++);
                timbreDao.insert(entity);
            } else {
                entity.setName(voice.getName());
                entity.setLanguages(StringUtils.defaultIfBlank(voice.getLanguages(), "普通话"));
                entity.setReferenceText(StringUtils.defaultString(voice.getPromptText()));
                entity.setSort((long) sort++);
                timbreDao.updateById(entity);
                redisUtils.delete(RedisKeys.getTimbreDetailsKey(entity.getId()));
                redisUtils.delete(RedisKeys.getTimbreNameById(entity.getId()));
            }
        }
        return decorateRemoteVoices(ttsModelId, voices);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public IndexTtsVoiceVO registerIndexTtsVoice(
            String ttsModelId,
            String voiceId,
            String name,
            String languages,
            String promptText,
            MultipartFile audio) {
        if (!INDEX_VOICE_ID.matcher(StringUtils.defaultString(voiceId)).matches()) {
            throw new RenException("Voice ID 只能包含字母、数字、点、下划线和连字符，最长 80 个字符");
        }
        if (StringUtils.isBlank(name)) {
            throw new RenException("音色名称不能为空");
        }
        if (audio == null || audio.isEmpty()) {
            throw new RenException("请上传 WAV 参考音频");
        }
        if (audio.getSize() > INDEX_VOICE_MAX_BYTES) {
            throw new RenException("参考音频不能超过 20MB");
        }
        try {
            byte[] audioBytes = audio.getBytes();
            if (audioBytes.length < 44
                    || audioBytes[0] != 'R'
                    || audioBytes[1] != 'I'
                    || audioBytes[2] != 'F'
                    || audioBytes[3] != 'F') {
                throw new RenException("参考音频必须是有效的 WAV 文件");
            }
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("voice_id", voiceId);
            payload.put("name", name.trim());
            payload.put("languages", StringUtils.defaultIfBlank(languages, "普通话").trim());
            payload.put("prompt_text", StringUtils.defaultString(promptText).trim());
            payload.put("audio_base64", Base64.getEncoder().encodeToString(audioBytes));
            String body = objectMapper.writeValueAsString(payload);
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(indexTtsBaseUrl(ttsModelId) + "/v1/voices"))
                    .timeout(Duration.ofSeconds(60))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> response = INDEX_TTS_HTTP_CLIENT.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            ensureIndexTtsSuccess(response.statusCode(), response.body(), "注册音色");
            return syncIndexTtsRemoteVoices(ttsModelId).stream()
                    .filter(item -> voiceId.equals(item.getVoiceId()))
                    .findFirst()
                    .orElseThrow(() -> new RenException("远端音色注册成功，但同步结果中未找到该音色"));
        } catch (RenException exception) {
            throw exception;
        } catch (Exception exception) {
            if (exception instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            throw new RenException("IndexTTS2.5 音色注册失败：" + exception.getMessage(), exception);
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteIndexTtsVoice(String ttsModelId, String voiceId) {
        if (!INDEX_VOICE_ID.matcher(StringUtils.defaultString(voiceId)).matches()) {
            throw new RenException("Voice ID 格式不正确");
        }
        TimbreEntity local = findIndexVoice(ttsModelId, voiceId);
        if (local != null && timbreDao.countVoiceReferences(local.getId()) > 0) {
            throw new RenException("该音色仍被角色或角色模板使用，请先切换这些绑定");
        }
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(indexTtsBaseUrl(ttsModelId) + "/v1/voices/" + voiceId))
                    .timeout(Duration.ofSeconds(30))
                    .DELETE()
                    .build();
            HttpResponse<String> response = INDEX_TTS_HTTP_CLIENT.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            // 删除保持幂等：远端已缺失时，仍允许清理本地的失效目录记录。
            if (response.statusCode() != 404) {
                ensureIndexTtsSuccess(response.statusCode(), response.body(), "删除音色");
            }
            if (local != null) {
                timbreDao.deleteById(local.getId());
                redisUtils.delete(RedisKeys.getTimbreDetailsKey(local.getId()));
                redisUtils.delete(RedisKeys.getTimbreNameById(local.getId()));
            }
        } catch (RenException exception) {
            throw exception;
        } catch (Exception exception) {
            if (exception instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            throw new RenException("IndexTTS2.5 音色删除失败：" + exception.getMessage(), exception);
        }
    }

    @Override
    public byte[] previewIndexTtsVoice(String ttsModelId, String voiceId, String text) {
        if (!INDEX_VOICE_ID.matcher(StringUtils.defaultString(voiceId)).matches()) {
            throw new RenException("Voice ID 格式不正确");
        }
        if (StringUtils.isBlank(text) || text.length() > 300) {
            throw new RenException("试听文本长度必须在 1 到 300 个字符之间");
        }
        try {
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("request_id", "manager-preview-" + UUID.randomUUID());
            payload.put("voice_id", voiceId);
            payload.put("text", text.trim());
            payload.put("lang", "zh");
            payload.put("speed", 1.0);
            String body = objectMapper.writeValueAsString(payload);
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(indexTtsBaseUrl(ttsModelId) + "/v1/tts"))
                    .timeout(Duration.ofSeconds(120))
                    .header("Content-Type", "application/json")
                    .header("Accept", "audio/wav")
                    .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
                    .build();
            HttpResponse<byte[]> response = INDEX_TTS_HTTP_CLIENT.send(
                    request,
                    HttpResponse.BodyHandlers.ofByteArray());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                String details = new String(response.body(), StandardCharsets.UTF_8);
                ensureIndexTtsSuccess(response.statusCode(), details, "试听音色");
            }
            return response.body();
        } catch (RenException exception) {
            throw exception;
        } catch (Exception exception) {
            if (exception instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            throw new RenException("IndexTTS2.5 音色试听失败：" + exception.getMessage(), exception);
        }
    }

    private List<IndexTtsVoiceVO> fetchIndexTtsRemoteVoices(String ttsModelId) {
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(indexTtsBaseUrl(ttsModelId) + "/v1/voices"))
                    .timeout(Duration.ofSeconds(15))
                    .GET()
                    .build();
            HttpResponse<String> response = INDEX_TTS_HTTP_CLIENT.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            ensureIndexTtsSuccess(response.statusCode(), response.body(), "读取音色列表");
            JsonNode voicesNode = objectMapper.readTree(response.body()).path("voices");
            if (!voicesNode.isArray()) {
                throw new RenException("IndexTTS2.5 音色接口返回格式不正确");
            }
            List<IndexTtsVoiceVO> voices = new ArrayList<>();
            for (JsonNode item : voicesNode) {
                IndexTtsVoiceVO voice = new IndexTtsVoiceVO();
                voice.setVoiceId(item.path("voice_id").asText());
                voice.setName(item.path("name").asText(voice.getVoiceId()));
                voice.setLanguages(item.path("languages").asText("普通话"));
                voice.setPromptText(item.path("prompt_text").asText(""));
                voice.setDefaultVoice(item.path("default").asBoolean(false));
                voices.add(voice);
            }
            return voices;
        } catch (RenException exception) {
            throw exception;
        } catch (Exception exception) {
            if (exception instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            throw new RenException("IndexTTS2.5 音色列表读取失败：" + exception.getMessage(), exception);
        }
    }

    private List<IndexTtsVoiceVO> decorateRemoteVoices(
            String ttsModelId,
            List<IndexTtsVoiceVO> voices) {
        for (IndexTtsVoiceVO voice : voices) {
            TimbreEntity local = findIndexVoice(ttsModelId, voice.getVoiceId());
            voice.setLocalId(local == null ? null : local.getId());
            voice.setSynced(local != null);
        }
        return voices;
    }

    private TimbreEntity findIndexVoice(String ttsModelId, String voiceId) {
        return timbreDao.selectOne(
                new QueryWrapper<TimbreEntity>()
                        .eq("tts_model_id", ttsModelId)
                        .eq("tts_voice", voiceId)
                        .last("LIMIT 1"));
    }

    private String stableIndexVoiceId(String ttsModelId, String voiceId) {
        return UUID.nameUUIDFromBytes(
                (ttsModelId + "\u0000" + voiceId).getBytes(StandardCharsets.UTF_8))
                .toString()
                .replace("-", "");
    }

    private String indexTtsBaseUrl(String ttsModelId) {
        ModelConfigEntity model = modelConfigService.getModelByIdFromCache(ttsModelId);
        if (model == null || model.getConfigJson() == null) {
            throw new RenException("IndexTTS2.5 模型配置不存在");
        }
        String type = model.getConfigJson().getStr("type");
        if (!"index_tts_v2_5".equals(type)) {
            throw new RenException("当前模型不是 IndexTTS2.5");
        }
        String url = StringUtils.removeEnd(model.getConfigJson().getStr("api_url"), "/");
        if (StringUtils.isBlank(url)) {
            throw new RenException("IndexTTS2.5 API 地址未配置");
        }
        if (url.endsWith("/v1/tts/stream")) {
            url = StringUtils.removeEnd(url, "/v1/tts/stream");
        } else if (url.endsWith("/v1/tts")) {
            url = StringUtils.removeEnd(url, "/v1/tts");
        }
        URI uri = URI.create(url);
        if (!("http".equalsIgnoreCase(uri.getScheme()) || "https".equalsIgnoreCase(uri.getScheme()))) {
            throw new RenException("IndexTTS2.5 API 地址必须使用 HTTP 或 HTTPS");
        }
        return url;
    }

    private void ensureIndexTtsSuccess(int statusCode, String body, String action) {
        if (statusCode >= 200 && statusCode < 300) {
            return;
        }
        String details = StringUtils.abbreviate(StringUtils.defaultString(body), 400);
        throw new RenException(action + "失败，远端状态码 " + statusCode +
                (StringUtils.isBlank(details) ? "" : "：" + details));
    }
}
