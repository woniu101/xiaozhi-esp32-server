-- liquibase formatted sql

-- changeset codex:202608281200
UPDATE `ai_model_provider`
SET `fields` = JSON_ARRAY_APPEND(
    `fields`,
    '$', JSON_OBJECT('key', 'dynamic_emotion', 'label', '允许动态情绪', 'type', 'boolean'),
    '$', JSON_OBJECT('key', 'emotion_presets', 'label', '情绪参考音频预设', 'type', 'dict', 'dict_name', 'emotion_presets'),
    '$', JSON_OBJECT('key', 'stream_sample_rate', 'label', '流式原始采样率', 'type', 'number'),
    '$', JSON_OBJECT('key', 'stream_chunk_size', 'label', '流式读取块大小', 'type', 'number'),
    '$', JSON_OBJECT('key', 'stream_fallback', 'label', '首包失败自动降级 WAV', 'type', 'boolean'),
    '$', JSON_OBJECT('key', 'fragment_interval', 'label', '分片间隔', 'type', 'number'),
    '$', JSON_OBJECT('key', 'overlap_length', 'label', '流式重叠长度', 'type', 'number'),
    '$', JSON_OBJECT('key', 'min_chunk_length', 'label', '最小语义分片长度', 'type', 'number')
)
WHERE `provider_code` = 'gpt_sovits_v2';

UPDATE `ai_model_provider`
SET `fields` = JSON_SET(
    `fields`,
    REPLACE(
        JSON_UNQUOTE(JSON_SEARCH(`fields`, 'one', 'streaming_mode', NULL, '$[*].key')),
        '.key', '.type'
    ), 'number',
    REPLACE(
        JSON_UNQUOTE(JSON_SEARCH(`fields`, 'one', 'streaming_mode', NULL, '$[*].key')),
        '.key', '.label'
    ), '流式模式（0关闭，1-3延迟递减）'
)
WHERE `provider_code` = 'gpt_sovits_v2'
  AND JSON_SEARCH(`fields`, 'one', 'streaming_mode', NULL, '$[*].key') IS NOT NULL;

UPDATE `ai_model_provider`
SET `fields` = JSON_ARRAY_APPEND(
    `fields`,
    '$', JSON_OBJECT('key', 'streaming', 'label', '启用真实流式播放', 'type', 'boolean'),
    '$', JSON_OBJECT('key', 'stream_chunk_size', 'label', '流式读取块大小', 'type', 'number'),
    '$', JSON_OBJECT('key', 'stream_fallback', 'label', '首包失败自动降级 WAV', 'type', 'boolean'),
    '$', JSON_OBJECT('key', 'interval_silence_ms', 'label', '语义分段静音（毫秒）', 'type', 'number'),
    '$', JSON_OBJECT('key', 'max_text_tokens_per_segment', 'label', '单段最大文本 Token', 'type', 'number')
)
WHERE `provider_code` = 'index_tts_v2_5';

UPDATE `ai_model_config`
SET `config_json` = JSON_SET(
    `config_json`,
    '$.streaming_mode', 2,
    '$.stream_sample_rate', 32000,
    '$.stream_chunk_size', 8192,
    '$.stream_fallback', JSON_EXTRACT('true', '$'),
    '$.fragment_interval', 0.3,
    '$.overlap_length', 2,
    '$.min_chunk_length', 16,
    '$.dynamic_emotion', JSON_EXTRACT('true', '$'),
    '$.emotion_presets', JSON_OBJECT()
)
WHERE `id` = 'TTS_GPT_SOVITS_V2';

UPDATE `ai_model_config`
SET `config_json` = JSON_SET(
    `config_json`,
    '$.streaming', JSON_EXTRACT('true', '$'),
    '$.stream_chunk_size', 8192,
    '$.stream_fallback', JSON_EXTRACT('true', '$'),
    '$.interval_silence_ms', 80,
    '$.max_text_tokens_per_segment', 80
)
WHERE `id` = 'TTS_IndexTTS2_5';
