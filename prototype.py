# %%
import av
import sys
from PySide6.QtCore import Qt, QTimer, QIODevice, QSize
from PySide6.QtGui import QImage, QColorSpace, QPixmap, QPixelFormat, QKeyEvent, qPixelFormatYuv
from PySide6.QtMultimedia import (
    QAudioFormat,
    QAudioSink,
    QAudio,
    QMediaDevices,
    QVideoFrame,
    QVideoFrameFormat,
)
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

from jerboa.media.player.decoding.timeline_decoder import (
    TimelineDecoder,
    JbVideoFrame,
    JbAudioFrame,
)
from jerboa.media.player.decoding.skipping_decoder import SkippingDecoder, SimpleDecoder
from jerboa.media import standardized_audio as std_audio
from jerboa.media.core import MediaType, AudioConfig, VideoConfig
from jerboa.core.timeline import FragmentedTimeline, TMSection


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.audio_player: AudioPlayer = None
        # self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, a0: QKeyEvent):
        if a0.key() == Qt.Key.Key_Space:
            if self.audio_player.audio_sink.state() == QAudio.State.SuspendedState:
                self.audio_player.start()
            else:
                self.audio_player.stop()
        super().keyPressEvent(a0)


class JBAudioSourceDevice(QIODevice):
    def __init__(self, jb_decoder: TimelineDecoder):
        assert jb_decoder.stream_info.media_type == MediaType.AUDIO

        QIODevice.__init__(self)

        self.decoder = jb_decoder
        self.open(QIODevice.ReadOnly)

    def readData(self, maxSize) -> bytes:
        audio_config: AudioConfig = self.decoder.dst_media_config

        sample_size_in_bytes = audio_config.channels_num * audio_config.format.bytes
        wanted_samples_num = int(maxSize / sample_size_in_bytes)
        audio = self.decoder.pop(wanted_samples_num)
        if audio is not None:
            return audio.signal.tobytes()
        return -1

    def writeData(self, _) -> int:
        return 0  # Not implemented as we're only reading audio data

    def bytesAvailable(self):
        return 2048 * 8 + super().bytesAvailable()


