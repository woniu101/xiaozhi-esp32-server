-- liquibase formatted sql

-- changeset codex:202608191200
ALTER TABLE `ai_persona_source`
    ADD COLUMN `owner_user_id` BIGINT DEFAULT NULL COMMENT 'Persona 所有者；空表示系统人物' AFTER `id`,
    ADD COLUMN `visibility` VARCHAR(16) NOT NULL DEFAULT 'private' COMMENT 'private/shared/public' AFTER `owner_user_id`,
    ADD COLUMN `persona_kind` VARCHAR(32) NOT NULL DEFAULT 'unverified' COMMENT 'fictional/real_person/public_figure/unverified' AFTER `display_name`,
    ADD COLUMN `description` VARCHAR(1000) DEFAULT NULL AFTER `persona_kind`,
    ADD COLUMN `avatar_path` VARCHAR(1000) DEFAULT NULL AFTER `description`,
    ADD COLUMN `gallery_provider` VARCHAR(64) DEFAULT NULL AFTER `avatar_path`,
    ADD COLUMN `gallery_external_id` VARCHAR(160) DEFAULT NULL AFTER `gallery_provider`,
    ADD COLUMN `source_ref` VARCHAR(255) DEFAULT NULL AFTER `source_url`,
    ADD COLUMN `relationship_ceiling` VARCHAR(16) NOT NULL DEFAULT 'friend' AFTER `persona_kind`,
    ADD COLUMN `latest_published_version` VARCHAR(64) DEFAULT NULL AFTER `relationship_ceiling`,
    ADD KEY `idx_persona_owner_visibility` (`owner_user_id`, `visibility`, `archived`),
    ADD KEY `idx_persona_gallery` (`gallery_provider`, `gallery_external_id`);

ALTER TABLE `ai_persona_version`
    ADD COLUMN `artifact_hash` CHAR(64) DEFAULT NULL AFTER `version`,
    ADD COLUMN `source_commit` VARCHAR(128) DEFAULT NULL AFTER `artifact_hash`,
    ADD COLUMN `token_count` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `compiler_version`,
    ADD COLUMN `quality_score` DECIMAL(5,2) DEFAULT NULL AFTER `token_count`,
    ADD COLUMN `test_status` VARCHAR(16) NOT NULL DEFAULT 'pending' AFTER `quality_score`,
    ADD COLUMN `test_report` JSON DEFAULT NULL AFTER `test_status`,
    ADD COLUMN `published_by` BIGINT DEFAULT NULL AFTER `published_at`,
    ADD COLUMN `archived_at` DATETIME DEFAULT NULL AFTER `published_by`,
    ADD KEY `idx_persona_version_hash` (`artifact_hash`);

UPDATE `ai_persona_version` v
JOIN `ai_persona_source` s ON s.id = v.persona_source_id
SET v.artifact_hash = s.artifact_hash
WHERE v.artifact_hash IS NULL;

UPDATE `ai_persona_source` s
SET s.latest_published_version = (
    SELECT v.version
    FROM `ai_persona_version` v
    WHERE v.persona_source_id = s.id AND v.status = 'published'
    ORDER BY v.published_at DESC, v.created_at DESC
    LIMIT 1
)
WHERE s.latest_published_version IS NULL;

CREATE TABLE `ai_persona_import_job` (
    `id` VARCHAR(32) NOT NULL,
    `owner_user_id` BIGINT NOT NULL,
    `source_type` VARCHAR(24) NOT NULL,
    `source_url` VARCHAR(1000) DEFAULT NULL,
    `source_ref` VARCHAR(255) DEFAULT NULL,
    `resolved_commit` VARCHAR(128) DEFAULT NULL,
    `artifact_hash` CHAR(64) DEFAULT NULL,
    `artifact_path` VARCHAR(1000) DEFAULT NULL,
    `status` VARCHAR(40) NOT NULL DEFAULT 'queued',
    `progress` INT NOT NULL DEFAULT 0,
    `inspection_json` JSON DEFAULT NULL,
    `compile_result_json` JSON DEFAULT NULL,
    `error_code` VARCHAR(64) DEFAULT NULL,
    `error_message_safe` VARCHAR(1000) DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `expires_at` DATETIME DEFAULT NULL,
    PRIMARY KEY (`id`),
    KEY `idx_persona_import_owner` (`owner_user_id`, `created_at`),
    KEY `idx_persona_import_status` (`status`, `updated_at`),
    KEY `idx_persona_import_hash` (`artifact_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Persona 异步导入任务';

CREATE TABLE `ai_persona_test_run` (
    `id` VARCHAR(32) NOT NULL,
    `persona_source_id` VARCHAR(160) NOT NULL,
    `version` VARCHAR(64) NOT NULL,
    `suite_version` VARCHAR(64) NOT NULL,
    `model_config_id` VARCHAR(64) DEFAULT NULL,
    `status` VARCHAR(16) NOT NULL DEFAULT 'pending',
    `score_json` JSON DEFAULT NULL,
    `report_json` JSON DEFAULT NULL,
    `created_by` BIGINT DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_persona_test_version` (`persona_source_id`, `version`, `created_at`),
    CONSTRAINT `fk_persona_test_source` FOREIGN KEY (`persona_source_id`)
        REFERENCES `ai_persona_source` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Persona 场景测试记录';
