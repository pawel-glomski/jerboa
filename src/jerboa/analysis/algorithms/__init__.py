import importlib
import pkgutil
import pathlib


def import_submodules(module_name: str, module_path: str) -> dict:
    return {
        name: importlib.import_module(module_name + "." + name)
        for loader, name, is_pkg in pkgutil.walk_packages([pathlib.Path(module_path).parent])
    }


__all__ = import_submodules(__name__, __file__).keys()
