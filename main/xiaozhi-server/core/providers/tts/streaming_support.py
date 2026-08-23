import asyncio
import audioop
from io import BytesIO
import queue
import traceback
import wave

from config.logger import setup_logging
from core.providers.tts.dto.dto import ContentType, InterfaceType, SentenceType
from core.utils import textUtils
from core.utils.tts import MarkdownCleaner


TAG = __name__
logger = setup_logging()


class StreamingPcmTranscoder:
    """Incrementally resample signed 16-bit mono PCM and emit device packets."""

    def __init__(self, source_rate, target_rate, output_format, opus_encoder, callback):
        self.source_rate = int(source_rate)
        self.target_rate = int(target_rate)
        self.output_format = output_format
        self.opus_encoder = opus_encoder
        self.callback = callback
        self._rate_state = None
        self._source_tail = b""
        self._pcm_buffer = bytearray()
        self._frame_bytes = int(self.target_rate * 0.06 * 2)
        self.input_bytes = 0
        self.output_bytes = 0

    def feed(self, data: bytes) -> None:
        if not data:
            return
        self.input_bytes += len(data)
        source = self._source_tail + bytes(data)
        even_length = len(source) - (len(source) % 2)
        self._source_tail = source[even_length:]
        source = source[:even_length]
        if not source:
            return

        if self.source_rate != self.target_rate:
            converted, self._rate_state = audioop.ratecv(
                source,
                2,
                1,
                self.source_rate,
                self.target_rate,
                self._rate_state,
            )
        else:
            converted = source
        if not converted:
            return
        self.output_bytes += len(converted)

        if self.output_format == "pcm":
            self._pcm_buffer.extend(converted)
            while len(self._pcm_buffer) >= self._frame_bytes:
                frame = bytes(self._pcm_buffer[: self._frame_bytes])
                del self._pcm_buffer[: self._frame_bytes]
                self.callback(frame)
            return

        self.opus_encoder.encode_pcm_to_opus_stream(
            converted,
            end_of_stream=False,
            callback=self.callback,
        )

    def finish(self) -> None:
        # An odd trailing byte cannot form a 16-bit PCM sample and is discarded.
        self._source_tail = b""
        if self.output_format == "pcm":
            if self._pcm_buffer:
                frame = bytes(self._pcm_buffer)
                frame += b"\x00" * (self._frame_bytes - len(frame))
                self.callback(frame)
                self._pcm_buffer.clear()
            return
        self.opus_encoder.encode_pcm_to_opus_stream(
            b"",
            end_of_stream=True,
            callback=self.callback,
        )


