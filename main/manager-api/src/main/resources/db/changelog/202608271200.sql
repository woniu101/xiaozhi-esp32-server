-- liquibase formatted sql

-- changeset codex:202608271200
UPDATE `ai_model_config`
SET `config_json` = JSON_SET(`config_json`, '$.lang', 'zh')
WHERE `id` = 'TTS_IndexTTS2_5';
