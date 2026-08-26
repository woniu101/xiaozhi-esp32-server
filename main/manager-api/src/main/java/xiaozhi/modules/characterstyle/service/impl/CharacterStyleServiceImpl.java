package xiaozhi.modules.characterstyle.service.impl;

import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Date;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;

import lombok.RequiredArgsConstructor;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.service.impl.BaseServiceImpl;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.agent.dao.AgentDao;
import xiaozhi.modules.agent.entity.AgentEntity;
import xiaozhi.modules.characterstyle.audio.SignatureAudioNormalizer;
import xiaozhi.modules.characterstyle.dao.CharacterStyleDao;
import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.SignatureConfig;
import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.SignatureItem;
import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.SignatureTrialMatch;
import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.SignatureTrialRequest;
import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.SignatureTrialResult;
import xiaozhi.modules.characterstyle.dto.CharacterStyleDTO.Summary;
import xiaozhi.modules.characterstyle.entity.CharacterStyleEntity;
import xiaozhi.modules.characterstyle.service.CharacterStyleService;
import xiaozhi.modules.characterstyle.source.CharacterStyleArchiveParser;
import xiaozhi.modules.characterstyle.source.CharacterStyleArchiveParser.ParsedStyle;
import xiaozhi.modules.characterstyle.source.GitHubSourceDownloader;
import xiaozhi.modules.characterstyle.source.GitHubSourceDownloader.DownloadedSource;
import xiaozhi.modules.llm.service.LLMService;

