-- liquibase formatted sql

-- changeset codex:202608311200
ALTER TABLE `ai_persona_version`
    ADD COLUMN `parent_version` VARCHAR(64) DEFAULT NULL COMMENT '重新解析修订链的根版本' AFTER `version`,
    ADD COLUMN `revision_no` INT UNSIGNED NOT NULL DEFAULT 1 COMMENT '同一源码版本的修订序号' AFTER `parent_version`,
    ADD COLUMN `source_artifact_path` VARCHAR(1000) DEFAULT NULL COMMENT '该版本对应的受控制品快照' AFTER `source_commit`,
    ADD COLUMN `compiled_hash` CHAR(64) DEFAULT NULL COMMENT 'canonical spec 与 runtime prompt 的稳定哈希' AFTER `compiler_version`,
    ADD KEY `idx_persona_revision` (`persona_source_id`, `parent_version`, `revision_no`),
    ADD KEY `idx_persona_compiled_hash` (`compiled_hash`);

ALTER TABLE `ai_persona_import_job`
    ADD COLUMN `base_version` VARCHAR(64) DEFAULT NULL COMMENT '重新解析所基于的人物版本' AFTER `expected_persona_id`,
    ADD COLUMN `force_revision` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '跳过源码版本去重并按输出创建修订版' AFTER `base_version`,
    ADD COLUMN `inherit_signature_audio` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '复制表达文本未变化的招牌录音' AFTER `force_revision`;

UPDATE `ai_persona_version`
SET `revision_no` = 1
WHERE `revision_no` IS NULL OR `revision_no` = 0;
