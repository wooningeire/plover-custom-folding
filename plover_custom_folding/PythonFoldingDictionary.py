import importlib.util
from importlib.machinery import SourceFileLoader
from typing import Optional

from plover.steno import Stroke
from plover.steno_dictionary import StenoDictionary

from .EngineGetterExtension import translator_container

from .lib.builder import Rule


class PythonFoldingDictionary(StenoDictionary):
    readonly = True


    def __init__(self):
        super().__init__()

        """(override)"""
        self._longest_key = 8

        self.__rules: "list[Rule] | None" = None
        self.__current_rules: set[Rule] = set()

    def _load(self, filepath: str):
        # SourceFileLoader because spec_from_file_location only accepts files with a `py` file extension
        loader = SourceFileLoader(filepath, filepath)
        spec = importlib.util.spec_from_loader(filepath, loader)
        if spec is None:
            raise Exception(f"file @ {filepath} does not exist")
        
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        

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
        if self.__rules is None:
            raise Exception("tried looking up before dictionary was loaded")
        if translator_container.translator is None:
            raise Exception(f"EngineGetterExtension is not enabled; enable it in Plover config > `Plugins`")

        strokes = tuple(Stroke.from_steno(steno) for steno in key)
        for rule in self.__rules:
            # Prevent a rule from looking up itself
            if rule in self.__current_rules:
                continue
            
            self.__current_rules.add(rule)

            translation = rule(strokes, translator_container.translator)
            
            self.__current_rules.remove(rule)
            
            if translation is None:
                continue
            return translation

        return None