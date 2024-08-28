from plover.engine import StenoEngine
from plover.translation import Translator
from plover.steno import Stroke

from .lib.builder import Rule

class TranslatorContainer:
    checking_shorter_outlines = False
    __shorter_outline_length = -1
    __checked_shorter_outlines = False


    def __init__(self):
        self.translator: "Translator | None" = None

    def check_shorter_outlines(self, longest_key_len: int):
        if self.translator is None: raise Exception("EngineGetterExtension is not enabled; enable it in Plover config > `Plugins`")

        # Check shorter outlines before trying to defold (mimic default Plover behavior)
        if TranslatorContainer.checking_shorter_outlines: return -1

        if TranslatorContainer.__checked_shorter_outlines:
            return self.__shorter_outline_length

        TranslatorContainer.__checked_shorter_outlines = True

        TranslatorContainer.checking_shorter_outlines = True
        strokes = []
        for translation in self.translator.get_state().translations:
            for stroke in translation.strokes:
                strokes.append(stroke)
                
                if len(strokes) == longest_key_len:
                    break
            if len(strokes) == longest_key_len:
                break

        for start_index in range(len(strokes) - 1, 0, -1):
            shorter_translation = self.translator.lookup(strokes[start_index:])
            if shorter_translation is None: continue

            TranslatorContainer.checking_shorter_outlines = False
            self.__shorter_outline_length = True
            return len(strokes) - start_index
        TranslatorContainer.checking_shorter_outlines = False

        self.__shorter_outline_length = False
        return -1
    
    def setup(self, engine: StenoEngine):
        self.translator = engine._translator

        def on_stroked(stroke: Stroke):
            Rule.clear_unmatched_rules()
            TranslatorContainer.clear_shorter_outlines()
        engine.hook_connect("stroked", on_stroked)

    @staticmethod
    def clear_shorter_outlines():
        TranslatorContainer.__shorter_outline_length = -1
        TranslatorContainer.__checked_shorter_outlines = False



translator_container = TranslatorContainer()

class EngineGetterExtension:
    def __init__(self, engine: StenoEngine):
        translator_container.setup(engine)
    
    def start(self):
        pass

    def stop(self):
        pass