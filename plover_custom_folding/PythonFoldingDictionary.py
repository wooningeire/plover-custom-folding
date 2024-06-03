import importlib.util
from importlib.machinery import SourceFileLoader
from typing import Optional, Callable

from plover.steno import Stroke
from plover.steno_dictionary import StenoDictionary
from plover.translation import Translator

from .EngineGetterExtension import translator_container


class PythonFoldingDictionary(StenoDictionary):
    readonly = True
    longest_key = 5

    __lookups: Optional[list[Callable[[tuple[str], Translator], str]]]
    __looking_up = False

    def __init__(self):
        super().__init__()

    def _load(self, filepath: str):
        # SourceFileLoader because spec_from_file_location only accepts files with a `py` file extension
        spec = importlib.util.spec_from_loader(filepath, SourceFileLoader(filepath, filepath))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        self.__lookups = module.lookups

    def __getitem__(self, key: tuple[str]) -> str:
        result = self.__lookup(key)
        if result is None:
            raise KeyError
        
        return result

    def get(self, key: tuple[str], fallback=None) -> Optional[str]:
        result = self.__lookup(key)
        if result is None:
            return fallback
        
        return result
    
    def __lookup(self, key: tuple[str]) -> Optional[str]:
        if self.__looking_up:
            return None

        # Prevent a folding dictionary from looking up itself
        self.__looking_up = True

        strokes = [Stroke.from_steno(steno) for steno in key]
        for lookup in self.__lookups:
            try:
                result = lookup(strokes, translator_container.translator)
                self.__looking_up = False
                return result
            except KeyError:
                continue

        self.__looking_up = False
        return None