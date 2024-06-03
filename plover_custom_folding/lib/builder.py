from plover.steno import Stroke
from plover.translation import Translator

from dataclasses import dataclass
from typing import Callable

from .types import Lookup


@dataclass
class FoldingRules:
    lookups: list[Lookup]
    longest_key: int = 8


_StrokeFilter = Callable[[tuple[Stroke]], tuple[Stroke]]
_StrokePredicate = Callable[[tuple[Stroke]], bool]

def _toggle_substroke(stroke: Stroke, substroke: Stroke):
    if substroke in stroke:
        return stroke - substroke
    else:
        return stroke + substroke
    
def _strokes_overlap(a: Stroke, b: Stroke):
    return ~(~a | ~b) != 0

def _empty_stroke():
    return Stroke.from_keys(())


class _Condition:
    """Determines whether a chord has been folded into another, and what keys comprise that fold."""

    def __init__(
        self,
        stroke_filter: _StrokeFilter,
        stroke_predicate: _StrokePredicate = lambda stroke: True,
        fold_substroke = _empty_stroke(),
        
        contained_substroke = _empty_stroke(),
        toggled_substroke = _empty_stroke(),
    ):
        self.__stroke_filter = stroke_filter
        self.__stroke_predicate = stroke_predicate
        self.__fold_substroke = fold_substroke

        self.__contained_substroke = contained_substroke
        self.__toggled_substroke = toggled_substroke

        assert not _strokes_overlap(contained_substroke, toggled_substroke)


    def __call__(self, strokes: tuple[Stroke]):
        return all(self.__stroke_predicate(stroke) for stroke in self.__stroke_filter(strokes))
    

    def folds(self, substroke_steno: str) -> "_Condition":
        substroke = Stroke.from_steno(substroke_steno)
        return _Condition(
            self.__stroke_filter,
            lambda stroke: self.__stroke_predicate(stroke) and substroke in stroke,
            self.__fold_substroke + substroke,

            self.__contained_substroke + substroke,
            self.__toggled_substroke,
        )

    fold = folds

    def folds_toggled(self, substroke_steno: str) -> "_Condition":
        substroke = Stroke.from_steno(substroke_steno)
        return _Condition(
            self.__stroke_filter,
            self.__stroke_predicate,
            self.__fold_substroke + substroke,

            self.__contained_substroke,
            self.__toggled_substroke + substroke,
        )
    
    fold_toggled = folds_toggled
    
    def remove_folds(self, strokes: tuple[Stroke]):
        return tuple(_toggle_substroke(stroke - self.__contained_substroke, self.__toggled_substroke) for stroke in strokes)

        
class _ConditionList:
    """Bundles a group of `_Condition`s."""

    def __init__(self, conditions: tuple[_Condition]):
        self.__conditions = conditions

    def all_satisfied(self, strokes: tuple[Stroke]):
        return all(condition(strokes) for condition in self.__conditions)
    
    def remove_folds(self, strokes: tuple[Stroke]):
        for condition in self.__conditions:
            strokes = condition.remove_folds(strokes)
    
        return strokes


_LookupStrategyHandler = Callable[[tuple[Stroke], Translator], "str | None"]

class _LookupStrategy:
    """Manipulates the input strokes and folded chords, queries the main translator, and produces new translations."""

    def __init__(self, handler: _LookupStrategyHandler):
        self.__handler = handler

    @staticmethod
    def of(fn: _LookupStrategyHandler):
        return _LookupStrategy(fn)
    
    def __call__(self, strokes_without_folds: tuple[Stroke], translator: Translator) -> "str | None":
        return self.__handler(strokes_without_folds, translator)


class _Rule:
    def __init__(
        self,
        condition_list: _ConditionList,
        lookup_strategies: tuple[_LookupStrategy],
        additional_rules: "tuple[_Rule]"=(),
    ):
        self.__condition_list = condition_list
        self.__lookup_strategies = lookup_strategies
        self.__additional_rules = additional_rules

    def __call__(self, strokes: tuple[Stroke], translator: Translator) -> str:
        if not self.__condition_list.all_satisfied(strokes):
            raise KeyError
        
        strokes_without_folds = self.__condition_list.remove_folds(strokes)

        for additional_rule in self.__additional_rules:
            try:
                return additional_rule(strokes_without_folds, translator)
            except KeyError:
                continue


        for lookup in self.__lookup_strategies:
            new_translation = lookup(strokes_without_folds, translator)
            if new_translation is not None:
                return new_translation

        raise KeyError
    
    def unless_also(self, *additional_rules: "tuple[_Rule]"):
        return _Rule(self.__condition_list, self.__lookup_strategies, self.__additional_rules + additional_rules)


class _LookupStrategyGatherer:
    def __init__(self, condition_list: _ConditionList):
        self.__condition_list = condition_list

    def then(self, *lookup_strategies: tuple[_LookupStrategy]):
        return _Rule(self.__condition_list, lookup_strategies)
    

class _ConditionGatherer():
    def __call__(self, *conditions: tuple[_Condition]):
        return _LookupStrategyGatherer(_ConditionList(conditions))


class FoldingRuleBuildHelper:
    when = _ConditionGatherer()

    first_stroke: _Condition = _Condition(lambda strokes: (strokes[0],))
    last_stroke: _Condition = _Condition(lambda strokes: (strokes[-1],))
    all_strokes: _Condition = _Condition(lambda strokes: strokes)
    @staticmethod
    def filtered_strokes(stroke_filter: _StrokeFilter):
        return _Condition(stroke_filter)
    
    @staticmethod
    def modify_translation(modify_translation: Callable[[str], str]):
        @_LookupStrategy.of
        def handler(strokes_without_folds: tuple[Stroke], translator: Translator):
            result = translator.lookup(strokes_without_folds)
            if result is None:
                return None
            
            return modify_translation(result)

        return handler
    