# Plover custom folding
Plugin that lets users use Python dictionaries to define custom folding rules.

After installing, the extension `EngineGetterExtension` must be enabled from Plover's config > `Plugins` in order for folding dictionaries to work.


## Dictionary examples
To avoid overwriting explicitly defined entries, folding dictionaries should most likely be placed at the bottom of the dictionary list.

```py
# Example of a Python folding dictionary. File extension is `fold-py`.

# This dictionary requires a system with the `^` and `+` keys.

from plover_custom_folding import f, Lookup

# Required. A list of rules or lookup functions of type `Callable[[tuple[Stroke, ...], Translator], str]`.
rules: list[Lookup] = [
    # Plover's default suffix folding rules based on the current system. Included so they take precedence over the
    # custom rules below.
    f.default_rules(),


    # Allows the substrokes `-GS` or `-GZ` to be included in the last stroke to append "{^ings}".
    # E.g., `WAUFPGS` => `watchings`
    f.when(f.last_stroke.folds("-GS", "-GZ")).then(f.append_to_translation(" {^ings}")),


    # Allows the substroke `*G` to be included in the last stroke to append "{^in'}".
    # We can use `unfold_suffix` because`*G` is defined as "{^in'}" in main.json already.
    f.when(f.last_stroke.folds("*G")).then(f.unfold_suffix),


    # Allows the `#` key to be included in the first stroke to capitalize a word.
    # E.g., `#KAP/TAL` => `{-|}capital` ("Capital")
    f.when(f.first_stroke.folds("#")).then(f.prepend_to_translation("{-|}")),


    # Allows the `^` key to be included in every stroke to make the translation a suffix (preserving case),
    # or when the first stroke also includes `+`, then also hyphenate it (preserving case).
    # E.g., `^PWUFT/^ER` => `{^~|^}buster`
    f.when(f.all_strokes.fold("^")).then(f.prepend_to_translation("{^~|^}"))
        .unless_also(
            f.when(f.first_stroke.folds("+")).then(f.prepend_to_translation("{^~|-^}")),
        ),
]

# Optional. The maximum length of the outline to check these folding rules for.
LONGEST_KEY: int = 8
```

Note that folding rules defined in a folding dictionary can be combined, e.g., `#^+WAUPGS` with the above rules translates to `{-|}{^~|-^}watch {^ings}` ("-Watchings" as a suffix).

```py
# If desired, we can manually define our own custom functions as rules.

from plover.steno import Stroke
from plover.translation import Translator

from plover_custom_folding import f, Lookup

def _lookup(strokes: tuple[Stroke, ...], translator: Translator):
    if "#" not in strokes[0].keys():
        raise KeyError

    translation = translator.lookup([strokes[0] - Stroke.from_steno("#")] + strokes[1:])
    if translation is None:
        raise KeyError

    return f"{{-|}}{translation}"

rules: list[Lookup] = [
    _lookup,
]
```