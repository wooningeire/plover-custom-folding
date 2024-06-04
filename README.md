# Plover custom folding
Plugin that lets users use Python dictionaries to define custom folding rules.


## Dictionary examples

```py
# Example of a Python folding dictionary. File extension is `fold-py`.

def init(f, FoldingRules):
    return FoldingRules([
        # Allows the `#` key to be included in the first stroke to capitalize a word.
        # E.g., `#KAP/TAL` => `{-|}capital` ("Capital")
        f.when(f.first_stroke.folds("#")).then(f.prepend_to_translation("{-|}")),

        # Allows the substroke `*G` to be included in the last stroke to append "{^in'}".
        f.when(f.last_stroke.folds("*G")).then(f.unfold_suffix),

        # Allows the `^` key to be included in every stroke to make the translation an affix,
        # or when the first stroke also includes `+`, then hyphenate it.
        # E.g., `^PWUFT/^ER` => `{^}buster`
        f.when(f.all_strokes.fold("^")).then(f.prepend_to_translation("{^}"))
            .unless_also(
                f.when(f.first_stroke.folds("+")).then(f.prepend_to_translation("{^}-")),
            ),
    ])
```

```py
# If desired, we can manually define our own custom functions as rules.

from plover.steno import Stroke
from plover.translation import Translator

from typing import Callable

def init(f, FoldingRules):
    def lookup(strokes: tuple[Stroke], translator: Translator):
        if "#" not in strokes[0].keys():
            raise KeyError

        translation = translator.lookup([strokes[0] - Stroke.from_steno("#")] + strokes[1:])
        if translation is None:
            raise KeyError

        return f"{{-|}}{translation}"

    return FoldingRules([
        lookup,
    ])
```