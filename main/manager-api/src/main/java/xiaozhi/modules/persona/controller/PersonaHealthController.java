package xiaozhi.modules.persona.controller;

import java.util.LinkedHashMap;
import java.util.Map;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import lombok.RequiredArgsConstructor;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.persona.client.PersonaCompilerClient;
import xiaozhi.modules.persona.metrics.PersonaMetrics;

@RestController
@RequestMapping("/persona/health")
@RequiredArgsConstructor
@RequiresPermissions("sys:role:normal")
public class PersonaHealthController {
    private final JdbcTemplate jdbcTemplate;
    private final PersonaCompilerClient compilerClient;
    private final PersonaMetrics personaMetrics;

    @GetMapping
    public Result<Map<String, Object>> health() {
        Map<String, Object> value = new LinkedHashMap<>();
        try {
            value.put("database", Integer.valueOf(1).equals(jdbcTemplate.queryForObject("SELECT 1", Integer.class)) ? "up" : "down");
        } catch (Exception error) {
            value.put("database", "down");
        }
        try {
            value.put("compiler", compilerClient.health());
        } catch (Exception error) {
            String message = error.getMessage();
            value.put("compiler", Map.of(
                    "status", "down",
                    "message", message == null || message.isBlank() ? "Persona Compiler 不可用" : message));
        }
        value.put("managerMetrics", personaMetrics.snapshot());
        boolean up = "up".equals(value.get("database"))
                && value.get("compiler") instanceof Map<?, ?> compiler
                && "up".equals(compiler.get("status"));
        value.put("status", up ? "up" : "degraded");
        return new Result<Map<String, Object>>().ok(value);
    }
}
