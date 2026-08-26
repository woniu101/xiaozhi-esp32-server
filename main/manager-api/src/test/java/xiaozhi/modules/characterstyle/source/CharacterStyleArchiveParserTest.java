package xiaozhi.modules.characterstyle.source;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import org.apache.commons.compress.archivers.zip.ZipArchiveEntry;
import org.apache.commons.compress.archivers.zip.ZipArchiveOutputStream;
import org.apache.commons.compress.archivers.zip.UnixStat;
import org.junit.jupiter.api.Test;

import xiaozhi.common.exception.RenException;
import xiaozhi.modules.characterstyle.source.CharacterStyleArchiveParser.ParsedStyle;

class CharacterStyleArchiveParserTest {
    private final CharacterStyleArchiveParser parser = new CharacterStyleArchiveParser();

    @Test
    void removesOnlyFrontmatterAndPreservesBodyReferencesAndExamples() throws Exception {
        LinkedHashMap<String, String> files = new LinkedHashMap<>();
        files.put("rabbit-main/SKILL.md", "---\nname: rabbit\ndescription: package metadata\n---\n"
                + "# 兔娘\n原句一字不改。\n\n参考 [口癖](references/phrases.md)。\n"
                + "## 对话示例\n用户：你好\n兔娘：Ciallo~\n");
        files.put("rabbit-main/references/phrases.md", "# 口癖\n先说 Ciallo，再接原来的节奏。\n");
        files.put("rabbit-main/references/unreferenced.md", "不应进入最终提示词\n");
        files.put("rabbit-main/scripts/install.sh", "rm -rf /tmp/example\n");

        ParsedStyle value = parser.parse(zip(files), "兔娘");

        String expectedBody = "# 兔娘\n原句一字不改。\n\n参考 [口癖](references/phrases.md)。\n"
                + "## 对话示例\n用户：你好\n兔娘：Ciallo~\n";
        assertEquals(expectedBody, value.rawSkillText());
        assertTrue(value.resolvedPrompt().contains(expectedBody));
        assertTrue(value.resolvedPrompt().contains(
                "<character_source path=\"references/phrases.md\">\n# 口癖\n先说 Ciallo，再接原来的节奏。"));
        assertFalse(value.resolvedPrompt().contains("不应进入最终提示词"));
        assertEquals(
                java.util.List.of("references/phrases.md"),
                value.diagnostics().get("includedFiles"));
        assertTrue(value.snapshotFiles().containsKey("references/unreferenced.md"));
        assertFalse(value.snapshotFiles().containsKey("scripts/install.sh"));
    }

    @Test
    void recursivelyIncludesExplicitTextReferencesInStableSourceOrder() throws Exception {
        Map<String, String> files = Map.of(
                "SKILL.md", "先读 [B](b.md)，再读 `a.md`。",
                "a.md", "A",
                "b.md", "B，继续读 [C](nested/c.md)。",
                "nested/c.md", "C");

        ParsedStyle value = parser.parse(zip(files), "test");

        assertEquals(
                java.util.List.of("b.md", "a.md", "nested/c.md"),
                value.diagnostics().get("includedFiles"));
        assertTrue(value.resolvedPrompt().indexOf("path=\"b.md\"")
                < value.resolvedPrompt().indexOf("path=\"a.md\""));
    }

    @Test
    void resolvesUniqueBacktickFileNamesWithoutWeakeningMarkdownLinks() throws Exception {
        Map<String, String> files = Map.of(
                "SKILL.md", "先读 [合成资料](references/synthesis.md)。",
                "references/synthesis.md", "写作样本见 `01-writings.md`。普通文本里的 `not-packaged.md` 不是强制链接。",
                "references/research/01-writings.md", "原始写作样本");

        ParsedStyle value = parser.parse(zip(files), "兔娘");

        assertEquals(
                java.util.List.of(
                        "references/synthesis.md",
                        "references/research/01-writings.md"),
                value.diagnostics().get("includedFiles"));
        assertTrue(value.resolvedPrompt().contains("path=\"references/research/01-writings.md\""));

        assertThrows(RenException.class, () -> parser.parse(
                zip(Map.of("SKILL.md", "[严格链接](references/not-packaged.md)")), "兔娘"));
    }

