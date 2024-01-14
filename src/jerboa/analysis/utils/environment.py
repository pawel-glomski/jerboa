# Jerboa - AI-powered media player
# Copyright (C) 2023 Paweł Głomski

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


import os
import sys
import subprocess
import importlib
import importlib.util
from dataclasses import dataclass

from jerboa.utils import ActivationContext
from jerboa.log import logger
from jerboa.core.multithreading import Task

INTERPRETER_PATH = sys.executable
PIP_INDEX_URL = os.environ.get("PIP_INDEX_URL", None)

PIP_GUARD = ActivationContext()

BUSY_LOOP_SLEEP_TIME = 0.05  # in seconds


@dataclass
class Package:
    name: str
    version_op: str | None = None
    version: str | None = None

    def __post_init__(self):
        assert (self.version_op is None) == (self.version is None)

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Package) and self.name == other.name

    def __str__(self) -> str:
        return f"{self.name}{self.version_op or ''}{self.version or ''}"

    def __repr__(self) -> str:
        return str(self)


def is_installed(package: Package):
    try:
        spec = importlib.util.find_spec(package.name)
    except ModuleNotFoundError:
        return False

    return spec is not None


def pip_install(packages: set[Package], executor: Task.Executor | None = None):
    with PIP_GUARD:
        to_install = {pkg for pkg in packages if not is_installed(pkg)}

        if len(to_install) > 0:
            logger.debug(f"Packages to install: {to_install}")

            index_url = [f"--index-url {PIP_INDEX_URL}"] if PIP_INDEX_URL is not None else []
            process = subprocess.Popen(
                [
                    INTERPRETER_PATH,
                    *["-m", "pip"],
                    "install",
                    *[str(pkg) for pkg in to_install],
                    "--prefer-binary",
                    *index_url,
                ],
            )

            if executor is None:
                process.wait()
            else:
                while process.poll() is None:
                    if not executor.abort_aware_sleep(BUSY_LOOP_SLEEP_TIME):
                        process.terminate()
                        executor.abort()

            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode, process.args, process.stdout, process.stderr
                )

            logger.debug(f"Installed packages: {to_install}")
        logger.debug(f"Prepared packages: {packages}")
