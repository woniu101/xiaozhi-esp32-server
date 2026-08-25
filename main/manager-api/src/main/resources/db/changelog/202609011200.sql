-- liquibase formatted sql

-- changeset codex:202609011200
ALTER TABLE `ai_persona_source`
    ADD COLUMN `previous_published_version` VARCHAR(64) DEFAULT NULL
        COMMENT '当前人物的可恢复上一版' AFTER `latest_published_version`;

UPDATE `ai_agent_persona` ap
JOIN `ai_persona_source` s ON s.id = ap.persona_source_id
SET ap.persona_source_id = NULL,
    ap.published_version = NULL,
    ap.enabled = 0,
    ap.companion_overlay_json = NULL
WHERE s.archived = 1;

DELETE m FROM `ai_companion_memory` m
JOIN `ai_persona_source` s ON s.id = m.persona_id
WHERE s.archived = 1;

DELETE e FROM `ai_companion_event` e
JOIN `ai_persona_source` s ON s.id = e.persona_id
WHERE s.archived = 1;

DELETE t FROM `ai_companion_turn` t
JOIN `ai_persona_source` s ON s.id = t.persona_id
WHERE s.archived = 1;

DELETE st FROM `ai_companion_state` st
JOIN `ai_persona_source` s ON s.id = st.persona_id
WHERE s.archived = 1;

DELETE j FROM `ai_persona_import_job` j
JOIN `ai_persona_source` s
  ON s.owner_user_id = j.owner_user_id
 AND (
     j.expected_persona_id = s.id
     OR JSON_UNQUOTE(JSON_EXTRACT(j.compile_result_json, '$.personaId')) = s.id
 )
WHERE s.archived = 1;

DELETE a FROM `ai_companion_audit` a
JOIN `ai_persona_source` s
  ON s.owner_user_id = a.operator_user_id
 AND (
     a.target_id = s.id
     OR a.target_id LIKE CONCAT(s.id, '@%')
     OR a.target_id LIKE CONCAT(s.id, '#%')
 )
WHERE s.archived = 1;

DELETE FROM `ai_persona_source`
WHERE `archived` = 1;

UPDATE `ai_persona_source` s
SET s.previous_published_version = (
    SELECT v.version
    FROM `ai_persona_version` v
    WHERE v.persona_source_id = s.id
      AND v.status = 'published'
      AND NOT (v.version <=> s.latest_published_version)
    ORDER BY v.published_at DESC, v.created_at DESC
    LIMIT 1
);

UPDATE `ai_agent_persona`
SET `published_version` = NULL
WHERE `published_version` IS NOT NULL;

CREATE TEMPORARY TABLE `tmp_persona_lifecycle_keep` (
    `persona_source_id` VARCHAR(160) NOT NULL,
    `version` VARCHAR(64) NOT NULL,
    PRIMARY KEY (`persona_source_id`, `version`)
);

INSERT IGNORE INTO `tmp_persona_lifecycle_keep` (`persona_source_id`, `version`)
SELECT s.id, s.latest_published_version
FROM `ai_persona_source` s
WHERE s.latest_published_version IS NOT NULL;

INSERT IGNORE INTO `tmp_persona_lifecycle_keep` (`persona_source_id`, `version`)
SELECT s.id, s.previous_published_version
FROM `ai_persona_source` s
WHERE s.previous_published_version IS NOT NULL;

INSERT IGNORE INTO `tmp_persona_lifecycle_keep` (`persona_source_id`, `version`)
SELECT v.persona_source_id, v.version
FROM `ai_persona_version` v
WHERE v.status = 'draft'
  AND NOT EXISTS (
      SELECT 1
      FROM `ai_persona_version` newer
      WHERE newer.persona_source_id = v.persona_source_id
        AND newer.status = 'draft'
        AND (
            newer.created_at > v.created_at
            OR (newer.created_at = v.created_at AND newer.id > v.id)
        )
  );

DELETE a
FROM `ai_persona_signature_asset` a
LEFT JOIN `tmp_persona_lifecycle_keep` k
  ON k.persona_source_id = a.persona_source_id AND k.version = a.persona_version
WHERE k.version IS NULL;

DELETE o
FROM `ai_persona_signature_override` o
LEFT JOIN `tmp_persona_lifecycle_keep` k
  ON k.persona_source_id = o.persona_source_id AND k.version = o.persona_version
WHERE k.version IS NULL;

DELETE r
FROM `ai_persona_test_run` r
LEFT JOIN `tmp_persona_lifecycle_keep` k
  ON k.persona_source_id = r.persona_source_id AND k.version = r.version
WHERE k.version IS NULL;

DELETE v
FROM `ai_persona_version` v
LEFT JOIN `tmp_persona_lifecycle_keep` k
  ON k.persona_source_id = v.persona_source_id AND k.version = v.version
WHERE k.version IS NULL;

DROP TEMPORARY TABLE `tmp_persona_lifecycle_keep`;

ALTER TABLE `ai_persona_source`
    DROP INDEX `idx_persona_source_status`,
    DROP INDEX `idx_persona_owner_visibility`,
    DROP COLUMN `archived`,
    ADD KEY `idx_persona_source_updated` (`updated_at`),
    ADD KEY `idx_persona_owner_visibility` (`owner_user_id`, `visibility`);

ALTER TABLE `ai_persona_version`
    DROP COLUMN `archived_at`;
