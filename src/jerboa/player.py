import time
from collections import deque

import pyglet
from pyglet.gl import GL_TEXTURE_2D
from pyglet.media import buffered_logger as bl
from pyglet.media.drivers import get_audio_driver
from pyglet.media.codecs.base import Source, SourceGroup


class _AudioPlayerProperty:
    """Descriptor for Player attributes to forward to the AudioPlayer.

    We want the Player to have attributes like volume, pitch, etc. These are
    actually implemented by the AudioPlayer. So this descriptor will forward
    an assignement to one of the attributes to the AudioPlayer. For example
    `player.volume = 0.5` will call `player._audio_player.set_volume(0.5)`.

    The Player class has default values at the class level which are retrieved
    if not found on the instance.
    """

    def __init__(self, attribute, doc=None):
        self.attribute = attribute
        self.__doc__ = doc or ""

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        if "_" + self.attribute in obj.__dict__:
            return obj.__dict__["_" + self.attribute]
        return getattr(objtype, "_" + self.attribute)

    def __set__(self, obj, value):
        obj.__dict__["_" + self.attribute] = value
        if obj._audio_player:
            getattr(obj._audio_player, "set_" + self.attribute)(value)


class PlaybackTimer:
    def __init__(self):
        self._time = 0.0
        self._systime = None

    def start(self):
        self._systime = time.time()

    def pause(self):
        self._time = self.get_time()
        self._systime = None

    def reset(self):
        self._time = 0.0
        if self._systime is not None:
            self._systime = time.time()

    def get_time(self):
        if self._systime is None:
            now = self._time
        else:
            now = time.time() - self._systime + self._time
        return now

    def set_time(self, value):
        self.reset()
        self._time = value


