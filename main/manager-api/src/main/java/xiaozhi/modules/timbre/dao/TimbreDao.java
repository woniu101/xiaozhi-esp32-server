package xiaozhi.modules.timbre.dao;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;

import xiaozhi.modules.timbre.entity.TimbreEntity;

/**
 * 音色持久层定义
 * 
 * @author zjy
 * @since 2025-3-21
 */
@Mapper
public interface TimbreDao extends BaseMapper<TimbreEntity> {

    @Select("SELECT " +
            "(SELECT COUNT(*) FROM ai_agent WHERE tts_voice_id = #{voiceId}) + " +
            "(SELECT COUNT(*) FROM ai_agent_template WHERE tts_voice_id = #{voiceId})")
    long countVoiceReferences(@Param("voiceId") String voiceId);
}
