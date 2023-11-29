import importlib

from jerboa.analysis.algorithm import Algorithm


class AlgorithmRegistry:
    def __init__(self) -> None:
        self._algorithms = list[type[Algorithm]]()

        self.register_algorithm_from_module("jerboa.analysis.algorithms.silence_remover")
        # self.register_algorithm("jerboa.analysis.algorithms.spectrogram")

    @property
    def algorithms(self) -> list[type[Algorithm]]:
        return self._algorithms

    def register_algorithm_from_module(
        self, algorithm_module: str, root: str | None = None
    ) -> bool:
        module = importlib.import_module(algorithm_module, root)
        self.register_algorithm(module.Algorithm)

    def register_algorithm(self, algorithm_class: type[Algorithm]) -> bool:
        self._algorithms.append(algorithm_class)
