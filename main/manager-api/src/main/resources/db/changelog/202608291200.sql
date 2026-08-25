-- liquibase formatted sql

-- changeset codex:202608291200
ALTER TABLE `ai_persona_import_job`
    ADD COLUMN `expected_persona_id` VARCHAR(160) DEFAULT NULL
        COMMENT '升级任务期望写入的 Persona ID；为空表示普通导入'
        AFTER `owner_user_id`,
    ADD KEY `idx_persona_import_expected` (`owner_user_id`, `expected_persona_id`, `created_at`);
