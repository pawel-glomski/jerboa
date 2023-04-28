# import pytest
# from common import TEST_REC_PATH, TEST_REC_CHANNELS

# import av
# from speechless.avsource import StreamDecoder, MediaType
# from speechless.timeline_changes import RangeSet


# def test_decoder_with_valid_file_should_decode_correct_file():
#   decoder = StreamDecoder(TEST_REC_PATH, 0)
#   assert decoder.container.name == TEST_REC_PATH


# def test_decoder_with_missing_file_should_throw():
#   with pytest.raises(av.error.FileNotFoundError):
#     StreamDecoder('missing_video.mp4', 0)


# @pytest.mark.parametrize('filepath, stream_idx',
#                          [(TEST_REC_PATH, TEST_REC_CHANNELS[MediaType.Video]),
#                           (TEST_REC_PATH, TEST_REC_CHANNELS[MediaType.Audio])])
# def test_decoder_with_valid_stream_should_decode_correct_stream(filepath, stream_idx):
#   decoder = StreamDecoder(filepath, stream_idx)
#   assert stream_idx == decoder.stream.index


# @pytest.mark.parametrize('filepath, stream_idx', [(TEST_REC_PATH, len(TEST_REC_CHANNELS)),
#                                                   (TEST_REC_PATH, -1)])
# def test_decoder_with_invalid_stream_should_throw(filepath, stream_idx):
#   with pytest.raises(ValueError):
#     StreamDecoder(filepath, stream_idx)


# def test_seek():
#   frame_filter = RangeSet((2, 3), (7, 8))
#   decoder = StreamDecoder(
#       TEST_REC_PATH,
#       0,
#   )

#   frame_filter.sub(2.5, 3)
#   seek_time = 0
#   decoder.queue_seek(seek_time)
#   frame = decoder.pop()

#   decoder.queue_seek(seek_time, new_frame_filter=frame_filter)
#   frame = decoder.pop()
#   assert frame.original_timestamp > 11


# def test_update_frame_filter():
#   frame_filter = RangeSet((0, 1))
#   decoder = StreamDecoder(TEST_REC_PATH, 0, init_frame_filter=frame_filter)

#   frame_filter.add(5, 10)
#   decoder.update_frame_filter(frame_filter)

#   frame_filter.sub(5, 10)
#   # b = SkipList()
#   # b.add_range(0, 10, skip=True)

#   # a_1 = avsource.StreamDecoder(TEST_REC_PATH, 0, b)
#   # a_2 = avsource.StreamDecoder(TEST_REC_PATH, 1, b)
#   # decoders = [a_1, a_2]
#   # for decoder in decoders:
#   #   decoder.remove_skip_range(0, 5)
#   #   decoder.seek(timestamp)

#   # skip_list.remove_range(0, 5)
#   # decoder.turn_edits_off()
#   # decoder.turn_edits_on()

#   # decoding_task = decoder._decode(new_skip_list)
#   # decoding_task.stop()

#   # impl = ImplClass()
#   # obj1 = OtherClass(impl)
#   # obj2 = OtherClass(impl)
#   # impl.change()