class SLPlayer(pyglet.event.EventDispatcher):
    # Spacialisation attributes, preserved between audio players
    _volume = 1.0
    _min_distance = 1.0
    _max_distance = 100000000.0

    _position = (0, 0, 0)
    _pitch = 1.0

    _cone_orientation = (0, 0, 1)
    _cone_inner_angle = 360.0
    _cone_outer_angle = 360.0
    _cone_outer_gain = 1.0

    def __init__(self):
        """Initialize the Player with a MasterClock."""
        self._source = None
        self._playlists = deque()
        self._audio_player = None

        self._texture = None
        # Desired play state (not an indication of actual state).
        self._playing = False

        self._timer = PlaybackTimer()

    def __del__(self):
        """Release the Player resources."""
        self.delete()

    def start(self, new_source):
        """
        Set the source of the player and start playing it.

        Args:
            new_source (Source or Iterable[Source]): The source to play.
        """
        self.pause()
        self._timer.reset()
        if self._source:
            self.seek(0.0)  # Reset source to the beginning
            self.source.is_player_source = False

        if new_source is None:
            self._source = None
            self.delete()
        else:
            old_source = self._source
            self._source = new_source.get_queue_source()

            if self._audio_player:
                if old_source and old_source.audio_format == self._source.audio_format:
                    self._audio_player.clear()
                    self._audio_player.source = self._source
                else:
                    self._audio_player.delete()
                    self._audio_player = None
            if old_source and old_source.video_format != self._source.video_format:
                pyglet.clock.unschedule(self.update_texture)
                self._texture = None

            self._set_playing(True)

    def _set_playing(self, playing):
        # stopping = self._playing and not playing
        # starting = not self._playing and playing

        self._playing = playing

        if playing and self.source:
            self._init_media_players()

            if self._audio_player:
                self._audio_player.play()
            if self._texture:
                pyglet.clock.schedule_once(self.update_texture, 0)

            self._timer.start()
        else:
            self._timer.pause()
            pyglet.clock.unschedule(self.update_texture)
            if self._audio_player:
                self._audio_player.stop()

    def _init_media_players(self):
        if self.source.audio_format:
            if self._audio_player is None:
                self._create_audio_player()
            if self._audio_player:
                # We succesfully created an audio player
                self._audio_player.prefill_audio()

        if self.source.video_format:
            if not self._texture:
                self._create_texture()

    @property
    def playing(self):
        """
        bool: Read-only. Determine if the player state is playing.

        The *playing* property is irrespective of whether or not there is
        actually a source to play. If *playing* is ``True`` and a source is
        queued, it will begin to play immediately. If *playing* is ``False``,
        it is implied that the player is paused. There is no other possible
        state.
        """
        return self._playing

    def play(self):
        """Begin playing the current source.

        This has no effect if the player is already playing.
        """
        self._set_playing(True)

    def pause(self):
        """Pause playback of the current source.

        This has no effect if the player is already paused.
        """
        self._set_playing(False)

    def delete(self):
        """Release the resources acquired by this player.

        The internal audio player and the texture will be deleted.
        """
        if self._source:
            self.source.is_player_source = False
        if self._audio_player:
            self._audio_player.delete()
            self._audio_player = None
        if self._texture:
            self._texture = None

    def seek(self, timestamp):
        """
        Seek for playback to the indicated timestamp on the current source.

        Timestamp is expressed in seconds. If the timestamp is outside the
        duration of the source, it will be clamped to the end.

        Args:
            timestamp (float): The time where to seek in the source, clamped to the
                beginning and end of the source.
        """
        playing = self._playing
        if playing:
            self.pause()
        if not self.source:
            return

        timestamp = max(timestamp, 0)

        self._timer.set_time(timestamp)
        self._source.seek(timestamp)
        if self._audio_player:
            # XXX: According to docstring in AbstractAudioPlayer this cannot
            # be called when the player is not stopped
            self._audio_player.clear()
        if self.source.video_format:
            self.update_texture()
            pyglet.clock.unschedule(self.update_texture)
        self._set_playing(playing)

    def _create_audio_player(self):
        assert not self._audio_player
        assert self.source

        audio_driver = get_audio_driver()
        if audio_driver is None:
            # Failed to find a valid audio driver
            return

        self._audio_player = audio_driver.create_audio_player(self.source, self)

        # Set the audio player attributes
        for attr in (
            "volume",
            "_min_distance",
            "_max_distance",
            "_position",
            "pitch",
            "_cone_orientation",
            "_cone_inner_angle",
            "_cone_outer_angle",
            "_cone_outer_gain",
        ):
            value = getattr(self, attr)
            if attr.startswith("_"):
                attr = attr[len("_") :]
            setattr(self, attr, value)

    @property
    def source(self):
        """Source: Read-only. The current :class:`Source`, or ``None``."""
        return self._source

    @property
    def time(self):
        """
        float: Read-only. Current playback time of the current source.

        The playback time is a float expressed in seconds, with 0.0 being the
        beginning of the media. The playback time returned represents the
        player master clock time which is used to synchronize both the audio
        and the video.
        """
        return self._timer.get_time()

    def _create_texture(self):
        video_format = self.source.video_format
        self._texture = pyglet.image.Texture.create(
            video_format.width, video_format.height, GL_TEXTURE_2D
        )
        self._texture = self._texture.get_transform(flip_y=True)
        # After flipping the texture along the y axis, the anchor_y is set
        # to the top of the image. We want to keep it at the bottom.
        self._texture.anchor_y = 0
        return self._texture

    @property
    def texture(self):
        """
        :class:`pyglet.image.Texture`: Get the texture for the current video frame.

        You should call this method every time you display a frame of video,
        as multiple textures might be used. The return value will be None if
        there is no video in the current source.
        """
        return self._texture

    def seek_next_frame(self):
        """Step forwards one video frame in the current source."""
        time = self.source.get_next_video_timestamp()
        if time is None:
            return
        self.seek(time)

    def update_texture(self, dt=None):
        """Manually update the texture from the current source.

        This happens automatically, so you shouldn't need to call this method.

        Args:
            dt (float): The time elapsed since the last call to
                ``update_texture``.
        """
        # self.pr.disable()
        # if dt > 0.05:
        #     print("update_texture dt:", dt)
        #     import pstats
        #     ps = pstats.Stats(self.pr).sort_stats("cumulative")
        #     ps.print_stats()
        source = self.source
        time = self.time

        frame_rate = source.video_format.frame_rate
        frame_duration = 1 / frame_rate
        ts = source.get_next_video_timestamp()
        # Allow up to frame_duration difference
        while ts is not None and ts + frame_duration < time:
            source.get_next_video_frame()  # Discard frame
            ts = source.get_next_video_timestamp()

        if ts is None:
            # No more video frames to show. End of video stream.
            pyglet.clock.schedule_once(self._video_finished, 0)
            return
        elif ts > time:
            # update_texture called too early (probably manually!)
            pyglet.clock.schedule_once(self.update_texture, ts - time)
            return

        image = source.get_next_video_frame()
        if image is not None:
            if self._texture is None:
                self._create_texture()
            self._texture.blit_into(image, 0, 0, 0)

        ts = source.get_next_video_timestamp()
        if ts is None:
            delay = frame_duration
        else:
            delay = ts - time

        delay = max(0.0, delay)
        pyglet.clock.schedule_once(self.update_texture, delay)
        # self.pr.enable()

    def on_eos(self):
        ...

    volume = _AudioPlayerProperty(
        "volume",
        doc="""
    The volume level of sound playback.

    The nominal level is 1.0, and 0.0 is silence.

    The volume level is affected by the distance from the listener (if
    positioned).
    """,
    )

    pitch = _AudioPlayerProperty(
        "pitch",
        doc="""
    The pitch shift to apply to the sound.

    The nominal pitch is 1.0. A pitch of 2.0 will sound one octave higher,
    and play twice as fast. A pitch of 0.5 will sound one octave lower, and
    play twice as slow. A pitch of 0.0 is not permitted.
    """,
    )

    def on_driver_reset(self):
        """The audio driver has been reset, by default this will kill the current audio player and create a new one,
        and requeue the buffers. Any buffers that may have been queued in a player will be resubmitted.  It will
        continue from the last buffers submitted, not played and may cause sync issues if using video.

        :event:
        """
        if self._audio_player:
            self._audio_player.on_driver_reset()

            # Voice has been changed, will need to reset all options on the voice.
            for attr in (
                "volume",
                "min_distance",
                "max_distance",
                "position",
                "pitch",
                "cone_orientation",
                "cone_inner_angle",
                "cone_outer_angle",
                "cone_outer_gain",
            ):
                value = getattr(self, attr)
                setattr(self, attr, value)

            if self._playing:
                self._audio_player.play()


SLPlayer.register_event_type("on_eos")
SLPlayer.register_event_type("on_driver_reset")
