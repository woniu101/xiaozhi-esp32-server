-- liquibase formatted sql

-- changeset codex:202608231200
-- Memory lifecycle metadata supports replacement, conflict resolution and expiry
-- without erasing the historical audit trail.
ALTER TABLE `ai_companion_memory`
    ADD COLUMN `subject_key` VARCHAR(190) DEFAULT NULL AFTER `memory_type`,
    ADD COLUMN `status` VARCHAR(16) NOT NULL DEFAULT 'active' AFTER `sensitivity`,
    ADD COLUMN `superseded_by` BIGINT UNSIGNED DEFAULT NULL AFTER `status`,
    ADD KEY `idx_companion_memory_subject` (`user_id`, `agent_id`, `persona_id`, `subject_key`, `status`),
    ADD KEY `idx_companion_memory_expiry` (`expires_at`, `status`);
