package xiaozhi.modules.persona.service.impl;

import java.util.Map;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.modules.persona.dao.PersonaDao;
import xiaozhi.modules.persona.metrics.PersonaMetrics;

@Slf4j
@Component
@RequiredArgsConstructor
public class PersonaImportRecoveryTask {
    private final PersonaDao personaDao;
    private final PersonaImportWorker worker;
    private final PersonaMetrics metrics;

    @Scheduled(initialDelay = 120_000, fixedDelay = 60_000)
    public void recoverStalledJobs() {
        for (Map<String, Object> job : personaDao.selectStalledImportJobs()) {
            String id = String.valueOf(job.get("id"));
            if (personaDao.claimStalledImportJob(id) != 1) continue;
            String status = String.valueOf(job.get("status"));
            boolean resumeCompile = "compiling".equals(status) || "validating".equals(status);
            log.info("Recovering stalled Persona import job: jobId={}, stage={}", id,
                    resumeCompile ? "compile" : "inspect");
            metrics.increment("companion_import_recovery_total",
                    "stage", resumeCompile ? "compile" : "inspect");
            if (resumeCompile) worker.compile(id);
            else worker.inspect(id);
        }
    }
}
