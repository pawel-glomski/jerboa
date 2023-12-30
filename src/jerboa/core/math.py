import numpy as np
from typing import Callable, Tuple

Real = np.double


def ranges_of_truth(arr: np.ndarray) -> np.ndarray:
    """Returns a list of ranges, for which elements of a specified array are True. For example:
    an array [True,True,False,False,True,True] will generate the output: [[0, 2],[4,6]].

    Args:
        arr (np.ndarray): 1-dimensional array to check

    Returns:
        np.ndarray: An array of ranges: <start, end)
    """
    assert len(arr.shape) == 1

    ranges = np.where(arr[:-1] != arr[1:])[0] + 1
    is_even = len(ranges) % 2 == 0
    beg = np.array([0] if arr[0] else [], dtype=int)
    end = np.array([len(arr)] if is_even == arr[0] else [], dtype=int)
    return np.concatenate([beg, ranges, end]).reshape((-1, 2))


def int_linspace_steps_by_limit(start: int, stop: int, part_limit: int) -> np.ndarray:
    """Splits an interval into minimal number of parts of roughly equal sizes, where the target size
    of a part is given, and returns sizes of these parts.

    Args:
        start (int): Start of an interval
        stop (int): Endpoint of an interval
        part_limit (int): Size limit of a part

    Returns:
        np.ndarray: Sizes of parts
    """
    sizes = int_linspace_steps_by_no(start, stop, int_number_of_parts(stop - start, part_limit))
    assert sizes.max() <= part_limit
    return sizes


def int_linspace_steps_by_no(start: int, stop: int, num: int) -> np.ndarray:
    """Splits an interval into a specified number of parts of roughly equal sizes and returns sizes
    of these parts.

    Args:
        start (int): Start of an interval
        stop (int): Endpoint of an interval
        num (int): Number of parts

    Returns:
        np.ndarray: Sizes of parts
    """
    points = np.linspace(start, stop, num + 1, endpoint=True, dtype=int)
    sizes = points[1:] - points[:-1]
    assert len(sizes) == num
    return sizes


def int_number_of_parts(number: int, part_limit: int) -> int:
    """Calculates the number of parts needed to evenly divide a number when the target value of a part
    is given

    Args:
        number (int): Number to divide
        part_limit (int): Limit of a part

    Returns:
        int: Number of parts
    """
    return max(int(np.ceil(number / part_limit)), 1)


def kernel_2d_from_window(shape: Tuple, window_fn: Callable, **kwargs) -> np.ndarray:
    """Creates a 2D kernel from a 1D window function

    Args:
        shape (tuple): Shape of the kernel
        window_fn (Callable): 1D window funciton (for example np.hanning)

    Returns:
        np.ndarray: 2D kernel
    """
    kernel = np.outer(window_fn(shape[0] + 2, **kwargs), window_fn(shape[1] + 2, **kwargs))
    kernel = kernel[1:-1, 1:-1]
    kernel /= kernel.sum()
    return kernel
