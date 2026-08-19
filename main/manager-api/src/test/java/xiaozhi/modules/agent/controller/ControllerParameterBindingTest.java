package xiaozhi.modules.agent.controller;

import static org.junit.jupiter.api.Assertions.assertFalse;

import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.Map;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;

import xiaozhi.modules.persona.controller.PersonaController;

class ControllerParameterBindingTest {

    @Test
    void routeParametersDoNotDependOnCompilerParameterMetadata() {
        Stream.of(AgentController.class, AgentSnapshotController.class, PersonaController.class)
                .flatMap(controller -> Stream.of(controller.getDeclaredMethods()))
                .forEach(this::assertExplicitRouteParameterNames);
    }

    private void assertExplicitRouteParameterNames(Method method) {
        for (Parameter parameter : method.getParameters()) {
            PathVariable pathVariable = parameter.getAnnotation(PathVariable.class);
            if (pathVariable != null) {
                assertFalse(pathVariable.value().isBlank() && pathVariable.name().isBlank(),
                        () -> method + " contains an unnamed @PathVariable");
            }

            RequestParam requestParam = parameter.getAnnotation(RequestParam.class);
            if (requestParam != null && !Map.class.isAssignableFrom(parameter.getType())) {
                assertFalse(requestParam.value().isBlank() && requestParam.name().isBlank(),
                        () -> method + " contains an unnamed @RequestParam");
            }
        }
    }
}
