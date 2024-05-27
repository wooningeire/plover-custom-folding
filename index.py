from plover.translation import Translation
from plover.engine import StenoEngine
from plover.steno import Stroke

def undoable(engine: StenoEngine, argument: str):
    translator = engine._translator

    """
    When a command call is located inside a dictionary entry's translation, the command's code is executed **after**
    the entry's Translation object has been pushed onto the Translator's `translation` stack.
    
    In order to make a stroke undoable, we need to:
     • Access the second-to-last Translation on the stack (the last Translation is the stroke that we want to make undoable)
     • Append a dummy stroke onto the `strokes` list for that Translation

    To access the second-to-last stroke, here we first untranslate the last Translation, and then retranslate it when
    we're done.

    There may be some side effects of this…?
    """

    translations: list[Translation] = translator.get_state().translations


    newest_translation = translations[-1]
    translator.untranslate_translation(newest_translation)

    if len(translations) >= 1:
        previous_translation = translations[-1]
        new_translation = Translation(previous_translation.strokes + [Stroke("*")], previous_translation.english)
        new_translation.replaced.append(previous_translation)

        translator.translate_translation(new_translation)
        translator.translate_translation(newest_translation)

    else:
        new_translation = Translation([Stroke("*")], " ")
        translator.translate_translation(new_translation)


def clrtrans(engine: StenoEngine, argument: str):
    translator = engine._translator

    newest_translation = translator.get_state().translations[-1]
    engine.clear_translator_state()
    translator.translate_translation(newest_translation)