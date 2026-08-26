package xiaozhi.modules.characterstyle.audio;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;

import javax.sound.sampled.AudioFileFormat;
import javax.sound.sampled.AudioFormat;
import javax.sound.sampled.AudioInputStream;
import javax.sound.sampled.AudioSystem;

import org.junit.jupiter.api.Test;

import xiaozhi.common.exception.RenException;

class SignatureAudioNormalizerTest {
    private final SignatureAudioNormalizer normalizer = new SignatureAudioNormalizer();

    @Test
    void normalizesStereoWavToMonoPcmAtTwentyFourKhz() throws Exception {
        byte[] upload = wav(16_000F, 2, 1.0D);

        byte[] value = normalizer.normalizeWav(upload);

        try (AudioInputStream audio = AudioSystem.getAudioInputStream(new ByteArrayInputStream(value))) {
            assertEquals(24_000F, audio.getFormat().getSampleRate());
            assertEquals(1, audio.getFormat().getChannels());
            assertEquals(16, audio.getFormat().getSampleSizeInBits());
            assertEquals(AudioFormat.Encoding.PCM_SIGNED, audio.getFormat().getEncoding());
            assertEquals(24_000, audio.getFrameLength());
        }
    }

    @Test
    void rejectsNonAudioAndOutOfRangeDuration() throws Exception {
        assertThrows(RenException.class, () -> normalizer.normalizeWav("not wav".getBytes()));
        assertThrows(RenException.class, () -> normalizer.normalizeWav(audio(16_000F, 1, 1D,
                AudioFileFormat.Type.AIFF)));
        assertThrows(RenException.class, () -> normalizer.normalizeWav(wav(16_000F, 1, 0.1D)));
        assertThrows(RenException.class, () -> normalizer.normalizeWav(wav(8_000F, 1, 16D)));
    }

    private byte[] wav(float sampleRate, int channels, double seconds) throws Exception {
        return audio(sampleRate, channels, seconds, AudioFileFormat.Type.WAVE);
    }

    private byte[] audio(float sampleRate, int channels, double seconds, AudioFileFormat.Type type)
            throws Exception {
        int frames = (int) Math.round(sampleRate * seconds);
        byte[] pcm = new byte[frames * channels * 2];
        for (int frame = 0; frame < frames; frame++) {
            short sample = (short) Math.round(Math.sin(frame * 0.08D) * 8_000D);
            for (int channel = 0; channel < channels; channel++) {
                int offset = (frame * channels + channel) * 2;
                pcm[offset] = (byte) sample;
                pcm[offset + 1] = (byte) (sample >>> 8);
            }
        }
        AudioFormat format = new AudioFormat(sampleRate, 16, channels, true, false);
        try (AudioInputStream input = new AudioInputStream(
                new ByteArrayInputStream(pcm), format, frames);
                ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            AudioSystem.write(input, type, output);
            return output.toByteArray();
        }
    }
}
