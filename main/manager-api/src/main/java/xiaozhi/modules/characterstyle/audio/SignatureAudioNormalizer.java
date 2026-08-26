package xiaozhi.modules.characterstyle.audio;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;

import javax.sound.sampled.AudioFileFormat;
import javax.sound.sampled.AudioFormat;
import javax.sound.sampled.AudioInputStream;
import javax.sound.sampled.AudioSystem;

import org.springframework.stereotype.Component;

import xiaozhi.common.exception.RenException;

@Component
public class SignatureAudioNormalizer {
    public static final int MAX_UPLOAD_BYTES = 5 * 1024 * 1024;
    public static final float OUTPUT_SAMPLE_RATE = 24_000F;
    public static final double MIN_DURATION_SECONDS = 0.2D;
    public static final double MAX_DURATION_SECONDS = 15D;

    public byte[] normalizeWav(byte[] upload) {
        if (upload == null || upload.length == 0) {
            throw new RenException("招牌录音不能为空");
        }
        if (upload.length > MAX_UPLOAD_BYTES) {
            throw new RenException("招牌录音超过 5MB 限制");
        }
        if (upload.length < 12
                || !asciiEquals(upload, 0, "RIFF")
                || !asciiEquals(upload, 8, "WAVE")) {
            throw new RenException("招牌录音必须是 RIFF/WAVE 文件");
        }

        try (AudioInputStream source = AudioSystem.getAudioInputStream(new ByteArrayInputStream(upload))) {
            AudioFormat sourceFormat = source.getFormat();
            float sourceRate = sourceFormat.getSampleRate();
            int channels = sourceFormat.getChannels();
            if (!Float.isFinite(sourceRate) || sourceRate < 8_000F || sourceRate > 96_000F) {
                throw new RenException("招牌录音采样率必须在 8kHz 到 96kHz 之间");
            }
            if (channels < 1 || channels > 2) {
                throw new RenException("招牌录音只支持单声道或双声道");
            }

            AudioFormat decodedFormat = new AudioFormat(
                    AudioFormat.Encoding.PCM_SIGNED,
                    sourceRate,
                    16,
                    channels,
                    channels * 2,
                    sourceRate,
                    false);
            if (!AudioSystem.isConversionSupported(decodedFormat, sourceFormat)) {
                throw new RenException("招牌录音必须是可解码的 WAV 音频");
            }

            byte[] decoded;
            try (AudioInputStream pcm = AudioSystem.getAudioInputStream(decodedFormat, source)) {
                decoded = readLimited(pcm, maxDecodedBytes(sourceRate, channels));
            }
            short[] mono = mixToMono(decoded, channels);
            double duration = mono.length / (double) sourceRate;
            if (duration < MIN_DURATION_SECONDS || duration > MAX_DURATION_SECONDS) {
                throw new RenException("招牌录音时长必须在 0.2 到 15 秒之间");
            }

            short[] normalized = resample(mono, sourceRate, OUTPUT_SAMPLE_RATE);
            byte[] pcmBytes = shortsToBytes(normalized);
            AudioFormat outputFormat = new AudioFormat(OUTPUT_SAMPLE_RATE, 16, 1, true, false);
            try (AudioInputStream output = new AudioInputStream(
                    new ByteArrayInputStream(pcmBytes), outputFormat, normalized.length);
                    ByteArrayOutputStream wav = new ByteArrayOutputStream()) {
                AudioSystem.write(output, AudioFileFormat.Type.WAVE, wav);
                return wav.toByteArray();
            }
        } catch (RenException error) {
            throw error;
        } catch (Exception error) {
            throw new RenException("招牌录音必须是可解码的 WAV 音频", error);
        }
    }

    private int maxDecodedBytes(float sampleRate, int channels) {
        return (int) Math.ceil(sampleRate * channels * 2D * (MAX_DURATION_SECONDS + 1D));
    }

    private byte[] readLimited(AudioInputStream input, int limit) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int read;
        while ((read = input.read(buffer)) != -1) {
            if (output.size() + read > limit) {
                throw new RenException("招牌录音时长超过 15 秒限制");
            }
            output.write(buffer, 0, read);
        }
        return output.toByteArray();
    }

    private short[] mixToMono(byte[] pcm, int channels) {
        int frameSize = channels * 2;
        if (pcm.length == 0 || pcm.length % frameSize != 0) {
            throw new RenException("招牌录音 PCM 数据不完整");
        }
        short[] mono = new short[pcm.length / frameSize];
        for (int frame = 0; frame < mono.length; frame++) {
            int total = 0;
            for (int channel = 0; channel < channels; channel++) {
                int offset = frame * frameSize + channel * 2;
                total += (short) ((pcm[offset] & 0xff) | (pcm[offset + 1] << 8));
            }
            mono[frame] = (short) (total / channels);
        }
        return mono;
    }

    private short[] resample(short[] source, float sourceRate, float targetRate) {
        if (sourceRate == targetRate) {
            return source;
        }
        int outputLength = Math.max(1, (int) Math.round(source.length * targetRate / sourceRate));
        short[] output = new short[outputLength];
        double scale = sourceRate / targetRate;
        for (int index = 0; index < outputLength; index++) {
            double sourcePosition = index * scale;
            int left = Math.min((int) sourcePosition, source.length - 1);
            int right = Math.min(left + 1, source.length - 1);
            double fraction = sourcePosition - left;
            output[index] = (short) Math.round(source[left] * (1D - fraction) + source[right] * fraction);
        }
        return output;
    }

    private byte[] shortsToBytes(short[] samples) {
        byte[] value = new byte[samples.length * 2];
        for (int index = 0; index < samples.length; index++) {
            value[index * 2] = (byte) samples[index];
            value[index * 2 + 1] = (byte) (samples[index] >>> 8);
        }
        return value;
    }

    private boolean asciiEquals(byte[] value, int offset, String expected) {
        if (value.length < offset + expected.length()) {
            return false;
        }
        for (int index = 0; index < expected.length(); index++) {
            if (value[offset + index] != (byte) expected.charAt(index)) {
                return false;
            }
        }
        return true;
    }
}