class AudioPlayer:
    def __init__(self, audio_decoder: TimelineDecoder):
        jb_audio_cofnig = audio_decoder.dst_media_config
        self.format = QAudioFormat()
        self.format.setSampleRate(jb_audio_cofnig.sample_rate)
        self.format.setChannelCount(jb_audio_cofnig.channels_num)
        self.format.setSampleFormat(QAudioFormat.SampleFormat.Float)

        output_device = QMediaDevices.defaultAudioOutput()
        x = output_device.supportedSampleFormats()
        if not output_device.isFormatSupported(self.format):
            self.format = output_device.nearestFormat(self.format)

        # print([dev.description() for dev in QMediaDevices.audioOutputs()])
        self.audio_source = JBAudioSourceDevice(audio_decoder)

        self.audio_sink = QAudioSink(QMediaDevices.defaultAudioOutput(), self.format)
        self.audio_sink.start(self.audio_source)

    def start(self):
        self.audio_sink.resume()

    def stop(self):
        self.audio_sink.suspend()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.setWindowTitle("Video Player")

    # label = QLabel(window)
    # label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    # window.setCentralWidget(label)

    video_widget = QVideoWidget()
    window.setCentralWidget(video_widget)

    video_sink = video_widget.videoSink()

    container = av.open("out.mp4")
    # container = av.open("colors_test.mp4")
    # container = av.open("tests/test_recordings/test.mp4")
    # container = av.open(
    #     "https://rr4---sn-u2oxu-bqod.googlevideo.com/videoplayback?expire=1694836685&ei=bdMEZZiPFfiVv_IPjL6S6As&ip=37.47.230.231&id=o-AEe6z7oMkLgFHFo31rPWFtAUqEvJkFKnLp0-PdJv4_6G&itag=243&source=youtube&requiressl=yes&mh=Nr&mm=31%2C29&mn=sn-u2oxu-bqod%2Csn-u2oxu-f5fr&ms=au%2Crdu&mv=m&mvi=4&pl=27&initcwndbps=802500&vprv=1&svpuc=1&mime=video%2Fwebm&gir=yes&clen=67302645&dur=5465.726&lmt=1692505602512043&mt=1694814608&fvip=5&keepalive=yes&fexp=24007246&beids=24350018&c=IOS&txp=5437434&sparams=expire%2Cei%2Cip%2Cid%2Citag%2Csource%2Crequiressl%2Cvprv%2Csvpuc%2Cmime%2Cgir%2Cclen%2Cdur%2Clmt&sig=AOq0QJ8wRgIhAJqw8fdKOpkeFYXCPs0HGwLnkx8szm29lhY6BjTgQgRiAiEAhRwYJL8L_izZ4G1AOBculimZo5NouFwNNRQIawOg-QQ%3D&lsparams=mh%2Cmm%2Cmn%2Cms%2Cmv%2Cmvi%2Cpl%2Cinitcwndbps&lsig=AG3C_xAwRgIhAIyMKHbIW8rg5czSGWwwSRAdgNSpCpoSmiIedfZXW7ZDAiEA80p_uXubeCA_jrmaGIYq4E20Mze7u_Hid-RDThsyWf8%3D"
    # )
    audio_stream = container.streams.audio[0]

    timeline = FragmentedTimeline(
        TMSection(0, 5, modifier=0.5),
        TMSection(5, 15, modifier=0.0),
        TMSection(15, float("inf"), modifier=1.5),
    )
    audio_decoder = TimelineDecoder(
        skipping_decoder=SkippingDecoder(
            simple_decoder=SimpleDecoder(container.name, media_type=MediaType.AUDIO, stream_idx=0)
        ),
        dst_media_config=AudioConfig(
            format=std_audio.FORMAT.packed,
            layout=audio_stream.layout,
            sample_rate=audio_stream.sample_rate,
        ),
        init_timeline=timeline,
    )
    video_decoder = TimelineDecoder(
        skipping_decoder=SkippingDecoder(
            simple_decoder=SimpleDecoder(container.name, media_type=MediaType.VIDEO, stream_idx=0)
        ),
        dst_media_config=VideoConfig(
            format=VideoConfig.PixelFormat.RGBA8888,
        ),
        init_timeline=timeline,
    )

    player = AudioPlayer(audio_decoder)
    window.audio_player = player

    video_stream = container.streams.video[0]

    timer = QTimer()
    timer.setSingleShot(True)
    current_frame: JbAudioFrame | JbVideoFrame | None = None

    def update_frame():
        global current_frame

        audio_time = player.audio_sink.processedUSecs() / 1e6

        if current_frame is not None:
            time_diff = current_frame.timepoint - audio_time
            # can display it a bit earlier (up to 1ms sooner)
            if time_diff <= 1e-3:
                # image = QImage(
                #     current_frame.data.tobytes(),
                #     current_frame.data.shape[1],
                #     current_frame.data.shape[0],
                #     QImage.Format.Format_RGB888,
                # )

                qformat = QVideoFrameFormat(
                    QSize(current_frame.width, current_frame.height),
                    QVideoFrameFormat.PixelFormat.Format_RGBA8888,
                )
                qformat.setColorSpace(QVideoFrameFormat.ColorSpace.ColorSpace_AdobeRgb)
                qformat.setColorTransfer(QVideoFrameFormat.ColorTransfer.ColorTransfer_ST2084)
                qformat.setColorRange(QVideoFrameFormat.ColorRange.ColorRange_Video)
                qframe = QVideoFrame(qformat)

                qframe.map(QVideoFrame.MapMode.ReadWrite)
                for plane_idx in range(qframe.planeCount()):
                    plane = qframe.bits(plane_idx)
                    plane[:] = current_frame.planes[plane_idx]
                qframe.unmap()

                video_sink.setVideoFrame(qframe)
                # label.setPixmap(QPixmap.fromImage(image))
                current_frame = None

        if current_frame is None:
            frame = video_decoder.pop()
            while frame is not None and frame.timepoint - audio_time < 0:
                frame = video_decoder.pop()
            current_frame = frame

        if current_frame is not None:
            timer.start(max(0, int((current_frame.timepoint - audio_time) * 1e3)))

    timer.timeout.connect(update_frame)
    timer.start(0)

    player.start()
    window.show()
    # sys.exit(app.exec())
    app.exec()

    import atexit

    def cleanup():
        import typing

        for cleanup in typing._cleanups:
            cleanup()

    atexit.register(cleanup)

