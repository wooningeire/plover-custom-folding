from typing import Optional

from plover.engine import StenoEngine
from plover.translation import Translator

class TranslatorContainer:
    translator: Optional[Translator] = None
translator_container = TranslatorContainer()

class EngineGetterExtension:
    def __init__(self, engine: StenoEngine):
        translator_container.translator = engine._translator
    
    def start(self):
        pass

    def stop(self):
        pass