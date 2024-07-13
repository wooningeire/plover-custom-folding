from plover.steno import Stroke
from plover.translation import Translator
import plover.log

from typing import Callable

from .Rule import Case, Condition, Clause, Statement, Prerequisite, LookupStrategy, Rule, StrokeFilter, Outline, Formatter, empty_stroke


class _ClauseBuilder:
    def __init__(
        self,
        stroke_filter: StrokeFilter,
        conditions: tuple[Condition, ...] = (),
    ):
        """A function that returns the strokes to test."""
        self.__stroke_filter = stroke_filter
        self.__conditions = conditions


    def __call__(self) -> Clause:
        return Clause(self.__stroke_filter, self.__conditions)
    

    def folds(self, *substrokes_steno: str):
        """Tests if ANY SINGLE given substroke is folded into a set of strokes."""

        substrokes = tuple(Stroke.from_steno(substroke_steno) for substroke_steno in substrokes_steno)
        cases: list[Case] = []
        for substroke in sorted(substrokes, key=lambda substroke: len(substroke), reverse=True):
            cases.append(Case(
                substroke,
                empty_stroke(),
            ))

        return _ClauseBuilder(
            self.__stroke_filter,
            self.__conditions + (Condition(tuple(cases)),),
        )

    fold = folds

    def toggles(self, *substrokes_steno: str):
        """Tests if ANY SINGLE given substroke is toggled in a set of strokes."""

        substrokes = tuple(Stroke.from_steno(substroke_steno) for substroke_steno in substrokes_steno)
        cases: list[Case] = []
        for substroke in sorted(substrokes, key=lambda substroke: len(substroke), reverse=True):
            cases.append(Case(
                empty_stroke(),
                substroke,
            ))

        return _ClauseBuilder(
            self.__stroke_filter,
            self.__conditions + (Condition(tuple(cases)),),
        )
    
    toggle = toggles

class _LookupStrategyGatherer:
    def __init__(self, prerequisite: Prerequisite):
        self.__prerequisite = prerequisite

    def then(self, *lookup_strategy_creators: Callable[[], LookupStrategy]):
        """Gathers a list of lookup strategies that are run IN ORDER and INDEPENDENTLY."""
        return Rule(self.__prerequisite, tuple(create_lookup_strategy() for create_lookup_strategy in lookup_strategy_creators))
    
    def and_also(self, *rules: Rule):
        return Rule(self.__prerequisite, ()).unless_also(*rules)
    

class _TranslationModificationGatherer:
    def __init__(
        self,
        modify_translation: Callable[[str], str]=lambda translation: translation,
        modify_outline: Callable[[Outline], Outline]=lambda strokes: strokes,
        check_additional_folds=True,
    ):
        self.__modify_outline = modify_outline
        self.__modify_translation = modify_translation
        self.__check_additional_folds = check_additional_folds


    def __call__(self) -> LookupStrategy:
        @LookupStrategy.of
        def handler(defolded_strokes: Outline, folds: Outline, strokes: Outline, translator: Translator):
            original_check_additional_folds = Rule.check_additional_folds
            if not self.__check_additional_folds:
                Rule.check_additional_folds = False

            foldless_translation = translator.lookup(self.__modify_outline(defolded_strokes))

            if not self.__check_additional_folds:
                Rule.check_additional_folds = original_check_additional_folds

            if foldless_translation is None:
                return None
                        
            return self.__modify_translation(foldless_translation)

        return handler
    

    def modify_translation(self, modify_translation: Formatter) -> "_TranslationModificationGatherer":
        """Translates the outline without any folds, and modifies the translation according to the callback."""
        return _TranslationModificationGatherer(lambda translation: modify_translation(self.__modify_translation(translation)), self.__modify_outline)
    
    def prefix_translation(self, string: str) -> "_TranslationModificationGatherer":
        return self.modify_translation(lambda translation: f"{string}{translation}")
        
    def suffix_translation(self, string: str) -> "_TranslationModificationGatherer":
        return self.modify_translation(lambda translation: f"{translation}{string}")


