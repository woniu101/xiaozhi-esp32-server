-- liquibase formatted sql

-- changeset codex:202608181200
CREATE TABLE IF NOT EXISTS `ai_persona_source` (
    `id` VARCHAR(160) NOT NULL COMMENT 'Persona 稳定标识',
    `adapter_type` VARCHAR(32) NOT NULL COMMENT 'dot-skill/manual-yaml 等来源类型',
    `display_name` VARCHAR(100) NOT NULL COMMENT '显示名称',
    `source_url` VARCHAR(1000) DEFAULT NULL COMMENT '上游来源地址',
    `source_commit` VARCHAR(128) DEFAULT NULL COMMENT '上游提交',
    `artifact_hash` CHAR(64) NOT NULL COMMENT '导入制品 SHA-256',
    `upstream_schema_version` VARCHAR(32) DEFAULT NULL COMMENT '上游 schema 版本',
    `raw_artifact_path` VARCHAR(1000) DEFAULT NULL COMMENT '受控原始制品路径',
    `is_real_person` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否基于真人',
    `is_public_figure` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否公众人物',
    `archived` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否归档',
    `creator` BIGINT DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updater` BIGINT DEFAULT NULL,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_persona_source_status` (`archived`, `updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Companion Persona 来源';

CREATE TABLE IF NOT EXISTS `ai_persona_version` (
    `id` VARCHAR(32) NOT NULL COMMENT '版本记录ID',
    `persona_source_id` VARCHAR(160) NOT NULL,
    `version` VARCHAR(64) NOT NULL,
    `canonical_spec_json` JSON NOT NULL,
    `runtime_prompt` MEDIUMTEXT NOT NULL,
    `compiler_version` VARCHAR(64) NOT NULL,
    `status` VARCHAR(16) NOT NULL DEFAULT 'draft' COMMENT 'draft/published/archived',
    `validation_report` JSON DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `published_at` DATETIME DEFAULT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_persona_version` (`persona_source_id`, `version`),
    KEY `idx_persona_published` (`persona_source_id`, `status`, `published_at`),
    CONSTRAINT `fk_persona_version_source` FOREIGN KEY (`persona_source_id`)
        REFERENCES `ai_persona_source` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Companion Persona 版本';

CREATE TABLE IF NOT EXISTS `ai_agent_persona` (
    `agent_id` VARCHAR(32) NOT NULL,
    `persona_source_id` VARCHAR(160) DEFAULT NULL,
    `published_version` VARCHAR(64) DEFAULT NULL COMMENT '为空时使用当前 published',
    `enabled` TINYINT(1) NOT NULL DEFAULT 0,
    `companion_overlay_json` JSON DEFAULT NULL,
    `creator` BIGINT DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updater` BIGINT DEFAULT NULL,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`agent_id`),
    KEY `idx_agent_persona_source` (`persona_source_id`),
    CONSTRAINT `fk_agent_persona_agent` FOREIGN KEY (`agent_id`)
        REFERENCES `ai_agent` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='智能体 Companion Persona 绑定';

CREATE TABLE IF NOT EXISTS `ai_companion_state` (
    `user_id` VARCHAR(64) NOT NULL,
    `agent_id` VARCHAR(32) NOT NULL,
    `emotion_json` JSON NOT NULL,
    `relationship_json` JSON NOT NULL,
    `revision` BIGINT UNSIGNED NOT NULL DEFAULT 0,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`user_id`, `agent_id`),
    CONSTRAINT `fk_companion_state_agent` FOREIGN KEY (`agent_id`)
        REFERENCES `ai_agent` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Companion 当前状态';

CREATE TABLE IF NOT EXISTS `ai_companion_event` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `turn_id` VARCHAR(64) NOT NULL,
    `user_id` VARCHAR(64) NOT NULL,
    `agent_id` VARCHAR(32) NOT NULL,
    `event_type` VARCHAR(64) NOT NULL,
    `payload_json` JSON NOT NULL,
    `payload_hash` CHAR(64) NOT NULL,
    `confidence` DECIMAL(5,4) NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_companion_event_turn` (`turn_id`, `event_type`, `payload_hash`),
    KEY `idx_companion_event_owner` (`user_id`, `agent_id`, `created_at`),
    CONSTRAINT `fk_companion_event_agent` FOREIGN KEY (`agent_id`)
        REFERENCES `ai_agent` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Companion 事件日志';

CREATE TABLE IF NOT EXISTS `ai_companion_turn` (
    `turn_id` VARCHAR(64) NOT NULL,
    `user_id` VARCHAR(64) NOT NULL,
    `agent_id` VARCHAR(32) NOT NULL,
    `state_revision` BIGINT UNSIGNED NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`turn_id`),
    KEY `idx_companion_turn_owner` (`user_id`, `agent_id`, `created_at`),
    CONSTRAINT `fk_companion_turn_agent` FOREIGN KEY (`agent_id`)
        REFERENCES `ai_agent` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Companion 轮次幂等记录';

CREATE TABLE IF NOT EXISTS `ai_companion_memory` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `user_id` VARCHAR(64) NOT NULL,
    `agent_id` VARCHAR(32) NOT NULL,
    `memory_type` VARCHAR(32) NOT NULL,
    `content` TEXT NOT NULL,
    `normalized_hash` CHAR(64) NOT NULL,
    `importance` DECIMAL(5,4) NOT NULL,
    `confidence` DECIMAL(5,4) NOT NULL,
    `sensitivity` VARCHAR(32) NOT NULL DEFAULT 'personal',
    `occurred_at` DATETIME DEFAULT NULL,
    `source_turn_id` VARCHAR(64) NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `last_accessed_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `expires_at` DATETIME DEFAULT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_companion_memory` (`user_id`, `agent_id`, `memory_type`, `normalized_hash`),
    KEY `idx_companion_memory_owner` (`user_id`, `agent_id`, `importance`, `created_at`),
    CONSTRAINT `fk_companion_memory_agent` FOREIGN KEY (`agent_id`)
        REFERENCES `ai_agent` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Companion 长期记忆';

CREATE TABLE IF NOT EXISTS `ai_companion_audit` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `operator_user_id` BIGINT DEFAULT NULL,
    `action` VARCHAR(64) NOT NULL,
    `target_type` VARCHAR(32) NOT NULL,
    `target_id` VARCHAR(192) NOT NULL,
    `details_json` JSON DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_companion_audit_target` (`target_type`, `target_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Companion 管理审计';
