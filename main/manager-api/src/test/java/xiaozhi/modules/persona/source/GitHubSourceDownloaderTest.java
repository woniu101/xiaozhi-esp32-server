package xiaozhi.modules.persona.source;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

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
}
