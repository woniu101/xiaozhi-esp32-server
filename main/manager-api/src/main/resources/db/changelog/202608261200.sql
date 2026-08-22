-- liquibase formatted sql

-- changeset codex:202608261200
ALTER TABLE `ai_tts_voice`
    MODIFY COLUMN `name` VARCHAR(100) COMMENT '音色名称',
    MODIFY COLUMN `tts_voice` VARCHAR(80) COMMENT '音色编码',
    MODIFY COLUMN `languages` VARCHAR(100) COMMENT '语言';
