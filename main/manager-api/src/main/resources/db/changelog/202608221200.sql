-- liquibase formatted sql

-- changeset codex:202608221200
-- Scope Companion runtime data by Persona. Persona versions intentionally share the
-- same state; switching to a different Persona no longer inherits another character's
-- relationship, events, turns, or memories.

ALTER TABLE `ai_companion_state`
    ADD COLUMN `persona_id` VARCHAR(160) DEFAULT NULL AFTER `agent_id`;
ALTER TABLE `ai_companion_event`
    ADD COLUMN `persona_id` VARCHAR(160) DEFAULT NULL AFTER `agent_id`;
ALTER TABLE `ai_companion_turn`
    ADD COLUMN `persona_id` VARCHAR(160) DEFAULT NULL AFTER `agent_id`;
ALTER TABLE `ai_companion_memory`
    ADD COLUMN `persona_id` VARCHAR(160) DEFAULT NULL AFTER `agent_id`;

UPDATE `ai_companion_state` s
LEFT JOIN `ai_agent_persona` p ON p.agent_id = s.agent_id
SET s.persona_id = COALESCE(NULLIF(p.persona_source_id, ''), '__legacy__')
WHERE s.persona_id IS NULL;

UPDATE `ai_companion_event` e
LEFT JOIN `ai_agent_persona` p ON p.agent_id = e.agent_id
SET e.persona_id = COALESCE(NULLIF(p.persona_source_id, ''), '__legacy__')
WHERE e.persona_id IS NULL;

UPDATE `ai_companion_turn` t
LEFT JOIN `ai_agent_persona` p ON p.agent_id = t.agent_id
SET t.persona_id = COALESCE(NULLIF(p.persona_source_id, ''), '__legacy__')
WHERE t.persona_id IS NULL;

UPDATE `ai_companion_memory` m
LEFT JOIN `ai_agent_persona` p ON p.agent_id = m.agent_id
SET m.persona_id = COALESCE(NULLIF(p.persona_source_id, ''), '__legacy__')
WHERE m.persona_id IS NULL;

ALTER TABLE `ai_companion_state`
    MODIFY COLUMN `persona_id` VARCHAR(160) NOT NULL,
    DROP PRIMARY KEY,
    ADD PRIMARY KEY (`user_id`, `agent_id`, `persona_id`);

ALTER TABLE `ai_companion_event`
    MODIFY COLUMN `persona_id` VARCHAR(160) NOT NULL,
    DROP INDEX `idx_companion_event_owner`,
    ADD KEY `idx_companion_event_owner` (`user_id`, `agent_id`, `persona_id`, `created_at`);

ALTER TABLE `ai_companion_turn`
    MODIFY COLUMN `persona_id` VARCHAR(160) NOT NULL,
    DROP INDEX `idx_companion_turn_owner`,
    ADD KEY `idx_companion_turn_owner` (`user_id`, `agent_id`, `persona_id`, `created_at`);

ALTER TABLE `ai_companion_memory`
    MODIFY COLUMN `persona_id` VARCHAR(160) NOT NULL,
    DROP INDEX `uk_companion_memory`,
    DROP INDEX `idx_companion_memory_owner`,
    ADD UNIQUE KEY `uk_companion_memory` (`user_id`, `agent_id`, `persona_id`, `memory_type`, `normalized_hash`),
    ADD KEY `idx_companion_memory_owner` (`user_id`, `agent_id`, `persona_id`, `importance`, `created_at`);
