import numpy as np

GROWTH_MULTIPLIER = 1.1


class CircularBuffer:
    """Circular buffer implemented using NumPy."""

    def __init__(self, shape: tuple = (8,), index_axis: int = 0, dtype: np.dtype = np.float64):
        """
        Initializes the circular buffer.

        Args:
          shape (tuple): Shape of the buffer, excluding the index axis.
          index_axis (int): Index axis along which to store the data.
          dtype (np.dtype): Data type of the buffer.
        """
        self.data = np.zeros(shape, dtype=dtype)
        self._axis = index_axis
        self._head = self._tail = self._size = 0
        try:
            shape[index_axis]
        except IndexError as exc:
            raise ValueError(f"Wrong index axis! {index_axis=}, {shape=}.") from exc

    def __repr__(self) -> str:
        return np.concatenate(self._get(self._size), self._axis).__repr__()

    def __str__(self) -> str:
        return np.concatenate(self._get(self._size), self._axis).__str__()

    def __len__(self) -> int:
        """
        Returns:
          int: Number of elements currently in the buffer.
        """
        return self._size

    def __getitem__(self, idx: int) -> np.ndarray:
        """Receives a single element at the specified index, without removing it from the buffer.
        Args:
          idx (int): Index of the element to receive.

        Returns:
          np.ndarray: The requested element.
        """
        if idx < 0:
            idx = len(self) + idx
        if not (0 <= idx < self._size):
            raise IndexError(f"Index out of range: {idx=}, {self._size=}")

        idx = (self._head + idx) % self.max_size
        return self.data[self._index_samples(idx, idx + 1)]

    def _index_samples(self, beg: int, end: int) -> tuple[slice]:
        indices = [slice(None) for _ in range(self.data.ndim)]
        indices[self._axis] = slice(beg, end)
        return tuple(indices)

    @property
    def index_axis(self) -> int:
        """
        Returns:
          int: The axis used to index elements.
        """
        return self._axis

    @property
    def max_size(self) -> int:
        """
        Returns:
          int: Maximum number of elements that can be stored in the buffer.
        """
        return self.data.shape[self._axis]

    @property
    def dtype(self) -> np.dtype:
        """
        Returns:
          int: The type of the data.
        """
        return self.data.dtype

    def get_shape_for_data(self, elements_num: int) -> tuple:
        """
        Returns:
          tuple: Shape for data with the number of elements equal to `elements_num`
        """
        shape = list(self.data.shape)
        shape[self.index_axis] = elements_num
        return tuple(shape)

    def resize(self, new_max_size: int):
        """
        Resizes the underyling buffer to a new size.

        Args:
          new_max_size (int): The new maximum size for the buffer.

        Raises:
          ValueError: If the new buffer won't be able to hold current number of elements.
        """
        if new_max_size < self._size:
            raise ValueError("New size cannot fit current contents!")
        if new_max_size == self.max_size:
            return

        data_part1, data_part2 = self._get(self._size)
        data1_size, data2_size = data_part1.shape[self._axis], data_part2.shape[self._axis]

        self._head = 0
        self._tail = data1_size + data2_size
        self._size = data1_size + data2_size

        new_shape = list(self.data.shape)
        new_shape[self._axis] = new_max_size
        self.data = np.zeros(new_shape, dtype=self.dtype)

        write_indices = [slice(None) for _ in range(self.data.ndim)]

        write_indices[self._axis] = slice(data1_size)
        self.data[tuple(write_indices)] = data_part1

        write_indices[self._axis] = slice(data1_size, data1_size + data2_size)
        self.data[tuple(write_indices)] = data_part2

    def put(self, data: np.ndarray) -> None:
        """
        Appends data into the buffer.

        Args:
          data (np.ndarray): The data to be appended into the buffer.
        """
        if data.size == 0:
            return

        insert_size = data.shape[self._axis]
        resulting_size = self._size + insert_size
        if resulting_size > self.max_size:
            self.resize(int(resulting_size * GROWTH_MULTIPLIER))

        idx_beg = self._tail
        idx_end = min(self.max_size, idx_beg + insert_size)
        idx_overflow = insert_size - (idx_end - idx_beg)
        assert idx_overflow <= self._head and (self._tail >= self._head or idx_end <= self._head)

        write_indices = self._index_samples(idx_beg, idx_end)  # idx_beg:idx_end
        read_indices = self._index_samples(None, idx_end - idx_beg)  # :idx_end - idx_beg
        self.data[write_indices] = data[read_indices]

        write_indices = self._index_samples(None, idx_overflow)  # :idx_overflow
        read_indices = self._index_samples(idx_end - idx_beg, None)  # idx_end - idx_beg:
        self.data[write_indices] = data[read_indices]

        self._tail = (self._tail + insert_size) % self.max_size
        self._size += insert_size

    def pop(self, pop_size: int) -> np.ndarray:
        """
        Removes and returns the first n elements from the buffer.

        Args:
          pop_size (int): The number of elements to remove from the buffer.

        Returns:
          np.ndarray: The elements removed from the buffer.

        Raises:
          ValueError: When attempting to remove more elements than the buffer contains.
        """
        data = np.concatenate(self._get(pop_size), self._axis)
        # max below prevents 0 % 0 when pop_size == 0 and max_size == 0 and does nothing for other cases
        self._head = (self._head + pop_size) % max(1, self.max_size)
        self._size -= pop_size
        return data

    def _get(self, count: int) -> tuple[np.ndarray, np.ndarray]:
        """
        Retrieves the first n elements of the buffer and returns them as two array views.

        The first (primary) view contains elements in the range: (`head` -> max(`max_size`, `tail`)).

        The second (overflow) view contains elements in the range: (0 -> head).

        The distribution of elements between the two views depends on the relative positions of `head`
        and `tail`. The total number of elements across both views is equal to `count`.

        Args:
          count (int): The number of elements to retrieve from the buffer.

        Returns:
          tuple[np.ndarray, np.ndarray]: A tuple containing the primary and overflow array views.
          Concatenate these views to obtain the complete result.

        Raises:
          ValueError: When the `count` is greater than the number of elements in the buffer.
        """
        if count > self._size:
            raise ValueError("Tried to access more elements than are in the buffer")

        idx_beg = self._head
        idx_end = min(self.max_size, idx_beg + count)
        idx_overflow = count - (idx_end - idx_beg)

        read_indices = [slice(None) for _ in range(self.data.ndim)]

        read_indices[self._axis] = slice(idx_beg, idx_end)  # idx_beg:idx_end
        part1 = self.data[tuple(read_indices)]

        read_indices[self._axis] = slice(idx_overflow)  # :idx_overflow
        part2 = self.data[tuple(read_indices)]

        return (part1, part2)

    def clear(self) -> None:
        """Discards all the elements."""
        self._head = self._tail = self._size = 0
