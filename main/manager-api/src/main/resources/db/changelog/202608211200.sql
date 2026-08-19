-- liquibase formatted sql

-- changeset codex:202608211200
-- Remove fields and tables from early Companion development builds. Each statement is
-- conditional so this migration is safe for both a fresh schema and an upgraded dev schema.

SET @drop_persona_source_license = IF(
    EXISTS(
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'ai_persona_source'
          AND column_name = 'license'
    ),
    'ALTER TABLE `ai_persona_source` DROP COLUMN `license`',
    'SELECT 1'
);
PREPARE companion_cleanup_stmt FROM @drop_persona_source_license;
EXECUTE companion_cleanup_stmt;
DEALLOCATE PREPARE companion_cleanup_stmt;

SET @drop_persona_source_status = IF(
    EXISTS(
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'ai_persona_source'
          AND column_name = 'authorization_status'
    ),
    'ALTER TABLE `ai_persona_source` DROP COLUMN `authorization_status`',
    'SELECT 1'
);
PREPARE companion_cleanup_stmt FROM @drop_persona_source_status;
EXECUTE companion_cleanup_stmt;
DEALLOCATE PREPARE companion_cleanup_stmt;

SET @drop_persona_source_note = IF(
    EXISTS(
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'ai_persona_source'
          AND column_name = 'rights_note'
    ),
    'ALTER TABLE `ai_persona_source` DROP COLUMN `rights_note`',
    'SELECT 1'
);
PREPARE companion_cleanup_stmt FROM @drop_persona_source_note;
EXECUTE companion_cleanup_stmt;
DEALLOCATE PREPARE companion_cleanup_stmt;

SET @drop_persona_job_metadata = IF(
    EXISTS(
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'ai_persona_import_job'
          AND column_name = 'authorization_json'
    ),
    'ALTER TABLE `ai_persona_import_job` DROP COLUMN `authorization_json`',
    'SELECT 1'
);
PREPARE companion_cleanup_stmt FROM @drop_persona_job_metadata;
EXECUTE companion_cleanup_stmt;
DEALLOCATE PREPARE companion_cleanup_stmt;

DROP TABLE IF EXISTS `ai_persona_voice_binding`;

SET @drop_voice_source_status = IF(
    EXISTS(
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'ai_voice_clone'
          AND column_name = 'source_authorization_status'
    ),
    'ALTER TABLE `ai_voice_clone` DROP COLUMN `source_authorization_status`',
    'SELECT 1'
);
PREPARE companion_cleanup_stmt FROM @drop_voice_source_status;
EXECUTE companion_cleanup_stmt;
DEALLOCATE PREPARE companion_cleanup_stmt;

SET @drop_voice_artifact_path = IF(
    EXISTS(
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'ai_voice_clone'
          AND column_name = 'source_consent_artifact_path'
    ),
    'ALTER TABLE `ai_voice_clone` DROP COLUMN `source_consent_artifact_path`',
    'SELECT 1'
);
PREPARE companion_cleanup_stmt FROM @drop_voice_artifact_path;
EXECUTE companion_cleanup_stmt;
DEALLOCATE PREPARE companion_cleanup_stmt;

SET @drop_voice_artifact_hash = IF(
    EXISTS(
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'ai_voice_clone'
          AND column_name = 'source_consent_artifact_hash'
    ),
    'ALTER TABLE `ai_voice_clone` DROP COLUMN `source_consent_artifact_hash`',
    'SELECT 1'
);
PREPARE companion_cleanup_stmt FROM @drop_voice_artifact_hash;
EXECUTE companion_cleanup_stmt;
DEALLOCATE PREPARE companion_cleanup_stmt;

SET @drop_voice_source_note = IF(
    EXISTS(
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'ai_voice_clone'
          AND column_name = 'source_consent_note'
    ),
    'ALTER TABLE `ai_voice_clone` DROP COLUMN `source_consent_note`',
    'SELECT 1'
);
PREPARE companion_cleanup_stmt FROM @drop_voice_source_note;
EXECUTE companion_cleanup_stmt;
DEALLOCATE PREPARE companion_cleanup_stmt;

SET @drop_voice_ai_flag = IF(
    EXISTS(
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'ai_voice_clone'
          AND column_name = 'ai_disclosure_accepted'
    ),
    'ALTER TABLE `ai_voice_clone` DROP COLUMN `ai_disclosure_accepted`',
    'SELECT 1'
);
PREPARE companion_cleanup_stmt FROM @drop_voice_ai_flag;
EXECUTE companion_cleanup_stmt;
DEALLOCATE PREPARE companion_cleanup_stmt;

SET @drop_voice_provider_flag = IF(
    EXISTS(
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'ai_voice_clone'
          AND column_name = 'provider_terms_accepted'
    ),
    'ALTER TABLE `ai_voice_clone` DROP COLUMN `provider_terms_accepted`',
    'SELECT 1'
);
PREPARE companion_cleanup_stmt FROM @drop_voice_provider_flag;
EXECUTE companion_cleanup_stmt;
DEALLOCATE PREPARE companion_cleanup_stmt;
