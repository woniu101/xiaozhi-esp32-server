package xiaozhi.modules.persona.service.impl;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import lombok.AllArgsConstructor;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.persona.dao.PersonaDao;
import xiaozhi.modules.persona.dto.PersonaRuntimeDTO.ResolveRequest;
import xiaozhi.modules.persona.service.PersonaService;

@Service
@AllArgsConstructor
public class PersonaServiceImpl implements PersonaService {
    private final PersonaDao personaDao;

    @Override
    public Map<String, Object> resolveRuntime(ResolveRequest request) {
        Map<String, Object> row = personaDao.selectRuntimeVersion(
                request.getAgentId(), request.getPersonaId(), request.getVersion());
        if (row == null) {
            throw new RenException("Persona 不存在、未发布或未绑定到该智能体");
        }
        String artifactHash = String.valueOf(row.get("artifactHash"));
        if (StringUtils.isNotBlank(request.getKnownArtifactHash())
                && request.getKnownArtifactHash().equals(artifactHash)) {
            Map<String, Object> notModified = new LinkedHashMap<>();
            notModified.put("notModified", true);
            notModified.put("personaId", row.get("personaId"));
            notModified.put("version", row.get("version"));
            notModified.put("artifactHash", artifactHash);
            return notModified;
        }
        Map<String, Object> result = new LinkedHashMap<>(row);
        Object canonical = row.get("canonicalSpec");
        if (canonical instanceof String text) {
            result.put("canonicalSpec", JsonUtils.parseMap(text));
        }
        result.put("notModified", false);
        Map<String, Object> effectivePolicy = new LinkedHashMap<>();
        effectivePolicy.put("relationshipCeiling", row.get("relationshipCeiling"));
        effectivePolicy.put("personaKind", row.get("personaKind"));
        result.put("effectivePolicy", effectivePolicy);
        return result;
    }

    @Override
    public void requireBindable(Long userId, String personaId, String version) {
        if (userId == null || StringUtils.isBlank(personaId)
                || personaDao.countBindableVersion(userId, personaId, version) < 1) {
            throw new RenException("Persona 不存在、不可访问或没有可绑定的已发布版本");
        }
    }

    @Override
    public List<Map<String, Object>> listBindable(Long userId) {
        return personaDao.selectBindableOptions(userId);
    }

    @Override
    public void recordBindingAudit(Long userId, String agentId, boolean enabled, String personaId, String version) {
        Map<String, Object> details = new LinkedHashMap<>();
        details.put("enabled", enabled);
        details.put("personaId", personaId);
        details.put("version", version);
        personaDao.insertAudit(userId, enabled ? "persona_agent_bound" : "persona_agent_disabled",
                "agent", agentId, JsonUtils.toJsonString(details));
    }
}
