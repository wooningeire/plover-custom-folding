from typing import Optional

from plover.steno import Stroke
from plover.steno_dictionary import StenoDictionary

from .lib.util import exec_module_from_filepath


class PythonDictionary(StenoDictionary):
    readonly = True


    def __init__(self):
        super().__init__()

        """(override)"""
        self._longest_key = 0
        self.__lookup = None
        self.__reverse_lookup = lambda translation: set()


    def _load(self, filepath: str):
        module = exec_module_from_filepath(filepath)

        self.__lookup = module.lookup
        self._longest_key = module.LONGEST_KEY
        self.__reverse_lookup = getattr(module, "reverse_lookup", self.__reverse_lookup)

    def __getitem__(self, key: tuple[str]) -> str:
        result = self.__lookup_steno(key)
        if result is None:
            raise KeyError
        
        return result

    def get(self, key: tuple[str], fallback=None) -> Optional[str]:
        result = self.__lookup_steno(key)
        if result is None:
            return fallback
        
        return result
    
    def __lookup_steno(self, key: tuple[str]) -> Optional[str]:
        if self.__lookup is None:
            raise Exception("tried looking up before dictionary was loaded")
    
        if len(key) > self._longest_key:
            return None

        strokes = tuple(Stroke.from_steno(steno) for steno in key)
        return self.__lookup(strokes)
    
    def reverse_lookup(self, translation: str) -> set[str]:
        return set(self.__reverse_lookup(translation))