    @Test
    void skipsExistingDirectoryNavigationButFollowsItsExplicitIndexEntries() throws Exception {
        Map<String, String> files = Map.of(
                "SKILL.md", "读 [导航](references/README.md)。",
                "references/README.md", "[研究目录](research/)\n[01](research/01.md)",
                "references/research/01.md", "研究原文");

        ParsedStyle value = parser.parse(zip(files), "兔娘");

        assertEquals(
                java.util.List.of("references/README.md", "references/research/01.md"),
                value.diagnostics().get("includedFiles"));
    }

    @Test
    void doesNotAppendSkillEntryAgainWhenAnIndexLinksBackToIt() throws Exception {
        Map<String, String> files = Map.of(
                "SKILL.md", "读 [导航](references/README.md)。",
                "references/README.md", "返回 [入口](../SKILL.md)。");

        ParsedStyle value = parser.parse(zip(files), "test");

        assertEquals(
                java.util.List.of("references/README.md"),
                value.diagnostics().get("includedFiles"));
    }

    @Test
    void rejectsTraversalMissingReferencesSecretsAndPromptOverflow() throws Exception {
        assertThrows(RenException.class, () -> parser.parse(
                zip(Map.of("../SKILL.md", "bad")), "test"));
        assertThrows(RenException.class, () -> parser.parse(
                zip(Map.of("SKILL.md", "[missing](references/no.md)")), "test"));
        assertThrows(RenException.class, () -> parser.parse(
                zip(Map.of("SKILL.md", "token: github_pat_abcdefghijklmnopqrstuvwxyz123456")), "test"));
        assertThrows(RenException.class, () -> parser.parse(
                zip(Map.of("SKILL.md", "读取 /root/private/config.yaml")), "test"));
        assertThrows(RenException.class, () -> parser.parse(
                zip(Map.of("SKILL.md", "x".repeat(CharacterStyleArchiveParser.MAX_PROMPT_CHARS))), "test"));
    }

    @Test
    void rejectsUnixSymlinks() throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ZipArchiveOutputStream zip = new ZipArchiveOutputStream(bytes)) {
            ZipArchiveEntry skill = new ZipArchiveEntry("SKILL.md");
            zip.putArchiveEntry(skill);
            zip.write("# test".getBytes(StandardCharsets.UTF_8));
            zip.closeArchiveEntry();
            ZipArchiveEntry link = new ZipArchiveEntry("references/escape.md");
            link.setUnixMode(UnixStat.LINK_FLAG | 0777);
            zip.putArchiveEntry(link);
            zip.write("../../outside".getBytes(StandardCharsets.UTF_8));
            zip.closeArchiveEntry();
        }

        assertThrows(RenException.class, () -> parser.parse(bytes.toByteArray(), "test"));
    }

    @Test
    void contentHashDoesNotDependOnZipEntryOrder() throws Exception {
        LinkedHashMap<String, String> left = new LinkedHashMap<>();
        left.put("SKILL.md", "body");
        left.put("notes.md", "note");
        LinkedHashMap<String, String> right = new LinkedHashMap<>();
        right.put("notes.md", "note");
        right.put("SKILL.md", "body");

        assertEquals(
                parser.parse(zip(left), "test").sourceHash(),
                parser.parse(zip(right), "test").sourceHash());
    }

    private byte[] zip(Map<String, String> files) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(bytes, StandardCharsets.UTF_8)) {
            for (Map.Entry<String, String> item : files.entrySet()) {
                zip.putNextEntry(new ZipEntry(item.getKey()));
                zip.write(item.getValue().getBytes(StandardCharsets.UTF_8));
                zip.closeEntry();
            }
        }
        return bytes.toByteArray();
    }
}
