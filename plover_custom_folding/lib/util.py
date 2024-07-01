import importlib.util
from importlib.machinery import SourceFileLoader

from plover.steno import Stroke


def exec_module_from_filepath(filepath: str):
    # SourceFileLoader because spec_from_file_location only accepts files with a `py` file extension
    loader = SourceFileLoader(filepath, filepath)
    spec = importlib.util.spec_from_loader(filepath, loader)
    if spec is None:
        raise Exception(f"file @ {filepath} does not exist")
    
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)

    return module

def empty_stroke() -> Stroke:
    return Stroke.from_keys(())