class SingleStreamTTSMixin:
    """Reusable queue, cancellation and PCM transport for HTTP streaming TTS."""

    def configure_single_stream(self, enabled: bool) -> None:
        self.streaming_enabled = bool(enabled)
        if self.streaming_enabled:
            self.interface_type = InterfaceType.SINGLE_STREAM
        self._stream_transcoder = None
        self._stream_segment_text = None
        self._stream_segment_announced = False
        self._active_stream_loop = None
        self._active_stream_response = None
        self._stream_packet_count = 0

    def cancel_current_synthesis(self) -> None:
        super().cancel_current_synthesis()
        loop = self._active_stream_loop
        response = self._active_stream_response
        if loop is not None and response is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(response.close)
            except RuntimeError:
                pass

    def register_active_stream(self, response) -> None:
        self._active_stream_loop = asyncio.get_running_loop()
        self._active_stream_response = response

    def clear_active_stream(self, response) -> None:
        if self._active_stream_response is response:
            self._active_stream_response = None
            self._active_stream_loop = None

    def ensure_stream_transcoder(self, source_rate: int) -> StreamingPcmTranscoder:
        target_rate = int(self.conn.sample_rate)
        if (
            self._stream_transcoder is None
            or self._stream_transcoder.source_rate != int(source_rate)
            or self._stream_transcoder.target_rate != target_rate
        ):
            if self._stream_transcoder is not None:
                self._stream_transcoder.finish()
            opus_encoder = getattr(self, "opus_encoder", None)
            if self.conn.audio_format != "pcm" and opus_encoder is None:
                raise RuntimeError("流式 Opus 编码器尚未初始化")
            self._stream_transcoder = StreamingPcmTranscoder(
                source_rate=source_rate,
                target_rate=target_rate,
                output_format=self.conn.audio_format,
                opus_encoder=opus_encoder,
                callback=self._handle_stream_packet,
            )
        return self._stream_transcoder

    def _handle_stream_packet(self, packet: bytes) -> None:
        if self.synthesis_cancelled():
            return
        if not self._stream_segment_announced:
            self.tts_audio_queue.put(
                (
                    SentenceType.FIRST,
                    None,
                    self._stream_segment_text,
                    getattr(self, "current_sentence_id", None),
                )
            )
            self._stream_segment_announced = True
        self._stream_packet_count += 1
        self.handle_opus(packet)

    def _reset_stream_state(self) -> None:
        self._stream_transcoder = None
        self._stream_segment_text = None
        self._stream_segment_announced = False
        self._stream_packet_count = 0
        if hasattr(self, "opus_encoder") and self.opus_encoder is not None:
            self.opus_encoder.reset_state()

    def _finish_stream_state(self) -> None:
        if self._stream_transcoder is not None and not self.synthesis_cancelled():
            self._stream_transcoder.finish()
        self._stream_transcoder = None

    def feed_wav_to_stream(self, audio: bytes) -> int:
        """Decode a WAV response and feed it through the active device stream."""
        if not audio or not audio.startswith(b"RIFF"):
            raise RuntimeError("TTS 降级响应不是有效 WAV 音频")
        with wave.open(BytesIO(audio), "rb") as wav_file:
            source_rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            pcm = wav_file.readframes(wav_file.getnframes())
        if channels == 2:
            pcm = audioop.tomono(pcm, sample_width, 0.5, 0.5)
        elif channels != 1:
            raise RuntimeError(f"TTS WAV 声道数不受支持: {channels}")
        if sample_width != 2:
            pcm = audioop.lin2lin(pcm, sample_width, 2)
        transcoder = self.ensure_stream_transcoder(source_rate)
        for offset in range(0, len(pcm), self.stream_chunk_size):
            if self.synthesis_cancelled():
                break
            transcoder.feed(pcm[offset : offset + self.stream_chunk_size])
        return len(pcm)

    def _run_stream_segment(self, text: str) -> None:
        original_text = text
        cleaned = MarkdownCleaner.clean_markdown(text)
        if self._correct_words_pattern:
            cleaned = self._correct_words_pattern.sub(
                lambda match: self.correct_words[match.group(0)], cleaned
            )
        if not cleaned or self.synthesis_cancelled():
            return
        self._stream_segment_text = original_text
        self._stream_segment_announced = False
        asyncio.run(self.stream_text_to_speak(cleaned))

    def _run_remaining_stream_text(self) -> None:
        full_text = "".join(self.tts_text_buff)
        remaining_text = full_text[self.processed_chars :]
        if remaining_text:
            segment_text = textUtils.get_string_no_punctuation_or_emoji(remaining_text)
            if segment_text:
                self._run_stream_segment(segment_text)
        self.processed_chars = len(full_text)

    def tts_text_priority_thread(self):
        if not self.streaming_enabled:
            return super().tts_text_priority_thread()

        while not self.conn.stop_event.is_set():
            try:
                message = self.tts_text_queue.get(timeout=1)
                if self.conn.client_abort:
                    self.cancel_current_synthesis()
                    continue
                if message.sentence_id != self.conn.sentence_id:
                    continue

                if message.sentence_type == SentenceType.FIRST:
                    self.current_sentence_id = message.sentence_id
                    self.apply_expression_plan(
                        message.expression_plan,
                        sentence_id=message.sentence_id,
                        turn_id=message.turn_id,
                    )
                    self.reset_synthesis_cancel()
                    self.tts_stop_request = False
                    self.processed_chars = 0
                    self.tts_text_buff = []
                    self.is_first_sentence = True
                    self.before_stop_play_files.clear()
                    self._reset_stream_state()
                elif ContentType.TEXT == message.content_type:
                    self.tts_text_buff.append(message.content_detail)
                    segment_text = self._get_segment_text()
                    if segment_text:
                        self._run_stream_segment(segment_text)
                elif ContentType.FILE == message.content_type:
                    if message.content_file:
                        self._process_audio_file_stream(
                            message.content_file,
                            callback=lambda audio: self.handle_audio_file(
                                audio, message.content_detail
                            ),
                        )

                if message.sentence_type == SentenceType.LAST:
                    self._run_remaining_stream_text()
                    self._finish_stream_state()
                    if not self.synthesis_cancelled():
                        self._process_before_stop_play_files()

            except queue.Empty:
                continue
            except Exception as exc:
                logger.bind(tag=TAG).error(
                    f"处理单流式TTS失败: {exc}, 类型: {type(exc).__name__}, "
                    f"堆栈: {traceback.format_exc()}"
                )
                if not self.synthesis_cancelled():
                    self.tts_audio_queue.put(
                        (
                            SentenceType.LAST,
                            [],
                            None,
                            getattr(self, "current_sentence_id", None),
                        )
                    )
