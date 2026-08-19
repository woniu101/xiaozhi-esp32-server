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

    int upsertPersonaSource(Map<String, Object> params);

    int insertPersonaVersion(Map<String, Object> params);

    Map<String, Object> selectVersionByHash(
            @Param("personaId") String personaId,
            @Param("version") String version);

    List<Map<String, Object>> selectPersonas(@Param("userId") Long userId);

    Map<String, Object> selectPersona(@Param("userId") Long userId, @Param("personaId") String personaId);

    List<Map<String, Object>> selectVersions(@Param("userId") Long userId, @Param("personaId") String personaId);

    Map<String, Object> selectVersion(
            @Param("userId") Long userId,
            @Param("personaId") String personaId,
            @Param("version") String version);

    int publishVersion(
            @Param("personaId") String personaId,
            @Param("version") String version,
            @Param("userId") Long userId);

    int publishSource(
            @Param("personaId") String personaId,
            @Param("version") String version,
            @Param("userId") Long userId,
            @Param("visibility") String visibility);

    int setPublishedPointer(@Param("personaId") String personaId, @Param("version") String version);

    int archiveVersion(@Param("personaId") String personaId, @Param("version") String version);

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
