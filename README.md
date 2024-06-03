# Plover custom folding
Plugin that lets users use Python dictionaries to define custom folding rules.

```py
# Filename: example.fold-py

# Python folding dictionary that allows the `#` key to be included in the
# first stroke to capitalize a word.
# E.g., `#KAP/TAL` => `{-|}capital` ("Capital")


from plover.steno import Stroke
from plover.translation import Translator

from typing import Callable


def _lookup(strokes: tuple[Stroke], translator: Translator):
    if "#" not in strokes[0].keys():
        raise KeyError

    unfolded_result = translator.lookup([strokes[0] - Stroke.from_steno("#")] + strokes[1:])
    if unfolded_result is None:
        raise KeyError

    return f"{{-|}}{unfolded_result}"


#region Exports

"""(optional | default = 8)
The maximum outline length that the given folding rules can be applied to."""
LONGEST_KEY: int = 4

"""A list of lookup functions that this dictionary will run."""
lookups: list[Callable[[tuple[Stroke], Translator], string]] = [
    _lookup,
]

#endregion
```