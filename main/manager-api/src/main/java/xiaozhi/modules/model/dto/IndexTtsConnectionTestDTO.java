package xiaozhi.modules.model.dto;

import cn.hutool.json.JSONObject;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Data
@Schema(description = "IndexTTS2.5 连接测试参数")
public class IndexTtsConnectionTestDTO {

    @Schema(description = "尚未保存或正在编辑的模型配置")
    private JSONObject configJson;
}
