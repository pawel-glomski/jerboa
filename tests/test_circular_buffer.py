import pytest

import math
import numpy as np
from typing import Callable

from jerboa.utils.circular_buffer import CircularBuffer

VALID_BUFFER_CASES = [
    ((0,), 0, np.float64),
    ((1,), 0, np.float32),
    ((2,), 0, np.float16),
    ((64,), 0, np.int64),
    ((0, 8), 0, np.int32),
    ((8, 0), 1, np.int16),
    ((8, 8), 0, np.int8),
    ((8, 8), 1, np.float64),
    ((4, 0, 4), 1, np.float32),
    ((4, 4, 4), 0, np.float16),
    ((4, 4, 4), 1, np.int64),
    ((4, 4, 4), 2, np.int32),
]
VALID_BUFFER_CASES_BY_NDIM = {}
for __buffer_args in VALID_BUFFER_CASES:
  VALID_BUFFER_CASES_BY_NDIM.setdefault(len(__buffer_args[0]), []).append(__buffer_args)

VALID_BUFFER_CASES_MINIMAL = [cases[-1] for cases in VALID_BUFFER_CASES_BY_NDIM.values()]

BufferArgs = tuple[tuple, int, np.dtype]  # shape, axis, dtype
BufferCreator = Callable[[tuple, int, np.dtype], CircularBuffer]


def create_elements(buffer: CircularBuffer, element_beg: int, element_end: int):
  if element_beg < 0:
    element_beg += len(buffer)
    element_end += len(buffer)

  element_shape = buffer.get_shape_for_data(min(1, element_end - element_beg))
  element_size = math.prod(element_shape)

  elements = []
  for idx in range(element_beg, element_end):
    element = np.arange(idx, idx + element_size, dtype=buffer.dtype)
    elements.append(element.reshape(element_shape))
  if elements:
    return np.concatenate(elements, buffer.index_axis, dtype=buffer.dtype)
  return np.ndarray(element_shape, buffer.dtype)


def create_empty_buffer(shape: tuple, axis: int, dtype: np.dtype) -> CircularBuffer:
  buffer = CircularBuffer(shape, axis, dtype)
  assert len(buffer) == 0
  return buffer


def create_filled_buffer(shape: tuple, axis: int, dtype: np.dtype,
                         elements_num: int) -> CircularBuffer:
  shape = list(shape)
  shape[axis] = shape[axis] if shape[axis] >= elements_num else elements_num + 1

  buffer = create_empty_buffer(shape, axis, dtype)
  buffer.put(create_elements(buffer, 0, elements_num))
  assert buffer.max_size >= len(buffer) == elements_num

  return buffer


