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

import inspect
import typing as T


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


class LazyObj:
    def __init__(self, obj_type: type, *args, **kwargs):
        self._obj_type = obj_type
        self._args = args
        self._kwargs = kwargs
        self._instance = None

    def __getattr__(self, attr_name: str) -> T.Any:
        if self._instance is None:
            self._instance = self._obj_type(*self._args, **self._kwargs)
            del self._obj_type
            del self._args
            del self._kwargs
            self.__getattribute__ = lambda attr: getattr(self._instance, attr)
        else:
            raise AttributeError(
                f"'{self._instance.__class__.__name__}' object has no attribute '{attr_name}'"
            )

        return self.__getattribute__(attr_name)


def assert_callable(fn: T.Callable, expected_args: set[str]) -> None:
    observed_args = inspect.signature(fn).parameters

    missing_args = expected_args - observed_args.keys()
    unexpected_args = observed_args.keys() - expected_args
    unexpected_args -= {
        param.name
        for param in observed_args.values()
        if (param.kind in [inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL])
        or param.default is not inspect.Parameter.empty
    }

    if len(missing_args) > 0 or len(unexpected_args):
        raise KeyError(
            f"Function ({fn}) has wrong signature. "
            f"Missing args={missing_args}, unexpected args={unexpected_args}"
        )
