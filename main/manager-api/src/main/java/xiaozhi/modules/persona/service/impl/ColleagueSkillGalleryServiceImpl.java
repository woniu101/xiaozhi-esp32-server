package xiaozhi.modules.persona.service.impl;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.yaml.snakeyaml.LoaderOptions;
import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.constructor.SafeConstructor;

import xiaozhi.common.exception.RenException;
import lombok.RequiredArgsConstructor;
import xiaozhi.modules.persona.metrics.PersonaMetrics;
import xiaozhi.modules.persona.service.PersonaGalleryService;

@Service
@RequiredArgsConstructor
public class ColleagueSkillGalleryServiceImpl implements PersonaGalleryService {
    private static final URI ARCHIVE = URI.create(
            "https://codeload.github.com/titanwings/colleague-skill-site/zip/refs/heads/main");
    private static final String CONTENT_PREFIX = "website/src/content/skills/";
    private static final long CACHE_SECONDS = 6 * 60 * 60;
    private static final int MAX_ARCHIVE_BYTES = 8 * 1024 * 1024;
    private static final int MAX_YAML_BYTES = 128 * 1024;
    private static final int MAX_FILES = 500;
    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(8))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    private final PersonaMetrics metrics;

    private volatile List<Map<String, Object>> cache = List.of();
    private volatile long cacheExpiresAt = 0;

    @Override
    public List<Map<String, Object>> list(String keyword) {
        if (cache.isEmpty() || Instant.now().getEpochSecond() >= cacheExpiresAt) {
            try {
                refresh();
            } catch (RuntimeException error) {
                if (cache.isEmpty()) {
                    throw error;
                }
            }
        }
        String query = StringUtils.trimToEmpty(keyword).toLowerCase(Locale.ROOT);
        return cache.stream()
                .filter(item -> query.isEmpty() || searchable(item).contains(query))
                .map(item -> {
                    Map<String, Object> copy = new LinkedHashMap<>(item);
                    return copy;
                })
                .toList();
    }

    @Override
    public Map<String, Object> detail(String provider, String externalId) {
        if (!"colleague-skill".equals(provider)) {
            throw new RenException("不支持的 Persona 画廊 Provider");
        }
        return list("").stream()
                .filter(item -> externalId.equals(item.get("externalId")))
                .findFirst()
                .orElseThrow(() -> new RenException("Persona 画廊条目不存在"));
    }

    @Override
    public synchronized List<Map<String, Object>> refresh() {
        long started = System.nanoTime();
        try {
            HttpRequest request = HttpRequest.newBuilder(ARCHIVE)
                    .timeout(Duration.ofSeconds(30))
                    .header("Accept", "application/zip")
                    .header("User-Agent", "xiaozhi-companion-gallery")
                    .GET()
                    .build();
            HttpResponse<byte[]> response = CLIENT.send(request, HttpResponse.BodyHandlers.ofByteArray());
            if (response.statusCode() != 200 || response.body().length == 0
                    || response.body().length > MAX_ARCHIVE_BYTES) {
                throw new RenException("Persona 画廊同步失败");
            }
            List<Map<String, Object>> loaded = parseArchive(response.body());
            if (loaded.isEmpty()) {
                throw new RenException("Persona 画廊没有可导入条目");
            }
            loaded.sort(Comparator.comparing(item -> String.valueOf(item.get("createdAt")), Comparator.reverseOrder()));
            cache = List.copyOf(loaded);
            cacheExpiresAt = Instant.now().getEpochSecond() + CACHE_SECONDS;
            metrics.increment("companion_gallery_sync_total", "provider", "colleague-skill", "status", "success");
            metrics.observeMillis("companion_gallery_sync_duration_ms",
                    (System.nanoTime() - started) / 1_000_000L, "provider", "colleague-skill", "status", "success");
            return list("");
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            recordFailure(started);
            throw new RenException("Persona 画廊同步被中断", error);
        } catch (RenException error) {
            recordFailure(started);
            throw error;
        } catch (Exception error) {
            recordFailure(started);
            throw new RenException("Persona 画廊同步失败", error);
        }
    }

    private void recordFailure(long started) {
        metrics.increment("companion_gallery_sync_total", "provider", "colleague-skill", "status", "failed");
        metrics.observeMillis("companion_gallery_sync_duration_ms",
                (System.nanoTime() - started) / 1_000_000L, "provider", "colleague-skill", "status", "failed");
    }

    private List<Map<String, Object>> parseArchive(byte[] archive) throws Exception {
        List<Map<String, Object>> result = new ArrayList<>();
        LoaderOptions options = new LoaderOptions();
        options.setAllowDuplicateKeys(false);
        options.setMaxAliasesForCollections(20);
        Yaml yaml = new Yaml(new SafeConstructor(options));
        int files = 0;
        try (ZipInputStream zip = new ZipInputStream(new ByteArrayInputStream(archive), StandardCharsets.UTF_8)) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                files++;
                if (files > MAX_FILES) {
                    throw new RenException("Persona 画廊归档文件数超过限制");
                }
                String name = entry.getName().replace('\\', '/');
                int marker = name.indexOf(CONTENT_PREFIX);
                if (entry.isDirectory() || marker < 0 || !name.endsWith(".yaml") || name.contains("../")) {
                    continue;
                }
                byte[] bytes = readEntry(zip);
                Object loaded = yaml.load(new String(bytes, StandardCharsets.UTF_8));
                if (!(loaded instanceof Map<?, ?> raw)) {
                    continue;
                }
                Map<String, Object> item = normalize(raw);
                if (item != null) {
                    result.add(item);
                }
            }
        }
        return result;
    }

    private static byte[] readEntry(ZipInputStream zip) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int read;
        while ((read = zip.read(buffer)) != -1) {
            output.write(buffer, 0, read);
            if (output.size() > MAX_YAML_BYTES) {
                throw new RenException("Persona 画廊 YAML 超过大小限制");
            }
        }
        return output.toByteArray();
    }

    private static Map<String, Object> normalize(Map<?, ?> raw) {
        String repo = string(raw.get("skill_repo"));
        if (!repo.matches("^https://github\\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$")) {
            return null;
        }
        String slug = string(raw.get("slug"));
        String name = string(raw.get("name"));
        if (slug.isBlank() || name.isBlank()) {
            return null;
        }
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("provider", "colleague-skill");
        item.put("externalId", slug);
        item.put("name", name);
        item.put("description", abbreviate(string(raw.get("description")), 1200));
        item.put("descriptionEn", abbreviate(string(raw.get("description_en")), 1200));
        item.put("type", string(raw.get("type")));
        item.put("personaMode", string(raw.get("persona_mode")));
        item.put("realPerson", booleanValue(raw.get("is_real_person")));
        item.put("publicFigure", booleanValue(raw.get("is_public_figure"))
                || "public-figure".equalsIgnoreCase(string(raw.get("persona_mode"))));
        item.put("tags", stringList(raw.get("tags")));
        item.put("personality", stringList(raw.get("personality")));
        item.put("author", raw.get("author") instanceof Map<?, ?> ? raw.get("author") : Map.of());
        item.put("createdAt", string(raw.get("created_at")));
        item.put("skillRepo", repo.replaceAll("/+$", ""));
        item.put("galleryUrl", "https://titanwings.github.io/colleague-skill-site/gallery/" + slug + "/");
        item.put("compatible", true);
        return item;
    }

    private static String searchable(Map<String, Object> item) {
        return (string(item.get("name")) + " " + string(item.get("description")) + " "
                + string(item.get("tags")) + " " + string(item.get("personality"))).toLowerCase(Locale.ROOT);
    }

    private static List<String> stringList(Object value) {
        if (!(value instanceof List<?> list)) {
            return List.of();
        }
        return list.stream().map(ColleagueSkillGalleryServiceImpl::string).filter(item -> !item.isBlank()).toList();
    }

    private static String string(Object value) {
        return value == null ? "" : String.valueOf(value).trim();
    }

    private static boolean booleanValue(Object value) {
        return Boolean.TRUE.equals(value) || "true".equalsIgnoreCase(string(value)) || "1".equals(string(value));
    }

    private static String abbreviate(String value, int max) {
        return value.length() <= max ? value : value.substring(0, max - 1) + "…";
    }
}
