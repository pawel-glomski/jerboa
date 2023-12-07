import importlib
import importlib.util

from jerboa.core.signal import Signal
from jerboa.analysis.algorithm import Algorithm


class AlgorithmRegistry:
    def __init__(self, algorithm_added_signal: Signal) -> None:
        self._algorithms = list[type[Algorithm]]()

        self._algorithm_added_signal = algorithm_added_signal

    @property
    def algorithms(self) -> list[type[Algorithm]]:
        return self._algorithms

    def register_algorithm_from_module(
        self, algorithm_module: str, root: str | None = None
    ) -> bool:
        module = importlib.import_module(algorithm_module, root)
        self.register_algorithm(module.Algorithm)

    def register_algorithm_from_file(self, algorithm_path: str):
        spec = importlib.util.spec_from_file_location(
            f"_jerboa_algorithm_{len(self._algorithms)}", algorithm_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.register_algorithm(module.Algorithm)

    def register_algorithm(self, algorithm_class: type[Algorithm]) -> bool:
        self._algorithms.append(algorithm_class)
        self._algorithm_added_signal.emit(algorithm=algorithm_class)
