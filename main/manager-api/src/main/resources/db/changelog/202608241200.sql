-- liquibase formatted sql

-- changeset codex:202608241200
ALTER TABLE `ai_companion_turn`
    ADD COLUMN `diagnostic_json` JSON DEFAULT NULL AFTER `state_revision`;
