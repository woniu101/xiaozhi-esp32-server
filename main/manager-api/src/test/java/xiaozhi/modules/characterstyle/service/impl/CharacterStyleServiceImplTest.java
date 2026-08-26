package xiaozhi.modules.characterstyle.service.impl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.test.util.ReflectionTestUtils;
import org.mockito.ArgumentCaptor;

import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.agent.dao.AgentDao;
import xiaozhi.modules.agent.entity.AgentEntity;
import xiaozhi.modules.characterstyle.audio.SignatureAudioNormalizer;
import xiaozhi.modules.characterstyle.dao.CharacterStyleDao;
import xiaozhi.modules.characterstyle.entity.CharacterStyleEntity;
import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.SignatureConfig;
import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.SignatureItem;
import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.SignatureTrialRequest;
import xiaozhi.modules.characterstyle.source.CharacterStyleArchiveParser;
import xiaozhi.modules.characterstyle.source.CharacterStyleArchiveParser.ParsedStyle;
import xiaozhi.modules.characterstyle.source.GitHubSourceDownloader;
import xiaozhi.modules.llm.service.LLMService;

class CharacterStyleServiceImplTest {

    @TempDir
    Path storage;

    @Test
    void failedDatabaseUpdateRestoresPreviousSourceSnapshot() throws Exception {
        CharacterStyleArchiveParser parser = mock(CharacterStyleArchiveParser.class);
        CharacterStyleDao dao = mock(CharacterStyleDao.class);
        LinkedHashMap<String, byte[]> files = new LinkedHashMap<>();
        files.put("SKILL.md", "new source".getBytes(StandardCharsets.UTF_8));
        ParsedStyle parsed = new ParsedStyle(
                files,
                "new source",
                "<character_style>new source</character_style>",
                "new-hash",
                Map.of("includedFiles", List.of()));
        when(parser.parse(any(byte[].class), anyString())).thenReturn(parsed);

        CharacterStyleEntity existing = new CharacterStyleEntity();
        existing.setId("rabbit");
        existing.setUserId(7L);
        existing.setName("old");
        existing.setSignatureConfig("{\"enabled\":false,\"items\":[]}");
        when(dao.selectById("rabbit")).thenReturn(existing);
        when(dao.updateById(any(CharacterStyleEntity.class))).thenReturn(0);

        CharacterStyleServiceImpl service = new CharacterStyleServiceImpl(
                parser,
                mock(GitHubSourceDownloader.class),
                mock(AgentDao.class),
                mock(SignatureAudioNormalizer.class),
                mock(LLMService.class));
        ReflectionTestUtils.setField(service, "baseDao", dao);
        ReflectionTestUtils.setField(service, "storageRoot", storage.toString());
        Path oldSkill = storage.resolve("rabbit/source/SKILL.md");
        Files.createDirectories(oldSkill.getParent());
        Files.writeString(oldSkill, "old source", StandardCharsets.UTF_8);

        assertThrows(
                RenException.class,
                () -> service.importZip(7L, "rabbit", "兔娘", new byte[] { 1 }));

        assertEquals("old source", Files.readString(oldSkill, StandardCharsets.UTF_8));
    }

    @Test
    void contextTrialUsesSkillForSemanticsAndReportsDeterministicAudioRouting() throws Exception {
        CharacterStyleDao dao = mock(CharacterStyleDao.class);
        AgentDao agentDao = mock(AgentDao.class);
        LLMService llmService = mock(LLMService.class);

        SignatureItem signature = new SignatureItem();
        signature.setId("ciallo");
        signature.setDisplayText("Ciallo～(∠・ω< )⌒★");
        signature.setAliases(List.of());
        signature.setAudioPath("signatures/ciallo.wav");
        signature.setEnabled(true);
        SignatureConfig config = new SignatureConfig();
        config.setEnabled(true);
        config.setItems(List.of(signature));

        CharacterStyleEntity style = new CharacterStyleEntity();
        style.setId("rabbit");
        style.setUserId(7L);
        style.setResolvedPrompt("兔娘原始 Skill，助手名是 {{assistant_name}}");
        style.setSignatureConfig(JsonUtils.toJsonString(config));
        when(dao.selectById("rabbit")).thenReturn(style);

        AgentEntity agent = new AgentEntity();
        agent.setId("agent-1");
        agent.setUserId(7L);
        agent.setAgentName("小兔");
        agent.setLlmModelId("LLM_deepseek");
        when(agentDao.selectById("agent-1")).thenReturn(agent);
        when(llmService.generateReply(anyString(), anyString(), anyString()))
                .thenReturn("哪个啊？你不说我怎么知——Ciallo～(∠・ω< )⌒★");

        CharacterStyleServiceImpl service = new CharacterStyleServiceImpl(
                mock(CharacterStyleArchiveParser.class),
                mock(GitHubSourceDownloader.class),
                agentDao,
                mock(SignatureAudioNormalizer.class),
                llmService);
        ReflectionTestUtils.setField(service, "baseDao", dao);
        ReflectionTestUtils.setField(service, "storageRoot", storage.toString());
        Path audio = storage.resolve("rabbit/signatures/ciallo.wav");
        Files.createDirectories(audio.getParent());
        Files.write(audio, new byte[] { 1, 2, 3 });

        SignatureTrialRequest request = new SignatureTrialRequest();
        request.setAgentId("agent-1");
        request.setUserText("兔娘，想听那个了");
        var result = service.trialSignatureContext(7L, "rabbit", request);

        assertEquals(1, result.getMatches().size());
        assertTrue(result.getMatches().get(0).isFixedAudio());
        ArgumentCaptor<String> prompt = ArgumentCaptor.forClass(String.class);
        verify(llmService).generateReply(prompt.capture(), eq("兔娘，想听那个了"), eq("LLM_deepseek"));
        assertTrue(prompt.getValue().contains("兔娘原始 Skill，助手名是 小兔"));
        assertTrue(prompt.getValue().contains("录音可用本身不得提高使用频率"));
        assertTrue(prompt.getValue().contains("Ciallo～(∠・ω< )⌒★"));
    }
}
