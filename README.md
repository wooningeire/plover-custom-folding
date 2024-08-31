# Plover custom folding
Plugin that lets users use Python dictionaries to define custom folding rules.

After installing, the extension `EngineGetterExtension` must be enabled from Plover's config > `Plugins` in order for folding dictionaries to work.


## Setup
This plugin is currently not available from Plover's Plugins Manager. [Instructions are available on the Plover wiki](https://plover.wiki/index.php/Plugins#Find_the_plugin_on_PyPI_or_as_a_git_repo) on how to install this plugin from PyPI or this Git repository.


## Dictionary examples
To avoid overwriting explicitly defined entries, folding dictionaries should most likely be placed at the bottom of the dictionary list.

```py
# Example of a Python folding dictionary with some basic rules. File extension is `fold-py`.

import plover_custom_folding as f

# Required. A list of rules or lookup functions of type `Callable[[tuple[Stroke, ...], Translator], str]`.
rules: list[f.Lookup] = [
    # Allows the `#` key to be included in the first stroke to capitalize a word.
    # E.g., `#KAP/TAL` => `{-|}capital` ("Capital")
    f.when(f.first_stroke.folds("#")).then(f.prefix_translation("{-|}")).preferring_folds(),

    # Allows the `-R` key to be included in the last stroke to append "{^er}".
    # E.g., `SHEURPL` => `shim {^er}` ("shimmer")
    f.when(f.last_stroke.folds("-R")).then(f.suffix_translation(" {^er}")),

    # Allows the substrokes `-GS` or `-GZ` to be included in the last stroke to append "{^ings}".
    # E.g., `WAUFPGS` => `watchings`
    f.when(f.last_stroke.folds("-GS", "-GZ")).then(f.suffix_translation(" {^ings}")),

    # Allows `-G` to be included and `*` to be toggled in the last stroke to append "{^in'}".
    # We can use `unfold_suffix` because `*G` is defined as "{^in'}" in main.json already.
    f.when(f.last_stroke.folds("-G").toggles("*")).then(f.unfold_suffix),
]

# Optional. The maximum length of the outline to check these folding rules for.
LONGEST_KEY: int = 8
```

```py
# Dictionary with some more complex rules. This dictionary requires a system with the `^` and `+` keys.

import plover_custom_folding as f 

rules: list[f.Lookup] = [
    # Note: the rules are grouped in a specific order. The higher rules will take precedence over (be checked earlier
    # than) lower ones, but modifications to the outline/translation occur in reverse order to the order in which each
    # rule is found to be satisfied.


    # Allows the `^` key to be included in every stroke to make the translation a suffix (preserving case),
    # or when the first stroke also includes `+`, then also hyphenate it (preserving case).
    # E.g., `^PWUFT/^*ER` => `{^~|^}buster`
    f.when(f.all_strokes.fold("^")).then(f.prefix_translation("{^~|^}"))
        .unless_also(
            f.when(f.first_stroke.folds("+")).then(f.prefix_translation("{^~|-^}")),
        ),

    # See above.
    f.when(f.first_stroke.folds("#")).then(f.prefix_translation("{-|}")).preferring_folds(),


    # Allows the `STK` substroke to be included in the first stroke and if so, we then lookup the de-folded outline
    # but with the stroke `TKEUS` behind it, and then again with the stroke `TKEU` behind it and `S` added to the first
    # stroke, and then just the de-folded stroke with "{dis^}" prefixed to the resulting translation.
    # E.g., `STKEPL/TPHAEUT` => `disseminate`
    # E.g., `STKPWHRAOEF` => `{dis^} belief` ("disbelief")
    f.when(f.first_stroke.folds("STK")).then(
        f.prefix_outline("TKEUS/"),
        f.prefix_outline("TKEU/S"),
        f.prefix_translation("{dis^} "),
    ),


    # Plover's default suffix folding rules based on the current system. Included so they take precedence over the
    # custom rules below.
    f.default_system_rules(),

    # See above.
    f.when(f.last_stroke.folds("-R")).then(f.suffix_translation(" {^er}")),
    f.when(f.last_stroke.folds("-GS", "-GZ")).then(f.suffix_translation(" {^ings}")),
    f.when(f.last_stroke.folds("-G").toggles("*")).then(f.unfold_suffix),
]
```

Note that separate folding rules defined in a folding dictionary can be combined, e.g., `#^+WAUFPGS` with the above rules translates to `{-|}{^~|-^}watch {^ings}` ("-Watchings" as a suffix). The order in which the rules modify the translation depends on the order in which they are specified in the list; e.g., since the `#` rule is specified first, it applies the outermost modification to the translation.

```py
# If desired, we can manually define our own custom functions as rules.

from plover.steno import Stroke
from plover.translation import Translator

import plover_custom_folding as f

def _lookup(strokes: tuple[Stroke, ...], translator: Translator):
    if "#" not in strokes[0].keys():
        raise KeyError

    translation = translator.lookup([strokes[0] - Stroke.from_steno("#")] + strokes[1:])
    if translation is None:
        raise KeyError

    return f"{{-|}}{translation}"

rules: list[f.Lookup] = [
    _lookup,
]
```


## Methods
TODO.

### `Rule.preferring_folds(self)`
Using built-in folding, Plover will give precedence to a shorter outline that is explicitly defined as opposed to a longer outline that is found using a fold. This plugin matches this behavior by default, but `preferring_folds` overrides this behavior, which may come in handy especially for prefix folds.

This makes certain multistroke entries more predictable:
* `SRAL/TKAEUGT` → `validate {^ing}` (original: `val dating`; conflict occurs because `TKAEUGT` → `dating` is explicitly defined in main.json)

… but others may have unexpected results:
* `SKP/HREUD` → `and I will {^ed}` (original: `and lid`; conflict occurs because of misstroke entry `SKP/HREU` → `and I will` in main.json)
