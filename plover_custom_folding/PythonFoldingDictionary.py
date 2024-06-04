import importlib.util
from importlib.machinery import SourceFileLoader
from typing import Optional

from plover.steno import Stroke
from plover.steno_dictionary import StenoDictionary

from .EngineGetterExtension import translator_container

# Need to import lazily because `Stroke` can't be instantiated immediately
from .lib.types import Lookup
# from .lib.builder import FoldingRules, FoldingRuleBuildHelper, Lookup


class PythonFoldingDictionary(StenoDictionary):
    readonly = True

    __current_lookups: set[Lookup] = set()

    def __init__(self):
        from .lib.builder import FoldingRules

        super().__init__()

        """(override)"""
        self._longest_key = 8

        self.__rules: "FoldingRules | None" = None

    def _load(self, filepath: str):
        from .lib.builder import FoldingRules, FoldingRuleBuildHelper

        # SourceFileLoader because spec_from_file_location only accepts files with a `py` file extension
        spec = importlib.util.spec_from_loader(filepath, SourceFileLoader(filepath, filepath))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        assert isinstance(rules := module.init(FoldingRuleBuildHelper, FoldingRules), FoldingRules)
        self.__rules = rules
        self._longest_key = rules.longest_key

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
        for lookup in self.__rules.lookups:
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