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


import importlib
import importlib.util
from pathlib import Path

from jerboa.log import logger
from jerboa.settings import Settings, ENVIRONMENT
from jerboa.core.signal import Signal
from jerboa.core.multithreading import ThreadPool, FnTask
from jerboa.analysis.algorithm import Algorithm, Environment


class AlgorithmRegistry:
    def __init__(
        self,
        settings: Settings,
        thread_pool: ThreadPool,
        prev_task_still_running_error_msg: str,
        alg_env_prep_error_message: str,
        alg_registered_signal: Signal,
        alg_env_prep_task_started_signal: Signal,
        alg_env_prep_progress_signal: Signal,
        show_error_message_signal: Signal,
    ) -> None:
        self._settings = settings
        self._algorithms_by_path = dict[Path, Algorithm]()
        self._algorithms_by_name = dict[str, Algorithm]()

        self._algorithm_dir_paths = [
            Path(__file__).parent / "algorithms",
            ENVIRONMENT.extensions_analysis_dir_path,
        ]

        self._thread_pool = thread_pool
        self._last_task_future: FnTask.Future = FnTask(lambda: None, already_finished=True).future

        self._prev_task_still_running_error_msg = prev_task_still_running_error_msg
        self._alg_env_prep_error_message = alg_env_prep_error_message

        self._alg_registered_signal = alg_registered_signal
        self._alg_env_prep_task_started_signal = alg_env_prep_task_started_signal
        self._alg_env_prep_progress_signal = alg_env_prep_progress_signal
        self._show_error_message_signal = show_error_message_signal

    @property
    def algorithms(self) -> dict[Path, Algorithm]:
        return self._algorithms_by_path

    def get(self, algorithm_index: int) -> Algorithm:
        return list(self._algorithms_by_path.values())[algorithm_index]

    def update(self) -> None:
        for algorithm_dir in self._algorithm_dir_paths:
            for algorithm_module_path in algorithm_dir.glob("*"):
                self.register_algorithm_from_path(algorithm_module_path)

    def register_algorithm_from_path(self, algorithm_path: Path) -> None:
        try:
            algorithm_path = Path(algorithm_path)
            if algorithm_path in self.algorithms:
                return

            module_name = f"_jb_alg_{len(self._algorithms_by_path)}_{algorithm_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, algorithm_path)
            if spec is None:
                return

            algorithm_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(algorithm_module)

            self._register_algorithm(algorithm_path, algorithm_module.ALGORITHM)

        except Exception:
            logger.exception(f"Failed to register analysis algorithm from '{algorithm_path}'")

    def _register_algorithm(self, algorithm_path: Path, algorithm: Algorithm):
        assert algorithm.name not in self._algorithms_by_name

        self._algorithms_by_path[algorithm_path] = algorithm
        self._algorithms_by_name[algorithm.name] = algorithm
        self._alg_registered_signal.emit(algorithm=algorithm)

        if algorithm.environment.state == Environment.State.NOT_PREPARED__TRY_BY_DEFAULT:
            self._prepare_environment(algorithm, last_env_params={})

    def prepare_environment(self, algorithm: Algorithm, env_parameters: dict[str]):
        assert algorithm is self._algorithms_by_name[algorithm.name]
        assert len(env_parameters.keys() - algorithm.environment.model_fields.keys()) == 0

        last_params = algorithm.environment.model_dump()
        for param_name, param_value in env_parameters.items():
            setattr(algorithm.environment, param_name, param_value)

        self._prepare_environment(algorithm, last_env_params=last_params)

    def _prepare_environment(self, algorithm: Algorithm, *, last_env_params: dict[str]) -> None:
        if not self._last_task_future.stage.is_finished(finishing_aborted=True):
            self._show_error_message_signal.emit(message=self._prev_task_still_running_error_msg)
            return

        def task(executor: FnTask.Executor):
            try:
                algorithm.environment.prepare(executor, self._alg_env_prep_progress_signal)
                with executor.finish_context:
                    logger.debug(
                        f"Algorithm ({algorithm.name}) environment preparation... Successful"
                    )
                    algorithm.environment.state = Environment.State.PREPARATION_SUCCESSFUL
                    self._alg_env_prep_progress_signal.emit(progress=1, message=None)
            except FnTask.Abort:
                logger.debug(f"Algorithm ({algorithm.name}) environment preparation aborted")

                # restore the last config, do not update `environment.state`
                algorithm.environment.model_copy(update=last_env_params)
                self._alg_env_prep_progress_signal.emit(progress=None, message=None)
                raise
            except Exception as exception:
                # this is a task, do not log the crash here, it will be logged by the executor
                # logger.exception("Algorithm environment preparation crashed")

                # do not restore the last config, update `environment.state`
                algorithm.environment.state = Environment.State.PREPARATION_FAILED
                self._alg_env_prep_progress_signal.emit(progress=None, message=None)
                self._show_error_message_signal.emit(
                    title=f"{self._alg_env_prep_error_message} ({algorithm.name})",
                    message=repr(exception),
                )
                raise

        logger.debug(f"Algorithm ({algorithm.name}) environment preparation...")
        self._last_task_future = self._thread_pool.start(FnTask(task))
        self._alg_env_prep_task_started_signal.emit(
            algorithm=algorithm,
            task_future=self._last_task_future,
        )
