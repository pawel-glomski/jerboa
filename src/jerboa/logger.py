import sys
from loguru import logger
from functools import lru_cache
from typing import Callable


def _patch_extra(record) -> None:
    if context := record["extra"]["context"]:
        record["extra"]["context"] = f"<{context}> "
    if details := record["extra"]["details"]:
        record["extra"]["details"] = f"\n ↳ {details}"


logger.remove()
logger.add(
    sys.stderr,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}:{line}</cyan> | "
        "<level>{extra[context]}{message}</level>"
        "<light-black>{extra[details]}</light-black>"
    ),
    diagnose=False,
)
logger.configure(
    extra={
        "context": "",
        "details": "",
    }
)
logger = logger.patch(_patch_extra)


@lru_cache(5)
def log_once(log_fn: Callable[[str], None], *args, **kwargs):
    log_fn(*args, **kwargs)
