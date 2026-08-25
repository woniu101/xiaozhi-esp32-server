package xiaozhi.modules.persona.dao;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.util.List;
import java.util.Map;

import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.BoundSql;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.Test;

import net.sf.jsqlparser.parser.CCJSqlParserUtil;

class PersonaDaoMapperTest {
    private static final String NAMESPACE = PersonaDao.class.getName() + ".";

    @Test
    void lifecycleCleanupStatementsAreParserSafeAndKeepExplicitVersions() throws Exception {
        Configuration configuration = mapperConfiguration();
        Map<String, Object> params = Map.of(
                "personaId", "persona.test",
                "retainedVersions", List.of("v3", "v2", "v4-draft"));

        for (String statement : List.of(
                "deleteSignatureAssetsOutsideLifecycle",
                "deleteSignatureOverridesOutsideLifecycle",
                "deleteTestRunsOutsideLifecycle",
                "deleteVersionsOutsideLifecycle")) {
            BoundSql boundSql = configuration.getMappedStatement(NAMESPACE + statement).getBoundSql(params);
            String sql = boundSql.getSql().replaceAll("\\s+", " ").trim();

            assertTrue(sql.contains("NOT IN ( ? , ? , ? )"), sql);
            assertFalse(sql.contains(" JOIN "), sql);
            assertDoesNotThrow(() -> CCJSqlParserUtil.parse(sql), sql);
        }
    }

    @Test
    void lifecycleCleanupIsANoOpWhenNoVersionCanBeRetained() throws Exception {
        Configuration configuration = mapperConfiguration();
        Map<String, Object> params = Map.of(
                "personaId", "persona.test",
                "retainedVersions", List.of());

        for (String statement : List.of(
                "deleteSignatureAssetsOutsideLifecycle",
                "deleteSignatureOverridesOutsideLifecycle",
                "deleteTestRunsOutsideLifecycle",
                "deleteVersionsOutsideLifecycle")) {
            BoundSql boundSql = configuration.getMappedStatement(NAMESPACE + statement).getBoundSql(params);
            String sql = boundSql.getSql().replaceAll("\\s+", " ").trim();

            assertTrue(sql.contains("AND 1 = 0"), sql);
            assertDoesNotThrow(() -> CCJSqlParserUtil.parse(sql), sql);
        }
    }

    private Configuration mapperConfiguration() throws Exception {
        Configuration configuration = new Configuration();
        String resource = "mapper/persona/PersonaDao.xml";
        try (InputStream input = getClass().getClassLoader().getResourceAsStream(resource)) {
            if (input == null) throw new IllegalStateException("找不到 " + resource);
            new XMLMapperBuilder(input, configuration, resource, configuration.getSqlFragments()).parse();
        }
        return configuration;
    }
}
