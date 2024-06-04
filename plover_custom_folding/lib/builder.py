from plover.steno import Stroke
from plover.translation import Translator

from dataclasses import dataclass
from typing import Callable
from weakref import WeakKeyDictionary

from .types import Lookup


@dataclass
class FoldingRules:
    lookups: list[Lookup]
    longest_key: int = 8


_StrokeFilter = Callable[[tuple[Stroke, ...]], tuple[Stroke, ...]]
_StrokePredicate = Callable[[tuple[Stroke, ...]], bool]

def _toggle_substroke(stroke: Stroke, substroke: Stroke):
    if substroke in stroke:
        return stroke - substroke
    else:
        return stroke + substroke
    
def _strokes_overlap(a: Stroke, b: Stroke):
    return ~(~a | ~b) != 0

def _empty_stroke():
    return Stroke.from_keys(())

def _create_stroke_index_mapping(strokes: tuple[Stroke, ...]):
    return {
        stroke: i
        for i, stroke in enumerate(strokes)
    }


class _Clause:
    """Determines whether a chord has been folded into another, and what keys comprise that fold."""

    def __init__(
        self,
        stroke_filter: _StrokeFilter,
        stroke_predicate: _StrokePredicate = lambda stroke: True,
        fold_substroke = _empty_stroke(),
        
        contained_substroke = _empty_stroke(),
        toggled_substroke = _empty_stroke(),
    ):
        """A function that returns the strokes to test."""
        self.__stroke_filter = stroke_filter
        """The condition to test on the strokes given by `stroke_filter`."""
        self.__stroke_predicate = stroke_predicate
        self.__fold_substroke = fold_substroke

        self.__contained_substroke = contained_substroke
        self.__toggled_substroke = toggled_substroke

        assert not _strokes_overlap(contained_substroke, toggled_substroke)


    def satisfied_by(self, strokes: tuple[Stroke, ...]):
        return all(self.__stroke_predicate(stroke) for stroke in self.__stroke_filter(strokes))
    

    def folds(self, substroke_steno: str) -> "_Clause":
        substroke = Stroke.from_steno(substroke_steno)
        return _Clause(
            self.__stroke_filter,
            lambda stroke: self.__stroke_predicate(stroke) and substroke in stroke,
            self.__fold_substroke + substroke,

            self.__contained_substroke + substroke,
            self.__toggled_substroke,
        )

    fold = folds

    def folds_toggled(self, substroke_steno: str) -> "_Clause":
        substroke = Stroke.from_steno(substroke_steno)
        return _Clause(
            self.__stroke_filter,
            self.__stroke_predicate,
            self.__fold_substroke + substroke,

            self.__contained_substroke,
            self.__toggled_substroke + substroke,
        )
    
    fold_toggled = folds_toggled
    
    def remove_folds(self, strokes: tuple[Stroke, ...], *, stroke_index_mapping: "dict[Stroke, int] | None"=None):
        new_strokes = list(strokes)
        stroke_index_mapping = stroke_index_mapping or _create_stroke_index_mapping(strokes)
        for stroke in self.__stroke_filter(strokes):
            new_strokes[stroke_index_mapping[stroke]] = _toggle_substroke(stroke - self.__contained_substroke, self.__toggled_substroke)
        return tuple(new_strokes)
    
    def get_folds(self, strokes: tuple[Stroke, ...], *, folds: "tuple[Stroke, ...] | None"=None, stroke_index_mapping: "dict[Stroke, int] | None"=None):
        new_folds = list(folds) if folds is not None else list(_empty_stroke() for _ in strokes)
        stroke_index_mapping = stroke_index_mapping or _create_stroke_index_mapping(strokes)
        for stroke in self.__stroke_filter(strokes):
            new_folds[stroke_index_mapping[stroke]] += self.__fold_substroke
        return tuple(new_folds)
        

class _Prerequisite:
    """Bundles a group of `_Clause`s."""

    def __init__(self, clauses: tuple[_Clause]):
        self.__clauses = clauses

    def satisfied_by(self, strokes: tuple[Stroke, ...]):
        return all(clause.satisfied_by(strokes) for clause in self.__clauses)
    
    def remove_folds(self, strokes: tuple[Stroke, ...], *, stroke_index_mapping: "dict[Stroke, int] | None"=None):
        stroke_index_mapping = stroke_index_mapping or _create_stroke_index_mapping(strokes)
        for clause in self.__clauses:
            strokes = clause.remove_folds(strokes, stroke_index_mapping=stroke_index_mapping)
    
        return strokes
    
    def get_folds(self, strokes: tuple[Stroke, ...], *, stroke_index_mapping: "dict[Stroke, int] | None"=None):
        folds = tuple(_empty_stroke() for _ in strokes)
        stroke_index_mapping = stroke_index_mapping or _create_stroke_index_mapping(strokes)
        for clause in self.__clauses:
            folds = clause.get_folds(strokes, folds=folds, stroke_index_mapping=stroke_index_mapping)

        return folds



