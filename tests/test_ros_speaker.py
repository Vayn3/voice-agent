from __future__ import annotations

import unittest

from backend.app.services.ros_speaker import RobotSpeakerPublisher


class FakeRosStream:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, audio: bytes) -> None:
        self.writes.append(audio)

    def close(self) -> None:
        self.closed = True


class RobotSpeakerPublisherTests(unittest.TestCase):
    def test_publishes_exact_raw_s16le_bytes_and_preserves_sample_boundaries(self) -> None:
        streams: list[FakeRosStream] = []

        def factory(**kwargs: object) -> FakeRosStream:
            stream = FakeRosStream(**kwargs)
            streams.append(stream)
            return stream

        speaker = RobotSpeakerPublisher(
            enabled=True,
            topic="/audio",
            stream_factory=factory,
        )

        # A 16-bit sample split between websocket packets must remain one
        # sample on the ROS side; no header or Float32 conversion is added.
        speaker.publish(b"\x01")
        speaker.publish(b"\x02\x03\x04")

        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0].writes, [b"\x01\x02\x03\x04"])
        self.assertEqual(streams[0].kwargs["sample_rate"], 24000)
        self.assertEqual(streams[0].kwargs["channels"], 1)
        self.assertEqual(streams[0].kwargs["sample_width"], 2)
        self.assertEqual(streams[0].kwargs["duplex_mode"], "half")
        speaker.close()
        self.assertTrue(streams[0].closed)

    def test_disabled_publisher_never_opens_a_ros_stream(self) -> None:
        def factory(**kwargs: object) -> FakeRosStream:
            raise AssertionError("disabled publisher should not create a ROS stream")

        speaker = RobotSpeakerPublisher(enabled=False, stream_factory=factory)
        speaker.publish(b"\x00\x00")
        self.assertFalse(speaker.active)


if __name__ == "__main__":
    unittest.main()
