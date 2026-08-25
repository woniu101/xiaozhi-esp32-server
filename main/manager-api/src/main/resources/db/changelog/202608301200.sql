-- liquibase formatted sql

-- changeset codex:202608301200
CREATE TABLE IF NOT EXISTS `ai_persona_signature_override` (
    `id` CHAR(32) NOT NULL,
    `persona_source_id` VARCHAR(160) NOT NULL,
    `persona_version` VARCHAR(64) NOT NULL,
    `signature_key` VARCHAR(64) NOT NULL,
    `display_text` VARCHAR(160) NOT NULL,
    `semantic_rule` TEXT NOT NULL,
    `explicit_aliases_json` JSON DEFAULT NULL,
    `positive_examples_json` JSON DEFAULT NULL,
    `ambiguity_policy` VARCHAR(300) DEFAULT NULL,
    `fallback_mode` VARCHAR(16) NOT NULL DEFAULT 'tts',
    `style_map_json` JSON DEFAULT NULL,
    `disabled` TINYINT(1) NOT NULL DEFAULT 0,
    `owner_user_id` BIGINT NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_persona_signature_version` (`persona_source_id`, `persona_version`, `signature_key`),
    KEY `idx_persona_signature_owner` (`owner_user_id`, `updated_at`),
    CONSTRAINT `fk_persona_signature_source`
        FOREIGN KEY (`persona_source_id`) REFERENCES `ai_persona_source` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='Persona 版本级招牌表达覆盖配置';

CREATE TABLE IF NOT EXISTS `ai_persona_signature_asset` (
    `id` CHAR(32) NOT NULL,
    `persona_source_id` VARCHAR(160) NOT NULL,
    `persona_version` VARCHAR(64) NOT NULL,
    `signature_key` VARCHAR(64) NOT NULL,
    `variant` VARCHAR(32) NOT NULL,
    `content_type` VARCHAR(64) NOT NULL,
    `original_filename` VARCHAR(255) DEFAULT NULL,
    `audio_data` LONGBLOB NOT NULL,
    `byte_size` INT UNSIGNED NOT NULL,
    `sha256` CHAR(64) NOT NULL,
    `owner_user_id` BIGINT NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_persona_signature_asset` (`persona_source_id`, `persona_version`, `signature_key`, `variant`),
    KEY `idx_persona_signature_asset_owner` (`owner_user_id`, `updated_at`),
    CONSTRAINT `fk_persona_signature_asset_source`
        FOREIGN KEY (`persona_source_id`) REFERENCES `ai_persona_source` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='Persona 招牌语音资产';