_LookupStrategyHandler = Callable[[tuple[Stroke, ...], tuple[Stroke, ...], tuple[Stroke, ...], Translator], "str | None"]

class _LookupStrategy:
    """Manipulates the input strokes and folded chords, queries the main translator, and produces new translations."""

    def __init__(self, handler: _LookupStrategyHandler):
        self.__handler = handler

    @staticmethod
    def of(fn: _LookupStrategyHandler):
        return _LookupStrategy(fn)
    
    def __call__(self, strokes_without_folds: tuple[Stroke, ...], folds: tuple[Stroke, ...], strokes: tuple[Stroke, ...], translator: Translator) -> "str | None":
        return self.__handler(strokes_without_folds, folds, strokes, translator)


class _Rule:
    def __init__(
        self,
        prerequisite: _Prerequisite,
        lookup_strategies: tuple[_LookupStrategy],
        additional_rules: "tuple[_Rule]"=(),
    ):
        self.__prerequisite = prerequisite
        self.__lookup_strategies = lookup_strategies
        self.__additional_rules = additional_rules

    def __call__(self, strokes: tuple[Stroke, ...], translator: Translator) -> str:
        if not self.__prerequisite.satisfied_by(strokes):
            raise KeyError
        
        stroke_index_mapping = _create_stroke_index_mapping(strokes)

        strokes_without_folds = self.__prerequisite.remove_folds(strokes, stroke_index_mapping=stroke_index_mapping)
        folds = self.__prerequisite.get_folds(strokes, stroke_index_mapping=stroke_index_mapping)

        for additional_rule in self.__additional_rules:
            try:
                return additional_rule(strokes_without_folds, translator)
            except KeyError:
                continue


        for lookup in self.__lookup_strategies:
            new_translation = lookup(strokes_without_folds, folds, strokes, translator)
            if new_translation is not None:
                return new_translation

        raise KeyError
    
    def unless_also(self, *additional_rules: "_Rule"):
        return _Rule(self.__prerequisite, self.__lookup_strategies, self.__additional_rules + additional_rules)


class _LookupStrategyGatherer:
    def __init__(self, prerequisite: _Prerequisite):
        self.__prerequisite = prerequisite

    def then(self, *lookup_strategies: _LookupStrategy):
        return _Rule(self.__prerequisite, lookup_strategies)
    


class FoldingRuleBuildUtils:
    def when(*clauses: _Clause):
        return _LookupStrategyGatherer(_Prerequisite(clauses))

    first_stroke: _Clause = _Clause(lambda strokes: (strokes[0],))
    last_stroke: _Clause = _Clause(lambda strokes: (strokes[-1],))
    all_strokes: _Clause = _Clause(lambda strokes: strokes)
    @staticmethod
    def filtered_strokes(stroke_filter: _StrokeFilter):
        return _Clause(stroke_filter)
    
    @staticmethod
    def modify_translation(modify_translation: Callable[[str], str]):
        """Translates the outline without any folds, and modifies the translation according to the callback."""

        @_LookupStrategy.of
        def handler(strokes_without_folds: tuple[Stroke, ...], folds: tuple[Stroke, ...], strokes: tuple[Stroke, ...], translator: Translator):
            foldless_translation = translator.lookup(strokes_without_folds)
            if foldless_translation is None:
                return None
                        
            return modify_translation(foldless_translation)

        return handler
    
    @staticmethod
    def prepend_to_translation(string: str):
        return FoldingRuleBuildUtils.modify_translation(lambda translation: f"{string}{translation}")
        
    @staticmethod
    def append_to_translation(string: str):
        return FoldingRuleBuildUtils.modify_translation(lambda translation: f"{translation}{string}")
    
    @staticmethod
    @_LookupStrategy.of
    def unfold_suffix(strokes_without_folds: tuple[Stroke, ...], folds: tuple[Stroke, ...], strokes: tuple[Stroke, ...], translator: Translator):
        """Default folding behavior. Removes the fold from the final stroke and appends the folded chord as a new
        stroke, using the chord's dictionary entry."""

        foldless_translation = translator.lookup(strokes_without_folds)
        if foldless_translation is None:
            return None
        
        fold_chord_translation = translator.lookup((folds[-1],))
        if fold_chord_translation is None:
            return None
        
        return f"{foldless_translation} {fold_chord_translation}"