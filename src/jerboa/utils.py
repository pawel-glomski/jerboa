class ActivationContext:
    def __init__(self):
        self._active = False

    def __del__(self):
        assert not self._active

    def __enter__(self) -> None:
        assert not self._active
        self._active = True

    def __exit__(self, *exc_args) -> None:
        assert self._active
        self._active = False

    def __bool__(self) -> bool:
        return self._active
