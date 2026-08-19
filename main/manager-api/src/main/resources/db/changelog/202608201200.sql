-- liquibase formatted sql

-- changeset codex:202608201200
-- Fail safely for legacy agent bindings that cannot resolve to a published Persona.
UPDATE `ai_agent_persona` ap
LEFT JOIN `ai_persona_source` s ON s.id = ap.persona_source_id
SET ap.enabled = 0
WHERE ap.enabled = 1
  AND (
      s.id IS NULL
      OR NOT EXISTS (
          SELECT 1 FROM `ai_persona_version` v
          WHERE v.persona_source_id = ap.persona_source_id AND v.status = 'published'
      )
  );