@Service
@RequiredArgsConstructor
public class CharacterStyleServiceImpl
        extends BaseServiceImpl<CharacterStyleDao, CharacterStyleEntity>
        implements CharacterStyleService {
    private final CharacterStyleArchiveParser archiveParser;
    private final GitHubSourceDownloader githubDownloader;
    private final AgentDao agentDao;
    private final SignatureAudioNormalizer signatureAudioNormalizer;
    private final LLMService llmService;

    @Value("${character-style.storage-root:${CHARACTER_STYLE_DIR:data/character_styles}}")
    private String storageRoot;

    @Override
    public List<Summary> list(Long userId) {
        List<CharacterStyleEntity> entities = baseDao.selectList(
                new QueryWrapper<CharacterStyleEntity>()
                        .eq("user_id", userId)
                        .orderByDesc("updated_at"));
        List<Summary> result = new ArrayList<>(entities.size());
        for (CharacterStyleEntity entity : entities) {
            Summary item = new Summary();
            item.setId(entity.getId());
            item.setName(entity.getName());
            item.setSourceType(entity.getSourceType());
            item.setSourceUrl(entity.getSourceUrl());
            item.setSourceRef(entity.getSourceRef());
            item.setSourceHash(entity.getSourceHash());
            item.setCreatedAt(entity.getCreatedAt());
            item.setUpdatedAt(entity.getUpdatedAt());
            result.add(item);
        }
        return result;
    }

    @Override
    public CharacterStyleEntity getOwned(Long userId, String styleId) {
        if (StringUtils.isBlank(styleId)) {
            throw new RenException("人物风格 ID 不能为空");
        }
        CharacterStyleEntity entity = baseDao.selectById(styleId);
        if (entity == null) {
            throw new RenException("人物风格不存在");
        }
        if (userId == null || !userId.equals(entity.getUserId())) {
            throw new RenException(ErrorCode.NO_PERMISSION);
        }
        return entity;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public CharacterStyleEntity importZip(
            Long userId, String styleId, String name, byte[] archive) {
        ParsedStyle parsed = archiveParser.parse(archive, name);
        return persistImport(userId, styleId, name, "zip", null, null, parsed, null);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public CharacterStyleEntity importGitHub(
            Long userId, String styleId, String name, String sourceUrl, String sourceRef) {
        DownloadedSource downloaded = githubDownloader.download(sourceUrl, sourceRef);
        ParsedStyle parsed = archiveParser.parse(downloaded.artifact(), name);
        return persistImport(
                userId,
                styleId,
                name,
                "github",
                downloaded.sourceUrl(),
                downloaded.sourceRef(),
                parsed,
                downloaded.commit());
    }

    private CharacterStyleEntity persistImport(
            Long userId,
            String requestedStyleId,
            String name,
            String sourceType,
            String sourceUrl,
            String sourceRef,
            ParsedStyle parsed,
            String commit) {
        if (userId == null) {
            throw new RenException(ErrorCode.USER_NOT_LOGIN);
        }
        CharacterStyleEntity existing = null;
        String styleId = requestedStyleId;
        if (StringUtils.isBlank(styleId)) {
            styleId = UUID.randomUUID().toString().replace("-", "");
        } else {
            existing = getOwned(userId, styleId);
        }
        requireSafeStyleId(styleId);

        LinkedHashMap<String, Object> diagnostics = new LinkedHashMap<>(parsed.diagnostics());
        if (commit != null) {
            diagnostics.put("commit", commit);
        }

        SnapshotSwap snapshot = installSnapshot(styleId, parsed.snapshotFiles());
        try {
            Date now = new Date();
            CharacterStyleEntity entity = existing == null ? new CharacterStyleEntity() : existing;
            entity.setId(styleId);
            entity.setUserId(userId);
            entity.setName(name.trim());
            entity.setSourceType(sourceType);
            entity.setSourceUrl(sourceUrl);
            entity.setSourceRef(sourceRef);
            entity.setSourceHash(parsed.sourceHash());
            entity.setRawSkillText(parsed.rawSkillText());
            entity.setResolvedPrompt(parsed.resolvedPrompt());
            entity.setDiagnostics(JsonUtils.toJsonString(diagnostics));
            entity.setUpdatedAt(now);
            if (existing == null) {
                entity.setSignatureConfig(null);
                entity.setCreatedAt(now);
                requireUpdated(baseDao.insert(entity));
            } else {
                requireUpdated(baseDao.updateById(entity));
            }
            completeSnapshotWithTransaction(snapshot);
            return entity;
        } catch (RuntimeException error) {
            restoreSnapshot(snapshot);
            throw error;
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void delete(Long userId, String styleId) {
        getOwned(userId, styleId);
        List<AgentEntity> bindings = agentDao.selectList(
                new QueryWrapper<AgentEntity>()
                        .select("id", "agent_name")
                        .eq("character_style_id", styleId));
        if (!bindings.isEmpty()) {
            String names = bindings.stream()
                    .map(agent -> agent.getAgentName() + "(" + agent.getId() + ")")
                    .limit(10)
                    .reduce((left, right) -> left + "、" + right)
                    .orElse("");
            throw new RenException("人物风格仍被以下智能体使用，请先解除绑定：" + names);
        }
        baseDao.deleteById(styleId);
        Path styleRoot = styleRoot(styleId);
        afterCommit(() -> deleteTree(styleRoot));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void bind(Long userId, String agentId, String styleId) {
        getOwned(userId, styleId);
        AgentEntity agent = requireOwnedAgent(userId, agentId);
        requireUpdated(agentDao.updateCharacterStyleBinding(agent.getId(), styleId, userId));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void unbind(Long userId, String agentId) {
        AgentEntity agent = requireOwnedAgent(userId, agentId);
        requireUpdated(agentDao.updateCharacterStyleBinding(agent.getId(), null, userId));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public CharacterStyleEntity updateSignatureConfig(
            Long userId, String styleId, SignatureConfig requested) {
        CharacterStyleEntity style = getOwned(userId, styleId);
        SignatureConfig current = parseSignatureConfig(style);
        SignatureConfig normalized = normalizeSignatureConfig(requested, current);

        Set<String> retainedIds = new LinkedHashSet<>();
        for (SignatureItem item : normalized.getItems()) {
            retainedIds.add(item.getId());
        }
        List<Path> removedAudio = new ArrayList<>();
        for (SignatureItem oldItem : current.getItems()) {
            if (!retainedIds.contains(oldItem.getId()) && StringUtils.isNotBlank(oldItem.getAudioPath())) {
                removedAudio.add(signatureAudioPath(styleId, oldItem.getId()));
            }
        }

        style.setSignatureConfig(JsonUtils.toJsonString(normalized));
        style.setUpdatedAt(new Date());
        requireUpdated(baseDao.updateById(style));
        if (!removedAudio.isEmpty()) {
            afterCommit(() -> removedAudio.forEach(this::deleteFileQuietly));
        }
        return style;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public CharacterStyleEntity uploadSignatureAudio(
            Long userId, String styleId, String itemId, byte[] audio) {
        CharacterStyleEntity style = getOwned(userId, styleId);
        requireSafeSignatureId(itemId);
        SignatureConfig config = parseSignatureConfig(style);
        SignatureItem item = requireSignatureItem(config, itemId);
        byte[] normalizedAudio = signatureAudioNormalizer.normalizeWav(audio);

        AudioSwap swap = installSignatureAudio(styleId, itemId, normalizedAudio);
        try {
            item.setAudioPath(signatureRelativePath(itemId));
            style.setSignatureConfig(JsonUtils.toJsonString(config));
            style.setUpdatedAt(new Date());
            requireUpdated(baseDao.updateById(style));
            completeAudioWithTransaction(swap);
            return style;
        } catch (RuntimeException error) {
            restoreAudio(swap);
            throw error;
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public CharacterStyleEntity deleteSignatureAudio(Long userId, String styleId, String itemId) {
        CharacterStyleEntity style = getOwned(userId, styleId);
        requireSafeSignatureId(itemId);
        SignatureConfig config = parseSignatureConfig(style);
        SignatureItem item = requireSignatureItem(config, itemId);
        item.setAudioPath(null);
        style.setSignatureConfig(JsonUtils.toJsonString(config));
        style.setUpdatedAt(new Date());
        requireUpdated(baseDao.updateById(style));
        Path audio = signatureAudioPath(styleId, itemId);
        afterCommit(() -> deleteFileQuietly(audio));
        return style;
    }

    @Override
    public byte[] readSignatureAudio(Long userId, String styleId, String itemId) {
        CharacterStyleEntity style = getOwned(userId, styleId);
        requireSafeSignatureId(itemId);
        SignatureItem item = requireSignatureItem(parseSignatureConfig(style), itemId);
        if (!signatureRelativePath(itemId).equals(item.getAudioPath())) {
            throw new RenException("该招牌表达尚未上传主录音");
        }
        Path audio = signatureAudioPath(styleId, itemId);
        try {
            if (!Files.isRegularFile(audio)) {
                throw new RenException("招牌录音不存在");
            }
            byte[] value = Files.readAllBytes(audio);
            if (value.length == 0 || value.length > SignatureAudioNormalizer.MAX_UPLOAD_BYTES) {
                throw new RenException("招牌录音文件无效");
            }
            return value;
        } catch (RenException error) {
            throw error;
        } catch (IOException error) {
            throw new RenException("招牌录音读取失败", error);
        }
    }

    @Override
    public SignatureTrialResult trialSignatureContext(
            Long userId, String styleId, SignatureTrialRequest request) {
        if (request == null) {
            throw new RenException("人物上下文试跑请求不能为空");
        }
        CharacterStyleEntity style = getOwned(userId, styleId);
        AgentEntity agent = requireOwnedAgent(userId, request.getAgentId());
        SignatureConfig current = parseSignatureConfig(style);
        SignatureConfig requested = request.getSignatureConfig() == null
                ? current
                : request.getSignatureConfig();
        SignatureConfig trialConfig = normalizeSignatureConfig(requested, current);

        String assistantName = StringUtils.defaultIfBlank(agent.getAgentName(), "小智");
        String resolvedPrompt = StringUtils.defaultString(style.getResolvedPrompt())
                .replace("{{assistant_name}}", assistantName);
        if (StringUtils.isBlank(resolvedPrompt)) {
            throw new RenException("人物风格缺少最终提示词");
        }
        String prompt = appendSignatureAudioContract(styleId, resolvedPrompt, trialConfig);
        String modelOutput = llmService.generateReply(
                prompt,
                request.getUserText().trim(),
                agent.getLlmModelId());

        SignatureTrialResult result = new SignatureTrialResult();
        result.setModelOutput(modelOutput);
        result.setMatches(findTrialMatches(styleId, trialConfig, modelOutput));
        return result;
    }

    private String appendSignatureAudioContract(
            String styleId, String resolvedPrompt, SignatureConfig config) {
        if (config == null || !config.isEnabled()) {
            return resolvedPrompt;
        }
        List<SignatureItem> ready = config.getItems().stream()
                .filter(SignatureItem::isEnabled)
                .filter(item -> isSignatureAudioReady(styleId, item))
                .toList();
        if (ready.isEmpty()) {
            return resolvedPrompt;
        }
        StringBuilder contract = new StringBuilder(resolvedPrompt)
                .append("\n\n<signature_audio_contract>\n")
                .append("固定录音只改变播放来源，不改变人物何时使用招牌表达。")
                .append("只有当人物 Skill 和当前对话上下文本来就决定使用某条表达时，")
                .append("才原样输出下面对应的规范台词；录音可用本身不得提高使用频率。\n");
        for (SignatureItem item : ready) {
            contract.append("- ")
                    .append(item.getId())
                    .append(": ")
                    .append(JsonUtils.toJsonString(item.getDisplayText()))
                    .append('\n');
        }
        return contract.append("</signature_audio_contract>").toString();
    }

    private List<SignatureTrialMatch> findTrialMatches(
            String styleId, SignatureConfig config, String modelOutput) {
        List<TrialCandidate> candidates = new ArrayList<>();
        for (SignatureItem item : config.getItems()) {
            if (StringUtils.isNotBlank(item.getDisplayText())) {
                candidates.add(new TrialCandidate(item.getDisplayText(), item));
            }
            for (String alias : item.getAliases()) {
                if (StringUtils.isNotBlank(alias)) {
                    candidates.add(new TrialCandidate(alias, item));
                }
            }
        }
        candidates.sort(Comparator.comparingInt((TrialCandidate value) -> value.text().length()).reversed());
        String foldedOutput = modelOutput.toLowerCase(Locale.ROOT);
        Set<String> matchedItems = new LinkedHashSet<>();
        List<SignatureTrialMatch> matches = new ArrayList<>();
        for (TrialCandidate candidate : candidates) {
            SignatureItem item = candidate.item();
            if (matchedItems.contains(item.getId())) {
                continue;
            }
            int start = findBoundedIgnoreCase(foldedOutput, candidate.text());
            if (start < 0) {
                continue;
            }
            SignatureTrialMatch match = new SignatureTrialMatch();
            match.setItemId(item.getId());
            match.setMatchedText(modelOutput.substring(start, start + candidate.text().length()));
            match.setFixedAudio(config.isEnabled()
                    && item.isEnabled()
                    && isSignatureAudioReady(styleId, item));
            matches.add(match);
            matchedItems.add(item.getId());
        }
        return matches;
    }

    private int findBoundedIgnoreCase(String foldedOutput, String candidate) {
        String foldedCandidate = candidate.toLowerCase(Locale.ROOT);
        int from = 0;
        while (from <= foldedOutput.length() - foldedCandidate.length()) {
            int start = foldedOutput.indexOf(foldedCandidate, from);
            if (start < 0) {
                return -1;
            }
            int end = start + foldedCandidate.length();
            boolean startOk = !startsAsciiWord(candidate)
                    || start == 0
                    || !isAsciiWord(foldedOutput.charAt(start - 1));
            boolean endOk = !endsAsciiWord(candidate)
                    || end == foldedOutput.length()
                    || !isAsciiWord(foldedOutput.charAt(end));
            if (startOk && endOk) {
                return start;
            }
            from = start + 1;
        }
        return -1;
    }

    private boolean isSignatureAudioReady(String styleId, SignatureItem item) {
        if (!signatureRelativePath(item.getId()).equals(item.getAudioPath())) {
            return false;
        }
        return Files.isRegularFile(signatureAudioPath(styleId, item.getId()));
    }

    private boolean startsAsciiWord(String value) {
        return StringUtils.isNotEmpty(value) && isAsciiWord(value.charAt(0));
    }

    private boolean endsAsciiWord(String value) {
        return StringUtils.isNotEmpty(value) && isAsciiWord(value.charAt(value.length() - 1));
    }

    private boolean isAsciiWord(char value) {
        return value >= 'A' && value <= 'Z'
                || value >= 'a' && value <= 'z'
                || value >= '0' && value <= '9'
                || value == '_';
    }

    private record TrialCandidate(String text, SignatureItem item) {
    }

    private SignatureConfig parseSignatureConfig(CharacterStyleEntity style) {
        if (StringUtils.isBlank(style.getSignatureConfig())) {
            return new SignatureConfig();
        }
        try {
            SignatureConfig config = JsonUtils.parseObject(
                    style.getSignatureConfig(), SignatureConfig.class);
            if (config == null) {
                return new SignatureConfig();
            }
            if (config.getItems() == null) {
                config.setItems(new ArrayList<>());
            }
            return config;
        } catch (RuntimeException error) {
            throw new RenException("人物招牌语音配置已损坏", error);
        }
    }

    private SignatureConfig normalizeSignatureConfig(
            SignatureConfig requested, SignatureConfig current) {
        if (requested == null) {
            throw new RenException("招牌语音配置不能为空");
        }
        List<SignatureItem> requestedItems = requested.getItems() == null
                ? List.of()
                : requested.getItems();
        if (requestedItems.size() > 50) {
            throw new RenException("一个人物最多配置 50 条招牌表达");
        }

        Map<String, SignatureItem> oldById = new HashMap<>();
        for (SignatureItem oldItem : current.getItems()) {
            if (oldItem != null && oldItem.getId() != null) {
                oldById.put(oldItem.getId(), oldItem);
            }
        }

        Set<String> ids = new LinkedHashSet<>();
        Map<String, String> matchOwners = new HashMap<>();
        List<SignatureItem> normalizedItems = new ArrayList<>();
        for (SignatureItem requestedItem : requestedItems) {
            if (requestedItem == null) {
                throw new RenException("招牌表达不能为空");
            }
            String id = StringUtils.trimToEmpty(requestedItem.getId());
            requireSafeSignatureId(id);
            if (!ids.add(id)) {
                throw new RenException("招牌表达 ID 重复: " + id);
            }
            String displayText = StringUtils.trimToEmpty(requestedItem.getDisplayText());
            requireSignatureText(displayText, "模型输出原文");

            List<String> aliases = requestedItem.getAliases() == null
                    ? List.of()
                    : requestedItem.getAliases();
            if (aliases.size() > 20) {
                throw new RenException("单条招牌表达最多配置 20 个别名");
            }
            LinkedHashMap<String, String> uniqueAliases = new LinkedHashMap<>();
            for (String rawAlias : aliases) {
                String alias = StringUtils.trimToEmpty(rawAlias);
                requireSignatureText(alias, "识别别名");
                uniqueAliases.putIfAbsent(alias.toLowerCase(java.util.Locale.ROOT), alias);
            }

            registerMatchText(matchOwners, displayText, id);
            for (String alias : uniqueAliases.values()) {
                registerMatchText(matchOwners, alias, id);
            }

            SignatureItem item = new SignatureItem();
            item.setId(id);
            item.setDisplayText(displayText);
            item.setAliases(new ArrayList<>(uniqueAliases.values()));
            item.setEnabled(requestedItem.isEnabled());
            SignatureItem old = oldById.get(id);
            if (old != null && signatureRelativePath(id).equals(old.getAudioPath())) {
                item.setAudioPath(old.getAudioPath());
            }
            normalizedItems.add(item);
        }

        SignatureConfig normalized = new SignatureConfig();
        normalized.setEnabled(requested.isEnabled());
        normalized.setItems(normalizedItems);
        return normalized;
    }

    private void requireSignatureText(String value, String fieldName) {
        if (value.isBlank() || value.length() > 300 || value.indexOf('\0') >= 0) {
            throw new RenException(fieldName + "长度必须为 1 到 300 个字符");
        }
    }

    private void registerMatchText(Map<String, String> owners, String value, String itemId) {
        String key = value.toLowerCase(java.util.Locale.ROOT);
        String previous = owners.putIfAbsent(key, itemId);
        if (previous != null && !previous.equals(itemId)) {
            throw new RenException("不同招牌表达不能使用相同的原文或别名: " + value);
        }
    }

    private SignatureItem requireSignatureItem(SignatureConfig config, String itemId) {
        return config.getItems().stream()
                .filter(item -> item != null && itemId.equals(item.getId()))
                .findFirst()
                .orElseThrow(() -> new RenException("招牌表达不存在: " + itemId));
    }

    private void requireUpdated(int rows) {
        if (rows != 1) {
            throw new RenException("人物风格配置更新失败");
        }
    }

    private String signatureRelativePath(String itemId) {
        requireSafeSignatureId(itemId);
        return "signatures/" + itemId + ".wav";
    }

    private Path signatureAudioPath(String styleId, String itemId) {
        Path style = styleRoot(styleId);
        Path audio = style.resolve(signatureRelativePath(itemId)).normalize();
        if (!audio.startsWith(style)) {
            throw new RenException("招牌录音存储路径越界");
        }
        return audio;
    }

    private void requireSafeSignatureId(String itemId) {
        if (itemId == null || !itemId.matches("^[A-Za-z0-9_-]{1,64}$")) {
            throw new RenException("招牌表达 ID 不合法");
        }
    }

    private AudioSwap installSignatureAudio(String styleId, String itemId, byte[] audio) {
        Path finalFile = signatureAudioPath(styleId, itemId);
        Path directory = finalFile.getParent();
        Path tempFile = directory.resolve("." + itemId + "-" + UUID.randomUUID() + ".tmp");
        Path backupFile = directory.resolve("." + itemId + "-" + UUID.randomUUID() + ".bak");
        boolean hadPrevious = Files.exists(finalFile);
        AudioSwap swap = new AudioSwap(finalFile, backupFile, tempFile, hadPrevious);
        try {
            Files.createDirectories(directory);
            Files.write(tempFile, audio, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            if (hadPrevious) {
                moveAtomic(finalFile, backupFile);
            }
            moveAtomic(tempFile, finalFile);
            return swap;
        } catch (Exception error) {
            restoreAudio(swap);
            throw error instanceof RenException value
                    ? value
                    : new RenException("招牌录音保存失败", error);
        }
    }

    private void completeAudioWithTransaction(AudioSwap swap) {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            cleanupAudio(swap);
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCompletion(int status) {
                if (status == TransactionSynchronization.STATUS_COMMITTED) {
                    cleanupAudio(swap);
                } else {
                    restoreAudio(swap);
                }
            }
        });
    }

    private void cleanupAudio(AudioSwap swap) {
        deleteFileQuietly(swap.backupFile());
        deleteFileQuietly(swap.tempFile());
    }

    private void restoreAudio(AudioSwap swap) {
        try {
            Files.deleteIfExists(swap.finalFile());
            if (swap.hadPrevious() && Files.exists(swap.backupFile())) {
                moveAtomic(swap.backupFile(), swap.finalFile());
            }
        } catch (Exception ignored) {
            // Keep the backup next to the target so an operator can recover it.
        } finally {
            deleteFileQuietly(swap.tempFile());
        }
    }

    private void deleteFileQuietly(Path file) {
        try {
            if (file != null) {
                Files.deleteIfExists(file);
            }
        } catch (IOException ignored) {
            // A stale file is safer than failing a committed configuration update.
        }
    }

    private AgentEntity requireOwnedAgent(Long userId, String agentId) {
        AgentEntity agent = agentDao.selectById(agentId);
        if (agent == null) {
            throw new RenException(ErrorCode.AGENT_NOT_FOUND);
        }
        if (userId == null || !userId.equals(agent.getUserId())) {
            throw new RenException(ErrorCode.NO_PERMISSION);
        }
        return agent;
    }

    private SnapshotSwap installSnapshot(String styleId, Map<String, byte[]> files) {
        Path root = normalizedStorageRoot();
        Path stagingDirectory = root.resolve(".staging")
                .resolve(styleId + "-" + UUID.randomUUID().toString().replace("-", ""))
                .normalize();
        Path stagingSource = stagingDirectory.resolve("source");
        Path finalSource = styleRoot(styleId).resolve("source");
        Path backupSource = root.resolve(".staging")
                .resolve(styleId + "-backup-" + UUID.randomUUID().toString().replace("-", ""))
                .normalize();
        boolean hadPrevious = Files.exists(finalSource);
        try {
            Files.createDirectories(stagingSource);
            for (Map.Entry<String, byte[]> item : files.entrySet()) {
                Path target = stagingSource.resolve(item.getKey()).normalize();
                if (!target.startsWith(stagingSource)) {
                    throw new RenException("人物风格快照路径越界");
                }
                Files.createDirectories(target.getParent());
                Files.write(target, item.getValue());
            }
            Files.createDirectories(finalSource.getParent());
            if (hadPrevious) {
                moveAtomic(finalSource, backupSource);
            }
            moveAtomic(stagingSource, finalSource);
            return new SnapshotSwap(finalSource, backupSource, stagingDirectory, hadPrevious);
        } catch (Exception error) {
            SnapshotSwap failed = new SnapshotSwap(finalSource, backupSource, stagingDirectory, hadPrevious);
            restoreSnapshot(failed);
            throw error instanceof RenException value
                    ? value
                    : new RenException("人物风格源码快照写入失败", error);
        }
    }

    private void completeSnapshotWithTransaction(SnapshotSwap snapshot) {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            cleanupSnapshot(snapshot);
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCompletion(int status) {
                if (status == TransactionSynchronization.STATUS_COMMITTED) {
                    cleanupSnapshot(snapshot);
                } else {
                    restoreSnapshot(snapshot);
                }
            }
        });
    }

    private void cleanupSnapshot(SnapshotSwap snapshot) {
        deleteTree(snapshot.backupSource());
        deleteTree(snapshot.stagingDirectory());
    }

    private void restoreSnapshot(SnapshotSwap snapshot) {
        try {
            deleteTree(snapshot.finalSource());
            if (snapshot.hadPrevious() && Files.exists(snapshot.backupSource())) {
                Files.createDirectories(snapshot.finalSource().getParent());
                moveAtomic(snapshot.backupSource(), snapshot.finalSource());
            }
        } catch (Exception ignored) {
            // Preserve the original exception; a leftover backup remains recoverable.
        } finally {
            deleteTree(snapshot.stagingDirectory());
        }
    }

    private void moveAtomic(Path source, Path target) throws IOException {
        try {
            Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException error) {
            Files.move(source, target);
        }
    }

    private void afterCommit(Runnable action) {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            action.run();
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                action.run();
            }
        });
    }

    private Path normalizedStorageRoot() {
        return Path.of(storageRoot).toAbsolutePath().normalize();
    }

    private Path styleRoot(String styleId) {
        requireSafeStyleId(styleId);
        Path root = normalizedStorageRoot();
        Path style = root.resolve(styleId).normalize();
        if (!style.startsWith(root)) {
            throw new RenException("人物风格存储路径越界");
        }
        return style;
    }

    private void requireSafeStyleId(String styleId) {
        if (styleId == null || !styleId.matches("^[A-Za-z0-9_-]{1,64}$")) {
            throw new RenException("人物风格 ID 不合法");
        }
    }

    private void deleteTree(Path root) {
        if (root == null || !Files.exists(root)) {
            return;
        }
        Path storage = normalizedStorageRoot();
        Path normalized = root.toAbsolutePath().normalize();
        if (!normalized.startsWith(storage) || normalized.equals(storage)) {
            throw new RenException("拒绝删除人物风格存储根目录之外的路径");
        }
        try (var paths = Files.walk(normalized)) {
            paths.sorted(Comparator.reverseOrder()).forEach(path -> {
                try {
                    Files.deleteIfExists(path);
                } catch (IOException error) {
                    throw new SnapshotDeleteException(error);
                }
            });
        } catch (SnapshotDeleteException error) {
            throw new RenException("人物风格文件清理失败", error.getCause());
        } catch (IOException error) {
            throw new RenException("人物风格文件清理失败", error);
        }
    }

    private record SnapshotSwap(
            Path finalSource,
            Path backupSource,
            Path stagingDirectory,
            boolean hadPrevious) {
    }

    private record AudioSwap(
            Path finalFile,
            Path backupFile,
            Path tempFile,
            boolean hadPrevious) {
    }

    private static final class SnapshotDeleteException extends RuntimeException {
        private SnapshotDeleteException(IOException cause) {
            super(cause);
        }
    }
}
