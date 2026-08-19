package xiaozhi.modules.persona.service;

import java.util.List;
import java.util.Map;

public interface PersonaGalleryService {
    List<Map<String, Object>> list(String keyword);

    Map<String, Object> detail(String provider, String externalId);

    List<Map<String, Object>> refresh();
}
