"""Publish realtime TTS PCM to the robot speaker ROS topic.

The wire format deliberately matches ``ros_voice/single_file_realtime_dialog.py``:
the payload is *raw* 24 kHz, mono, signed 16-bit little-endian PCM. In
particular, it must not be converted to Float32 and must not be wrapped in the
full-duplex FDPX frame, because the robot's normal ``/audio`` subscriber plays
the payload bytes directly.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable


LOGGER = logging.getLogger(__name__)

SAMPLE_RATE = 24_000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
SAMPLE_FORMAT = "pcm_s16le"


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class RobotSpeakerPublisher:
    """Lazy ROS1 speaker publisher for one browser voice-QA session.

    ROS is intentionally optional for local Windows development: if ``rospy``
    is unavailable the browser voice QA continues to work and a single warning
    is logged. On the robot, publishing is enabled by default.
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        topic: str | None = None,
        node_name: str | None = None,
        queue_size: int | None = None,
        stream_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.enabled = _env_flag("ROS_AUDIO_ENABLED", True) if enabled is None else enabled
        self.topic = topic or os.getenv("ROS_AUDIO_TOPIC", "/audio")
        self.node_name = node_name or os.getenv("ROS_AUDIO_NODE_NAME", "speaker_publisher")
        self.queue_size = queue_size or int(os.getenv("ROS_AUDIO_QUEUE_SIZE", "10"))
        self._stream_factory = stream_factory
        self._stream: Any | None = None
        self._start_attempted = False
        self._trailing_byte = b""
        self.error: str | None = None

    @property
    def active(self) -> bool:
        return self._stream is not None

    def start(self) -> bool:
        """Open the ROS publisher once and report whether it is usable."""
        if not self.enabled:
            return False
        if self._stream is not None:
            return True
        if self._start_attempted:
            return False

        self._start_attempted = True
        try:
            factory = self._stream_factory
            if factory is None:
                # Reuse the exact ROS message selection and byte publication
                # implementation used by the standalone robot dialogue script.
                from ros_voice.ros_audio import Ros1SpeakerStream

                factory = Ros1SpeakerStream
            self._stream = factory(
                topic=self.topic,
                node_name=self.node_name,
                queue_size=self.queue_size,
                latched=False,
                control_topic=os.getenv("ROS_AUDIO_CONTROL_TOPIC", "/audio/control"),
                duplex_mode="half",
                sample_rate=SAMPLE_RATE,
                channels=CHANNELS,
                sample_width=SAMPLE_WIDTH_BYTES,
            )
            LOGGER.info(
                "Robot speaker publishing enabled: topic=%s, format=%s, sample_rate=%s, channels=%s",
                self.topic,
                SAMPLE_FORMAT,
                SAMPLE_RATE,
                CHANNELS,
            )
            return True
        except Exception as exc:
            self.error = str(exc)
            LOGGER.warning(
                "Robot speaker is unavailable; TTS will continue in the browser only: %s",
                exc,
            )
            return False

    def publish(self, audio: bytes) -> None:
        """Publish raw s16le bytes, preserving sample boundaries across packets."""
        if not audio or not self.start():
            return

        pcm = self._trailing_byte + bytes(audio)
        if len(pcm) % SAMPLE_WIDTH_BYTES:
            self._trailing_byte = pcm[-1:]
            pcm = pcm[:-1]
        else:
            self._trailing_byte = b""

        if pcm:
            # ``write`` publishes raw PCM. Do not use ``write_framed`` here:
            # FDPX metadata would be treated as audible samples by /audio.
            try:
                self._stream.write(pcm)
            except Exception as exc:
                # A ROS transport failure must not end the browser dialogue.
                self.error = str(exc)
                LOGGER.warning("Failed to publish robot speaker PCM: %s", exc)
                try:
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None

    def close(self) -> None:
        if self._trailing_byte:
            LOGGER.warning("Discarded one incomplete 16-bit PCM byte at end of robot TTS stream.")
            self._trailing_byte = b""
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                LOGGER.exception("Failed to close robot speaker publisher")
            finally:
                self._stream = None
