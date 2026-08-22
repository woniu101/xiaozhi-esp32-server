-- liquibase formatted sql

-- changeset codex:202608251200
INSERT INTO `ai_model_provider` (
    `id`, `model_type`, `provider_code`, `name`, `fields`, `sort`,
    `creator`, `create_date`, `updater`, `update_date`
) VALUES (
    'SYSTEM_TTS_IndexTTS2_5',
    'TTS',
    'index_tts_v2_5',
    'IndexTTS2.5 动态情绪语音合成',
    JSON_ARRAY(
        JSON_OBJECT('key', 'api_url', 'label', 'API服务地址', 'type', 'string'),
        JSON_OBJECT('key', 'voice', 'label', '默认音色ID', 'type', 'string'),
        JSON_OBJECT('key', 'lang', 'label', '合成语言', 'type', 'string'),
        JSON_OBJECT('key', 'speed', 'label', '基础语速', 'type', 'number'),
        JSON_OBJECT('key', 'dynamic_emotion', 'label', '允许动态情绪', 'type', 'boolean'),
        JSON_OBJECT('key', 'emotion_alpha', 'label', '情绪强度上限', 'type', 'number'),
        JSON_OBJECT('key', 'normalize_emotion', 'label', '归一化情绪向量', 'type', 'boolean'),
        JSON_OBJECT('key', 'text_normalization', 'label', '文本标准化', 'type', 'boolean'),
        JSON_OBJECT('key', 'output_dir', 'label', '输出目录', 'type', 'string'),
        JSON_OBJECT('key', 'tts_timeout', 'label', '请求超时（秒）', 'type', 'number')
    ),
    19, 1, NOW(), 1, NOW()
);

INSERT INTO `ai_model_config` (
    `id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`,
    `config_json`, `doc_link`, `remark`, `sort`,
    `creator`, `create_date`, `updater`, `update_date`
) VALUES (
    'TTS_IndexTTS2_5',
    'TTS',
    'IndexTTS2_5',
    'IndexTTS2.5 动态情绪语音合成',
    0,
    1,
    '{"type":"index_tts_v2_5","api_url":"http://192.168.18.14:8092","voice":"tuniang-normal","lang":"ZH","speed":1.0,"dynamic_emotion":true,"emotion_alpha":0.85,"normalize_emotion":true,"text_normalization":true,"output_dir":"tmp/","tts_timeout":60}',
    NULL,
    '调用独立部署的 IndexTTS2.5 Companion API。支持 Companion 情绪类别、强度到八维情绪向量的动态映射；首版使用 /v1/tts WAV 接口。',
    19,
    1, NOW(), 1, NOW()
);

INSERT INTO `ai_tts_voice` (
    `id`, `tts_model_id`, `name`, `tts_voice`, `languages`, `voice_demo`,
    `remark`, `reference_audio`, `reference_text`, `sort`,
    `creator`, `create_date`, `updater`, `update_date`
) VALUES
    ('TTS_IndexTTS2_5_0001', 'TTS_IndexTTS2_5', '兔娘正常音', 'tuniang-normal', '普通话', NULL,
     'IndexTTS2.5 本地克隆音色', NULL, NULL, 1, 1, NOW(), 1, NOW()),
    ('TTS_IndexTTS2_5_0002', 'TTS_IndexTTS2_5', '兔娘夹子音', 'tuniang-cute', '普通话', NULL,
     'IndexTTS2.5 本地克隆音色', NULL, NULL, 2, 1, NOW(), 1, NOW());
