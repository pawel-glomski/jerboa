import logging
from functools import lru_cache
from typing import Callable

NULL_LOGGER = logging.getLogger("jerboa_null")
NULL_LOGGER.handlers = [logging.NullHandler()]
NULL_LOGGER.propagate = False

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger("jerboa")
logger.addHandler(handler)
# logger.setLevel(logging.WARNING)
logger.setLevel(logging.DEBUG)


@lru_cache(5)
def log_once(log_fn: Callable[[str], None], *args, **kwargs):
    log_fn(*args, **kwargs)
