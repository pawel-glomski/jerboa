# Jerboa - AI-powered media player
# Copyright (C) 2024 Paweł Głomski

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.


from __future__ import annotations

import sys
import loguru
from functools import lru_cache
from typing import Callable


sys.tracebacklimit = 10


class _Logger:
    def __init__(self):
        self._logger: loguru.Logger | None = None

    def __getstate__(self) -> dict[str]:
        return self.__dict__

    def __setstate__(self, state: dict[str]):
        self.__dict__.update(state)

    def __getattr__(self, attr_name: str):
        assert attr_name != "_logger"
        assert self._logger is not None, "Logger uninitialized"

        return getattr(self._logger, attr_name)

    def initialize(self, name: str, main_logger: loguru.Logger | "_Logger" | None = None) -> None:
        assert self._logger is None, "Logger initialized twice"

        if main_logger is None:
            self._logger = _Logger._create_logger()
        elif isinstance(main_logger, _Logger):
            self._logger = main_logger._logger  # pylint: disable=protected-access
        else:
            self._logger = main_logger

        self._logger = self._logger.bind(logger_name=name)

    @staticmethod
    def _create_logger() -> loguru.Logger:
        loguru.logger.remove()
        loguru.logger.add(
            sys.stderr,
            # "./log.txt",
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSSS}</green> | "
                "<level>{extra[logger_name]}</level> | "
                "<level>{thread.name}</level> | "
                "<level>{level}</level> | "
                "<cyan>{name}:{line}</cyan> | "
                "<level>{extra[context]}{message}</level>"
                "<light-black>{extra[details]}</light-black>"
            ),
            diagnose=False,
            enqueue=True,
        )
        loguru.logger.configure(
            extra={
                "context": "",
                "details": "",
            }
        )
        loguru.logger = loguru.logger.patch(_Logger._patch_extra)

        return loguru.logger

    @staticmethod
    def _patch_extra(record) -> None:
        if context := record["extra"]["context"]:
            record["extra"]["context"] = f"<{context}> "
        if details := record["extra"]["details"]:
            record["extra"]["details"] = f"\n ↳ {details}"


logger: loguru.Logger | _Logger = _Logger()


@lru_cache(5)
def log_once(log_fn: Callable[[str], None], *args, **kwargs):
    log_fn(*args, **kwargs)
