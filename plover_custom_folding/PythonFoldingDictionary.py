from typing import Optional

from plover.steno import Stroke
from plover.steno_dictionary import StenoDictionary

from .EngineGetterExtension import translator_container, TranslatorContainer
from .lib.builder import Rule
from .lib.util import exec_module_from_filepath


class PythonFoldingDictionary(StenoDictionary):
    readonly = True

    def __init__(self):
        super().__init__()

        """(override)"""
        self._longest_key = 8
        self.__rules: "list[Rule] | None" = None
        self.__current_rules: set[Rule] = set()

    def _load(self, filepath: str):
        module = exec_module_from_filepath(filepath)

        self.__rules = module.rules
        self._longest_key = getattr(module, "LONGEST_KEY", self._longest_key)

    def __getitem__(self, key: tuple[str, ...]) -> str:
        result = self.__lookup(key)
        if result is None:
            raise KeyError
        
        return result

    def get(self, key: tuple[str, ...], fallback=None) -> Optional[str]:
        result = self.__lookup(key)
        if result is None:
            return fallback
        
        return result
    
    def __lookup(self, key: tuple[str, ...]) -> Optional[str]:
        if self.__rules is None:
            raise Exception("tried looking up before dictionary was loaded")
        if translator_container.translator is None:
            raise Exception("EngineGetterExtension is not enabled; enable it in Plover config > `Plugins`")
        
        if not Rule.check_additional_folds:
            return None
        
        if TranslatorContainer.checking_shorter_outlines:
            return None
        
        strokes = tuple(Stroke.from_steno(steno) for steno in key)

        shorter_outline_length = translator_container.check_shorter_outlines(self._longest_key)
        shorter_outline_found = shorter_outline_length != -1 and shorter_outline_length < len(strokes)


        for rule in self.__rules:
            # Prevent a rule from looking up itself
            if rule in self.__current_rules:
                continue
            
            self.__current_rules.add(rule)

            translation = rule(strokes, translator_container.translator, shorter_outline_found)
            
            self.__current_rules.remove(rule)
            
            if translation is None:
                continue
            return translation

        return None