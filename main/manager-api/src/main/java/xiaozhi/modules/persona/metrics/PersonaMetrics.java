package xiaozhi.modules.persona.metrics;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

import org.springframework.stereotype.Component;

/**
 * Dependency-free, low-cardinality Persona metrics registry. The health endpoint
 * exposes the snapshot and production deployments can bridge it to Prometheus.
 */
@Component
public class PersonaMetrics {
    private final ConcurrentHashMap<MetricKey, LongAdder> counters = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<MetricKey, DurationStats> durations = new ConcurrentHashMap<>();

    public void increment(String name, String... labels) {
        counters.computeIfAbsent(key(name, labels), ignored -> new LongAdder()).increment();
    }

    public void observeMillis(String name, long durationMillis, String... labels) {
        durations.computeIfAbsent(key(name, labels), ignored -> new DurationStats())
                .record(Math.max(0L, durationMillis));
    }

    public Map<String, Object> snapshot() {
        List<Map<String, Object>> counterValues = new ArrayList<>();
        counters.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(entry -> counterValues.add(metric(entry.getKey(), "value", entry.getValue().sum())));
        List<Map<String, Object>> durationValues = new ArrayList<>();
        durations.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(entry -> {
                    Map<String, Object> value = metric(entry.getKey(), "sumMs", entry.getValue().sum.sum());
                    value.put("count", entry.getValue().count.sum());
                    value.put("maxMs", entry.getValue().max.get());
                    durationValues.add(value);
                });
        return Map.of("counters", counterValues, "durations", durationValues);
    }

    private static Map<String, Object> metric(MetricKey key, String valueName, long value) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("name", key.name());
        result.put("labels", key.labels());
        result.put(valueName, value);
        return result;
    }

    private static MetricKey key(String name, String... values) {
        if (values.length % 2 != 0) throw new IllegalArgumentException("metrics labels must be key/value pairs");
        Map<String, String> labels = new TreeMap<>();
        for (int index = 0; index < values.length; index += 2) {
            labels.put(values[index], values[index + 1]);
        }
        return new MetricKey(name, Map.copyOf(labels));
    }

    private record MetricKey(String name, Map<String, String> labels) implements Comparable<MetricKey> {
        @Override
        public int compareTo(MetricKey other) {
            int byName = name.compareTo(other.name);
            return byName != 0 ? byName : labels.toString().compareTo(other.labels.toString());
        }
    }

    private static final class DurationStats {
        private final LongAdder sum = new LongAdder();
        private final LongAdder count = new LongAdder();
        private final AtomicLong max = new AtomicLong();

        private void record(long value) {
            sum.add(value);
            count.increment();
            max.accumulateAndGet(value, Math::max);
        }
    }
}
