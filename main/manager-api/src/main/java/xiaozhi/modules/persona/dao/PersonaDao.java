package xiaozhi.modules.persona.dao;

import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface PersonaDao {
    Map<String, Object> selectRuntimeVersion(
            @Param("agentId") String agentId,
            @Param("personaId") String personaId,
            @Param("version") String version);

    int countBindableVersion(
            @Param("userId") Long userId,
            @Param("personaId") String personaId,
            @Param("version") String version);

    List<Map<String, Object>> selectBindableOptions(@Param("userId") Long userId);

    int insertImportJob(
            @Param("id") String id,
            @Param("ownerUserId") Long ownerUserId,
            @Param("expectedPersonaId") String expectedPersonaId,
            @Param("sourceType") String sourceType,
            @Param("sourceUrl") String sourceUrl,
            @Param("sourceRef") String sourceRef,
            @Param("artifactPath") String artifactPath,
            @Param("status") String status);

    int insertRecompileJob(
            @Param("id") String id,
            @Param("ownerUserId") Long ownerUserId,
            @Param("expectedPersonaId") String expectedPersonaId,
            @Param("baseVersion") String baseVersion,
            @Param("inheritSignatureAudio") boolean inheritSignatureAudio,
            @Param("sourceType") String sourceType,
            @Param("sourceUrl") String sourceUrl,
            @Param("sourceRef") String sourceRef,
            @Param("artifactPath") String artifactPath,
            @Param("status") String status);

    int countRecentImports(@Param("ownerUserId") Long ownerUserId);

    List<Map<String, Object>> selectStalledImportJobs();

    int claimStalledImportJob(@Param("id") String id);

    Map<String, Object> selectImportJob(@Param("id") String id, @Param("ownerUserId") Long ownerUserId);

    Map<String, Object> selectImportJobForUpdate(@Param("id") String id);

    int updateImportJob(
            @Param("id") String id,
            @Param("status") String status,
            @Param("progress") Integer progress,
            @Param("resolvedCommit") String resolvedCommit,
            @Param("artifactHash") String artifactHash,
            @Param("artifactPath") String artifactPath,
            @Param("inspectionJson") String inspectionJson,
            @Param("compileResultJson") String compileResultJson,
            @Param("errorCode") String errorCode,
            @Param("errorMessageSafe") String errorMessageSafe);

    String selectImportJobStatus(@Param("id") String id);

    int cancelImportJob(@Param("id") String id, @Param("ownerUserId") Long ownerUserId);

    Map<String, Object> selectSourceIdentity(@Param("personaId") String personaId);

    int countPersonaBindings(@Param("personaId") String personaId);

    List<Map<String, Object>> selectOwnedPersonaBindings(
            @Param("personaId") String personaId,
            @Param("userId") Long userId);

    List<String> selectPersonaArtifactPaths(
            @Param("personaId") String personaId,
            @Param("userId") Long userId);

    int clearPersonaBindings(@Param("personaId") String personaId);

    int deletePersonaMemories(@Param("personaId") String personaId);

    int deletePersonaEvents(@Param("personaId") String personaId);

    int deletePersonaTurns(@Param("personaId") String personaId);

    int deletePersonaStates(@Param("personaId") String personaId);

    int deletePersonaImportJobs(
            @Param("personaId") String personaId,
            @Param("userId") Long userId);

    int deletePersonaAudit(
            @Param("personaId") String personaId,
            @Param("userId") Long userId);

    int hardDeletePersonaSource(
            @Param("personaId") String personaId,
            @Param("userId") Long userId);

    Map<String, Object> selectLifecycleVersions(@Param("personaId") String personaId);

    int deleteSignatureAssetsOutsideLifecycle(
            @Param("personaId") String personaId,
            @Param("retainedVersions") List<String> retainedVersions);

    int deleteSignatureOverridesOutsideLifecycle(
            @Param("personaId") String personaId,
            @Param("retainedVersions") List<String> retainedVersions);

    int deleteTestRunsOutsideLifecycle(
            @Param("personaId") String personaId,
            @Param("retainedVersions") List<String> retainedVersions);

    int deleteVersionsOutsideLifecycle(
            @Param("personaId") String personaId,
            @Param("retainedVersions") List<String> retainedVersions);

    int clearPinnedPersonaVersions(@Param("personaId") String personaId);

    int upsertPersonaSource(Map<String, Object> params);

    int insertPersonaVersion(Map<String, Object> params);

    Map<String, Object> selectVersionByHash(
            @Param("personaId") String personaId,
            @Param("version") String version);

    Map<String, Object> selectRevisionByCompiledHash(
            @Param("personaId") String personaId,
            @Param("revisionRoot") String revisionRoot,
            @Param("compiledHash") String compiledHash);

    int selectMaxRevisionNo(
            @Param("personaId") String personaId,
            @Param("revisionRoot") String revisionRoot);

    List<Map<String, Object>> selectPersonas(@Param("userId") Long userId);

    Map<String, Object> selectPersona(@Param("userId") Long userId, @Param("personaId") String personaId);

    List<Map<String, Object>> selectVersions(@Param("userId") Long userId, @Param("personaId") String personaId);

    Map<String, Object> selectVersion(
            @Param("userId") Long userId,
            @Param("personaId") String personaId,
            @Param("version") String version);

    List<Map<String, Object>> selectSignatureOverrides(
            @Param("personaId") String personaId,
            @Param("version") String version);

    int upsertSignatureOverride(Map<String, Object> params);

    int setSignatureOverrideDisabled(
            @Param("personaId") String personaId,
            @Param("version") String version,
            @Param("signatureKey") String signatureKey,
            @Param("ownerUserId") Long ownerUserId,
            @Param("disabled") boolean disabled);

    List<Map<String, Object>> selectSignatureAssets(
            @Param("personaId") String personaId,
            @Param("version") String version);

    int upsertSignatureAsset(Map<String, Object> params);

    Map<String, Object> selectSignatureAsset(@Param("assetId") String assetId);

    int deleteSignatureAsset(
            @Param("assetId") String assetId,
            @Param("ownerUserId") Long ownerUserId);

    int publishVersion(
            @Param("personaId") String personaId,
            @Param("version") String version,
            @Param("userId") Long userId);

    int applySourceVersion(
            @Param("personaId") String personaId,
            @Param("version") String version,
            @Param("userId") Long userId);

    int restorePreviousVersion(
            @Param("personaId") String personaId,
            @Param("userId") Long userId,
            @Param("currentVersion") String currentVersion,
            @Param("previousVersion") String previousVersion);

    int insertTestRun(Map<String, Object> params);

    int completeTestRun(
            @Param("id") String id,
            @Param("status") String status,
            @Param("scoreJson") String scoreJson,
            @Param("reportJson") String reportJson);

    int updateVersionTest(
            @Param("personaId") String personaId,
            @Param("version") String version,
            @Param("testStatus") String testStatus,
            @Param("qualityScore") Object qualityScore,
            @Param("testReport") String testReport);

    List<Map<String, Object>> selectTestRuns(
            @Param("userId") Long userId,
            @Param("personaId") String personaId,
            @Param("version") String version);

    List<Map<String, Object>> selectPersonaAudit(
            @Param("userId") Long userId,
            @Param("personaId") String personaId);

    int insertAudit(
            @Param("operatorUserId") Long operatorUserId,
            @Param("action") String action,
            @Param("targetType") String targetType,
            @Param("targetId") String targetId,
            @Param("detailsJson") String detailsJson);
}
