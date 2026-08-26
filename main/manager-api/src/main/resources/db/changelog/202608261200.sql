-- IndexTTS2.5 标准 HTTP Provider。人物风格与情绪策略不属于本 Provider 配置。
DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_TTS_IndexTTS2_5';
INSERT INTO `ai_model_provider`
(`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES
('SYSTEM_TTS_IndexTTS2_5', 'TTS', 'index_tts_v2_5', 'IndexTTS2.5',
 '[{"key":"api_url","label":"API服务地址","type":"string"},{"key":"voice","label":"音色ID","type":"string"},{"key":"lang","label":"语言代码","type":"string"},{"key":"speed","label":"语速(0.5~2.0)","type":"number"},{"key":"tts_timeout","label":"请求超时(秒)","type":"number"},{"key":"streaming","label":"启用流式合成","type":"boolean"}]',
 20, 1, NOW(), 1, NOW());

DELETE FROM `ai_model_config` WHERE `id` = 'TTS_IndexTTS2_5';
INSERT INTO `ai_model_config`
(`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `doc_link`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES
('TTS_IndexTTS2_5', 'TTS', 'IndexTTS2_5', 'IndexTTS2.5', 0, 1,
 '{"type":"index_tts_v2_5","api_url":"http://127.0.0.1:8092","voice":"tuniang-normal","lang":"zh","speed":1.0,"text_normalization":true,"streaming":true,"stream_fallback":true,"stream_chunk_size":8192,"output_dir":"tmp/","tts_timeout":60}',
 NULL,
 '连接独立部署的 IndexTTS2.5 HTTP 服务。流式请求只在当前分段尚未向设备输出音频包时回退整段 WAV；已经输出后不会重播。',
 30, 1, NOW(), 1, NOW());

DELETE FROM `ai_tts_voice` WHERE `tts_model_id` = 'TTS_IndexTTS2_5';
INSERT INTO `ai_tts_voice`
(`id`, `tts_model_id`, `name`, `tts_voice`, `languages`, `voice_demo`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES
('TTS_IndexTTS2_5_0001', 'TTS_IndexTTS2_5', '兔娘', 'tuniang-normal', '普通话', NULL, 'IndexTTS2.5 默认音色', 1, 1, NOW(), 1, NOW());

-- 轻量 dot-skill 人物风格库：保留原文、最终提示词、来源快照哈希和诊断。
CREATE TABLE IF NOT EXISTS `ai_character_style` (
    `id` VARCHAR(32) NOT NULL COMMENT '人物风格ID',
    `user_id` BIGINT NOT NULL COMMENT '所有者用户ID',
    `name` VARCHAR(100) NOT NULL COMMENT '显示名称',
    `source_type` VARCHAR(16) NOT NULL COMMENT 'github或zip',
    `source_url` VARCHAR(500) NULL COMMENT 'GitHub来源地址',
    `source_ref` VARCHAR(200) NULL COMMENT '分支、标签或commit请求值',
    `source_hash` CHAR(64) NOT NULL COMMENT '安全快照SHA-256',
    `raw_skill_text` LONGTEXT NOT NULL COMMENT '清理frontmatter后的SKILL原文',
    `resolved_prompt` LONGTEXT NOT NULL COMMENT '包含明确引用资料的静态提示词',
    `signature_config` JSON NULL COMMENT '可选招牌表达配置',
    `diagnostics` JSON NOT NULL COMMENT '入口、纳入文件和字符数诊断',
    `created_at` DATETIME NOT NULL,
    `updated_at` DATETIME NOT NULL,
    PRIMARY KEY (`id`),
    INDEX `idx_character_style_user_updated` (`user_id`, `updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='dot-skill人物风格';

SET @character_style_col_exists = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'ai_agent'
      AND COLUMN_NAME = 'character_style_id'
);
SET @character_style_col_sql = IF(
    @character_style_col_exists = 0,
    'ALTER TABLE `ai_agent` ADD COLUMN `character_style_id` VARCHAR(32) NULL COMMENT ''绑定的人物风格ID'' AFTER `system_prompt`',
    'SELECT ''Column character_style_id already exists'' AS msg'
);
PREPARE character_style_col_stmt FROM @character_style_col_sql;
EXECUTE character_style_col_stmt;
DEALLOCATE PREPARE character_style_col_stmt;

SET @character_style_idx_exists = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'ai_agent'
      AND INDEX_NAME = 'idx_ai_agent_character_style_id'
);
SET @character_style_idx_sql = IF(
    @character_style_idx_exists = 0,
    'CREATE INDEX `idx_ai_agent_character_style_id` ON `ai_agent` (`character_style_id`)',
    'SELECT ''Index idx_ai_agent_character_style_id already exists'' AS msg'
);
PREPARE character_style_idx_stmt FROM @character_style_idx_sql;
EXECUTE character_style_idx_stmt;
DEALLOCATE PREPARE character_style_idx_stmt;
