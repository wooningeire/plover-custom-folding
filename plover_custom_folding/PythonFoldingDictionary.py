import importlib.util
from importlib.machinery import SourceFileLoader
from typing import Optional

from plover.steno import Stroke
from plover.steno_dictionary import StenoDictionary

from .EngineGetterExtension import translator_container

from .lib.builder import Lookup


class PythonFoldingDictionary(StenoDictionary):
    readonly = True

    __current_lookups: set[Lookup] = set()

    def __init__(self):
        super().__init__()

        """(override)"""
        self._longest_key = 8

        self.__rules: "list[Lookup] | None" = None

    def _load(self, filepath: str):
        # SourceFileLoader because spec_from_file_location only accepts files with a `py` file extension
        spec = importlib.util.spec_from_loader(filepath, SourceFileLoader(filepath, filepath))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        

        self.__rules = module.rules

        if hasattr(module, "LONGEST_KEY"):
            self._longest_key = module.LONGEST_KEY

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
        strokes = tuple(Stroke.from_steno(steno) for steno in key)
        for lookup in self.__rules:
            # Prevent a folding dictionary from looking up itself
            if lookup in self.__current_lookups:
                continue
            
            self.__current_lookups.add(lookup)

            try:
                return lookup(strokes, translator_container.translator)
            except KeyError:
                continue
            finally:
                self.__current_lookups.remove(lookup)

        return None