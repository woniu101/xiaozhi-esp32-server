package xiaozhi.modules.persona.source;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

import xiaozhi.common.exception.RenException;

class GitHubSourceDownloaderTest {
    private final GitHubSourceDownloader downloader = new GitHubSourceDownloader();

    @Test
    void parsesTreeRefWithoutNetworkAccess() {
        GitHubSourceDownloader.SourceDescriptor value = downloader.parse(
                "https://github.com/titanwings/example/tree/release-v1", null);
        assertEquals("titanwings", value.owner());
        assertEquals("example", value.repository());
        assertEquals("release-v1", value.ref());
    }

    @Test
    void rejectsPortsCredentialsAndTraversalRefs() {
        assertThrows(RenException.class,
                () -> downloader.parse("https://github.com:8443/owner/repo", null));
        assertThrows(RenException.class,
                () -> downloader.parse("https://user@github.com/owner/repo", null));
        assertThrows(RenException.class,
                () -> downloader.parse("https://github.com/owner/repo", "../secret"));
    }

    @Test
    void resolvesHeadBranchAndPeeledTagFromGitAdvertisement() {
        String head = "a".repeat(40);
        String branch = "b".repeat(40);
        String tagObject = "c".repeat(40);
        String tagCommit = "d".repeat(40);
        byte[] advertisement = ("001e# service=git-upload-pack\n0000"
                + "0050" + head + " HEAD\0symref=HEAD:refs/heads/main\n"
                + "003d" + branch + " refs/heads/main\n"
                + "003e" + tagObject + " refs/tags/v1\n"
                + "0041" + tagCommit + " refs/tags/v1^{}\n0000")
                .getBytes(StandardCharsets.ISO_8859_1);

        assertEquals(head, GitHubSourceDownloader.parseAdvertisedRef(advertisement, "HEAD"));
        assertEquals(branch, GitHubSourceDownloader.parseAdvertisedRef(advertisement, "main"));
        assertEquals(tagCommit, GitHubSourceDownloader.parseAdvertisedRef(advertisement, "v1"));
        assertNull(GitHubSourceDownloader.parseAdvertisedRef(advertisement, "missing"));
    }
}