def create_partially_filled_buffer(shape: tuple, axis: int, dtype: np.dtype) -> CircularBuffer:
  # to be partially filled, buffer needs to hold at least 1 element and still have space for at
  # least one more element
  if shape[axis] >= 2:
    buffer = create_filled_buffer(shape, axis, dtype, elements_num=shape[axis] // 2)
    assert 0 < len(buffer) < buffer.max_size

    return buffer
  pytest.skip("Not applicable test case")


def create_full_buffer(shape: tuple, axis: int, dtype: np.dtype) -> CircularBuffer:
  if shape[axis] > 0:  # to be full, buffer cannot be empty
    buffer = create_filled_buffer(shape, axis, dtype, elements_num=shape[axis])
    assert 0 < len(buffer) == buffer.max_size

    return buffer
  pytest.skip("Not applicable test case")


ALL_BUFFER_CREATORS = [create_empty_buffer, create_partially_filled_buffer, create_full_buffer]


class TestCircularBufferInit:

  @pytest.mark.parametrize('shape, axis', [
      ((), 0),
      ((), -1),
      ((), 1),
      ((1, 2), 2),
      ((1, 2, 3), -4),
  ])
  def test_init_should_raise_value_error_when_invalid_args(self, shape: tuple, axis: int):
    with pytest.raises(ValueError):
      CircularBuffer(shape, axis, np.float32)

  @pytest.mark.parametrize('shape, axis, dtype', [
      ((0,), 0, np.float32),
      ((1,), 0, np.float32),
      ((2, 3), 1, np.float16),
      ((1, 2, 0), 2, np.int8),
  ])
  def test_init_should_create_empty_buffer_when_valid_args(self, shape: tuple, axis: int,
                                                           dtype: np.dtype):
    buffer = CircularBuffer(shape, axis, dtype)

    assert len(buffer) == 0
    assert buffer.data.shape == shape
    assert buffer.dtype == dtype


class TestCircularBufferPut:

  @pytest.mark.parametrize('data', [
      np.ones((2, 3)),
      np.ones((1, 2, 2)),
      np.ones((1, 2, 0)),
      np.ones((1, 0)),
      np.ones((0, 1)),
  ])
  def test_put_should_raise_value_error_when_data_is_incompatible(self, data: np.ndarray):
    buffer = CircularBuffer((8,))

    with pytest.raises(ValueError):
      buffer.put(data)

  @pytest.mark.parametrize('elements_num', [1, 8])
  @pytest.mark.parametrize('buffer_args', VALID_BUFFER_CASES)
  def test_put_should_add_data_to_buffer_when_buffer_is_empty(self, buffer_args, elements_num: int):
    buffer = create_empty_buffer(*buffer_args)

    buffer.put(create_elements(buffer, 0, elements_num))

    assert len(buffer) == elements_num
    assert buffer.max_size >= elements_num

  @pytest.mark.parametrize('buffer_args', VALID_BUFFER_CASES)
  @pytest.mark.parametrize(
      'free_space_ratio',
      [
          0.5,  # does not overflow
          1.0,  # fills
          2.0,  # overflows
      ])
  def test_put_should_add_data_to_buffer_when_buffer_is_partially_filled(
      self, buffer_args, free_space_ratio: float):
    buffer = create_partially_filled_buffer(*buffer_args)
    buffer_size_before = len(buffer)

    free_space = buffer.max_size - len(buffer)
    elements_to_put_num = math.ceil(free_space * free_space_ratio)
    elements_to_put = create_elements(buffer, 0, elements_to_put_num)

    buffer.put(elements_to_put)
    assert len(buffer) == buffer_size_before + elements_to_put_num
    assert buffer.max_size >= len(buffer)

  @pytest.mark.parametrize('buffer_args', VALID_BUFFER_CASES)
  def test_put_should_add_data_to_buffer_when_buffer_is_full(self, buffer_args: BufferArgs):
    buffer = create_full_buffer(*buffer_args)
    buffer_size_before = len(buffer)
    elements_to_put_num = 5

    buffer.put(create_elements(buffer, 0, elements_to_put_num))
    assert len(buffer) == buffer_size_before + elements_to_put_num
    assert buffer.max_size >= len(buffer)


class TestCircularBufferResize:

  @pytest.mark.parametrize('elements_num, new_max_size', [
      (1, 0),
      (2, 0),
      (2, 1),
      (3, 2),
  ])
  @pytest.mark.parametrize('buffer_args', VALID_BUFFER_CASES_MINIMAL)
  def test_resize_should_raise_value_error_when_new_max_is_less_than_size(
      self, elements_num: int, new_max_size: int, buffer_args: BufferArgs):
    buffer = create_filled_buffer(*buffer_args, elements_num=elements_num)

    with pytest.raises(ValueError):
      buffer.resize(new_max_size)

  @pytest.mark.parametrize('elements_num, new_max_size', [
      (0, 0),
      (1, 1),
      (1, 2),
      (2, 3),
      (3, 5),
  ])
  @pytest.mark.parametrize('buffer_args', VALID_BUFFER_CASES_MINIMAL)
  def test_resize_should_change_buffer_max_size_when_new_max_size_is_bigger_than_size(
      self, elements_num: int, new_max_size: int, buffer_args: BufferArgs):
    buffer = create_filled_buffer(*buffer_args, elements_num=elements_num)
    buffer_len_before = len(buffer)

    buffer.resize(new_max_size)

    assert buffer.max_size == new_max_size
    assert len(buffer) == buffer_len_before


class TestCircularBufferPop:

  @pytest.mark.parametrize('buffer_creator', ALL_BUFFER_CREATORS)
  @pytest.mark.parametrize('buffer_args', VALID_BUFFER_CASES)
  def test_pop_should_raise_value_error_when_pop_size_is_greater_than_buffer_size(
      self, buffer_creator: BufferCreator, buffer_args: BufferArgs):
    buffer = buffer_creator(*buffer_args)
    with pytest.raises(ValueError):
      buffer.pop(len(buffer) + 1)

  @pytest.mark.parametrize('buffer_creator', ALL_BUFFER_CREATORS)
  @pytest.mark.parametrize('buffer_args', VALID_BUFFER_CASES)
  def test_pop_should_remove_nothing_and_return_empty_array_when_pop_size_is_zero(
      self, buffer_creator: BufferCreator, buffer_args: BufferArgs):
    buffer = buffer_creator(*buffer_args)
    buffer_size_before = len(buffer)

    removed_element = buffer.pop(0)

    assert removed_element.shape[buffer.index_axis] == 0
    assert len(buffer) == buffer_size_before

  @pytest.mark.parametrize('buffer_args', VALID_BUFFER_CASES)
  def test_pop_should_remove_and_return_requested_elements(self, buffer_args: BufferArgs):
    buffer = create_filled_buffer(*buffer_args, elements_num=8)

    expected_data1 = create_elements(buffer, 0, 2)  # 0, 1
    expected_data2 = create_elements(buffer, 2, 6)  # 2, 3, 4, 5
    expected_data3 = create_elements(buffer, 6, 8)  # 6, 7

    assert np.array_equal(buffer.pop(2), expected_data1)
    assert np.array_equal(buffer.pop(4), expected_data2)
    assert np.array_equal(buffer.pop(2), expected_data3)

  @pytest.mark.parametrize('buffer_creator', ALL_BUFFER_CREATORS)
  @pytest.mark.parametrize('buffer_args', VALID_BUFFER_CASES)
  def test_clear_should_remove_all_elements(self, buffer_creator: BufferCreator,
                                            buffer_args: BufferArgs):
    buffer = buffer_creator(*buffer_args)
    buffer_max_size_before = buffer.max_size

    buffer.clear()

    assert len(buffer) == 0
    assert buffer.max_size == buffer_max_size_before

  @pytest.mark.parametrize('buffer_creator', ALL_BUFFER_CREATORS)
  @pytest.mark.parametrize('buffer_args', VALID_BUFFER_CASES_MINIMAL)
  @pytest.mark.parametrize('idx_offset', [-1024, 0, 1, 10, 100])
  def test_getitem_should_raise_index_error_when_index_out_of_range(self,
                                                                    buffer_creator: BufferCreator,
                                                                    buffer_args: BufferArgs,
                                                                    idx_offset: int):
    buffer = buffer_creator(*buffer_args)

    with pytest.raises(IndexError):
      _ = buffer[len(buffer) + idx_offset]

  @pytest.mark.parametrize('buffer_args', VALID_BUFFER_CASES_MINIMAL)
  @pytest.mark.parametrize('idx', [-1, 0, 1, 8, 15])
  def test_getitem_should_return_correct_element_when_valid_index(self, buffer_args: BufferArgs,
                                                                  idx: int):
    buffer = create_empty_buffer(*buffer_args)
    buffer.put(create_elements(buffer, 0, 16))

    expected_element = create_elements(buffer, idx, idx + 1)

    assert np.array_equal(buffer[idx], expected_element)