from typing import Optional

from plover.engine import StenoEngine
from plover.translation import Translator

from .lib.builder import Rule

class TranslatorContainer:
    translator: Optional[Translator] = None
translator_container = TranslatorContainer()

class EngineGetterExtension:
    def __init__(self, engine: StenoEngine):
        translator_container.translator = engine._translator

        engine.hook_connect("stroked", lambda stroke: Rule.clear_unmatched_rules())
    
    def start(self):
        pass

    def stop(self):
        pass