class _OutlineModificationGatherer:
    def __init__(self, modify_outline: Callable[[Outline], Outline]=lambda strokes: strokes, check_additional_folds=True):
        self.__modify_outline = modify_outline
        self.__check_additional_folds = check_additional_folds


    def __call__(self) -> LookupStrategy:
        return self.__to_translation_modification_gatherer()()


    def __to_translation_modification_gatherer(self, modify_translation: Formatter=lambda translation: translation) -> _TranslationModificationGatherer:
        return _TranslationModificationGatherer(modify_translation, self.__modify_outline, self.__check_additional_folds)

    def modify_translation(self, modify_translation: Formatter=lambda translation: translation) -> _TranslationModificationGatherer:
        """Translates the outline without any folds, and modifies the translation according to the callback."""
        return self.__to_translation_modification_gatherer(modify_translation)
    
    def prefix_translation(self, string: str) -> _TranslationModificationGatherer:
        return self.__to_translation_modification_gatherer().prefix_translation(string)
        
    def suffix_translation(self, string: str) -> _TranslationModificationGatherer:
        return self.__to_translation_modification_gatherer().suffix_translation(string)
    
    def check_additional_folds(self) -> _TranslationModificationGatherer:
        return _OutlineModificationGatherer(self.__modify_outline, True).__to_translation_modification_gatherer()
    
    def modify_outline(self, modify_outline: Callable[[Outline], Outline]) -> "_OutlineModificationGatherer":
        """Translates the outline without any folds, and modifies the translation according to the callback."""
        return _OutlineModificationGatherer(lambda strokes: modify_outline(self.__modify_outline(strokes)), False)
    
    def prefix_outline(self, new_strokes_steno: str) -> "_OutlineModificationGatherer":
        new_strokes = tuple(Stroke.from_steno(stroke_steno) for stroke_steno in new_strokes_steno.split("/"))
        return self.modify_outline(lambda strokes: new_strokes[:-1] + (new_strokes[-1] + strokes[0],) + strokes[1:])
        
    def suffix_outline(self, new_strokes_steno: str) -> "_OutlineModificationGatherer":
        new_strokes = tuple(Stroke.from_steno(stroke_steno) for stroke_steno in new_strokes_steno.split("/"))
        return self.modify_outline(lambda strokes: strokes[:-1] + (new_strokes[0] + strokes[-1],) + new_strokes[1:])


def when(*builders: "Callable[[], Statement | Clause]") -> _LookupStrategyGatherer:
    """Gathers statements at least one of which must be true for this rule to be used."""
    return _LookupStrategyGatherer(Prerequisite(tuple(create() for create in builders)))
    
def when_all(*builders: "Callable[[], Statement | Clause]") -> _LookupStrategyGatherer:
    """Gathers statements all of which must be true for this rule to be used."""
    return when(all_rules(*builders))

first_stroke: _ClauseBuilder = _ClauseBuilder(lambda strokes: (strokes[0],))
last_stroke: _ClauseBuilder = _ClauseBuilder(lambda strokes: (strokes[-1],))
all_strokes: _ClauseBuilder = _ClauseBuilder(lambda strokes: strokes)
def nth_stroke(index: int):
    return _ClauseBuilder(lambda strokes: (strokes[index],))

def filtered_strokes(stroke_filter: StrokeFilter):
    return _ClauseBuilder(stroke_filter)


def all_rules(*builders: "Callable[[], Statement | Clause]"):
    return lambda: Statement(True, tuple(create() for create in builders))

def any_single_rule(*builders: "Callable[[], Statement | Clause]"):
    return lambda: Statement(False, tuple(create() for create in builders))


def modify_translation(modify_translation: Formatter=lambda translation: translation) -> _TranslationModificationGatherer:
    """Translates the outline without any folds, and modifies the translation according to the callback."""
    return _TranslationModificationGatherer(modify_translation)

def prefix_translation(string: str) -> _TranslationModificationGatherer:
    return _TranslationModificationGatherer().prefix_translation(string)

def suffix_translation(string: str) -> _TranslationModificationGatherer:
    return _TranslationModificationGatherer().suffix_translation(string)

def modify_outline(modify_outline: Callable[[Outline], Outline]) -> _OutlineModificationGatherer:
    """Translates the outline without any folds, and modifies the outline according to the callback."""
    return _OutlineModificationGatherer(modify_outline)

def prefix_outline(new_strokes_steno: str) -> _OutlineModificationGatherer:
    return _OutlineModificationGatherer().prefix_outline(new_strokes_steno)

def suffix_outline(new_strokes_steno: str) -> _OutlineModificationGatherer:
    return _OutlineModificationGatherer().suffix_outline(new_strokes_steno)

def group_rules(*rules: Rule) -> Rule:
    return Rule(Prerequisite(()), (), rules)


def unfold_suffix():
    """Default folding behavior. Removes the fold from the final stroke and appends the folded chord as a new
    stroke, using the chord's dictionary entry."""

    @LookupStrategy.of
    def handler(defolded_strokes: Outline, folds: Outline, strokes: Outline, translator: Translator):
        foldless_translation = translator.lookup(defolded_strokes)
        if foldless_translation is None:
            return None
        
        fold_chord_translation = translator.lookup((folds[-1],))
        if fold_chord_translation is None:
            return None
        
        return f"{foldless_translation} {fold_chord_translation}"

    return handler

def unfold_prefix():
    @LookupStrategy.of
    def handler(defolded_strokes: Outline, folds: Outline, strokes: Outline, translator: Translator):
        foldless_translation = translator.lookup(defolded_strokes)
        if foldless_translation is None:
            return None
        
        fold_chord_translation = translator.lookup((folds[0],))
        if fold_chord_translation is None:
            return None
    
        return f"{fold_chord_translation} {foldless_translation}"
    
    return handler


def use_defolded_translation():
    @LookupStrategy.of
    def handler(defolded_strokes: Outline, folds: Outline, strokes: Outline, translator: Translator):
        return translator.lookup(defolded_strokes)
    
    return handler

def default_system_rules():
    """Plover's default folding rules, depend on the current system."""

    from plover.system import SUFFIX_KEYS # type: ignore

    return when(last_stroke.folds(*SUFFIX_KEYS)).then(unfold_suffix)