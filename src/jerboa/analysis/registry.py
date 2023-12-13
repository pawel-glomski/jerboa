import importlib
import importlib.util
from pathlib import Path

from jerboa.logger import logger
from jerboa.settings import Settings, ENVIRONMENT
from jerboa.core.signal import Signal
from jerboa.core.multithreading import ThreadPool, FnTask
from jerboa.analysis.algorithm import Algorithm, Environment


class AlgorithmRegistry:
    def __init__(
        self,
        settings: Settings,
        thread_pool: ThreadPool,
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
            self._prepare_environment(algorithm)

    def prepare_environment(self, algorithm_name: str, env_parameters: dict[str]):
        algorithm = self._algorithms_by_name[algorithm_name]
        for param_name, param_value in env_parameters.items():
            setattr(algorithm.environment, param_name, param_value)

        self._prepare_environment(algorithm)

    def _prepare_environment(self, algorithm: Algorithm) -> None:
        if not self._last_task_future.stage.is_finished(finishing_aborted=True):
            self._show_error_message_signal.emit(message="Previous task is still running")
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
                algorithm.environment.state = Environment.State.PREPARATION_FAILED
                self._alg_env_prep_progress_signal.emit(progress=None, message=None)
                raise
            except Exception:
                logger.exception("Algorithm environment preparation crashed")
                algorithm.environment.state = Environment.State.PREPARATION_FAILED
                self._alg_env_prep_progress_signal.emit(progress=None, message=None)
                raise

        logger.debug(f"Algorithm ({algorithm.name}) environment preparation...")
        self._last_task_future = self._thread_pool.start(FnTask(task))
        self._alg_env_prep_task_started_signal.emit(
            algorithm_name=algorithm.name,
            task_future=self._last_task_future,
        )
