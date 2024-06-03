# This is separate so the classes in ./builder.py aren't executed (`Stroke` can't be instantiated immediately)

from plover.steno import Stroke
from plover.translation import Translator

from typing import Callable


Lookup = Callable[[tuple[Stroke], Translator], str]