from .algorithm import Algorithm


class AnalysisManager:
    def __init__(self) -> None:
        ...

    @property
    def run(self, algorithm: Algorithm) -> None:
        raise NotImplementedError()