# %%

# import av
# import numpy as np
# import errno

# # Load the audio file
# container = av.open("tests/test.mp4")
# stream = container.streams.audio[0]

# # Set the start and end time for the section to be sped up
# start_time = 10.0
# end_time = 20.0

# # Create a filter graph
# graph = av.filter.Graph()
# in_buffer = graph.add_abuffer(template=stream,)
# # split = graph.add("asplit", "2")
# # atempo1 = graph.add("atempo", "1.0")
# atempo2 = graph.add("atempo", "2.5")
# # aformat1 = graph.add("aformat", sample_rates=str(stream.rate),
# #                                      sample_fmts=stream.format.name,
# #                                      channel_layouts=stream.layout.name)
# aformat2 = graph.add("aformat",
#                      sample_rates=str(stream.rate),
#                      sample_fmts=stream.format.name,
#                      channel_layouts=stream.layout.name)

# # sink1 = graph.add("abuffersink")
# sink2 = graph.add("abuffersink")

# in_buffer.link_to(atempo2)
# atempo2.link_to(aformat2)
# aformat2.link_to(sink2)

# # in_buffer.link_to(split)
# # split.link_to(atempo1, 0)
# # split.link_to(atempo2, 1)
# # split.link_to(atempo1)
# # atempo1.link_to(aformat1)
# # atempo2.link_to(aformat2)
# # aformat1.link_to(sink1)
# # aformat2.link_to(sink2)

# graph.configure()

# container_out = av.open("out.mp4", 'w')
# stream_out = container_out.add_stream(template=stream)
# stream_out.thread_type = 'AUTO'
# container_out.start_encoding()

# # https://github.com/PyAV-Org/PyAV/blob/main/av/audio/resampler.pyx
# for pkt in container.demux(stream):
#   for frame in pkt.decode():
#     data = frame.to_ndarray()
#     data = data[:, :1024]
#     new_frame = av.AudioFrame.from_ndarray(data, frame.format.name, frame.layout.name)
#     new_frame.pts = frame.pts
#     new_frame.time_base = frame.time_base
#     new_frame.sample_rate = frame.sample_rate
#     graph.push(new_frame)
#     new_frame.pts += 1024
#     graph.push(new_frame)
#     new_frame.pts += 1024
#     graph.push(new_frame)
#     new_frame.pts += 1024
#     graph.push(new_frame)
#     new_frame.pts += 1024
#     graph.push(new_frame)
#     graph.push(None)
#   while True:
#     try:
#       frame = sink2.pull()
#       ...
#     except EOFError:
#       break
#     except av.utils.AVError as e:
#       if e.errno != errno.EAGAIN:
#         raise
#       break

# %%

# import sys
# import time
# from PySide6.QtCore import Qt, Signal, QThreadPool, Slot
# from PySide6.QtWidgets import QApplication, QMainWindow
# from PySide6.QtGui import QKeyEvent


# class MainWindow(QMainWindow):
#     signal = Signal(float)

#     def __init__(self):
#         super().__init__()
#         self._thread_pool = QThreadPool()

#         self.signal.connect(self.callback)

#     @Slot(float)
#     def callback(self, emit_time):
#         print(f"delay={time.time() - emit_time}")

#     def keyPressEvent(self, a0: QKeyEvent):
#         if a0.key() == Qt.Key.Key_Space:
#             self._thread_pool.start(self.job)
#         super().keyPressEvent(a0)

#     def job(self):
#         time.sleep(1)
#         self.signal.emit(time.time())
#         # self.callback(time.time_ns())


# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     window = MainWindow()
#     window.setWindowTitle("Video Player")
#     window.show()

#     sys.exit(app.exec())
