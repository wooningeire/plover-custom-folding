from plover.steno import Stroke
from plover.translation import Translator
import plover.log

from typing import Callable, Generator, TypeVar


T = TypeVar("T")

Lookup = Callable[[tuple[Stroke], Translator], str]
Formatter = Callable[[str], str]

Outline = tuple[Stroke, ...]
StrokeFilter = Callable[[Outline], Outline]

def _toggle_substroke(stroke: Stroke, substroke: Stroke):
    if substroke in stroke:
        return stroke - substroke
    else:
        return stroke + substroke
    
def _strokes_overlap(a: Stroke, b: Stroke):
    return ~(~a | ~b) != 0  # De Morgan's Law

def empty_stroke() -> Stroke:
    return Stroke.from_keys(())

def _create_stroke_index_mapping(strokes: Outline):
    return {
        stroke: i
        for i, stroke in enumerate(strokes)
    }


def _all_combinations(options: "tuple[tuple[T, ...], ...]", *, last_index=-1) -> "Generator[tuple[T, ...], None, None]":
    if len(options) + last_index < 0:
        yield ()
        return

    for option in options[last_index]:
        for combination in _all_combinations(options, last_index=last_index - 1):
            yield (*combination, option)

def _case_groups(options: "tuple[tuple[Case, ...], ...]", stroke_filter: StrokeFilter):
    yield from (_CaseGroup(*((case, stroke_filter) for case in cases)) for cases in _all_combinations(options))

class Case:
    def __init__(
        self,
        contained_substroke: Stroke,
        toggled_substroke: Stroke,
    ):
        self.__contained_substroke = contained_substroke
        self.__toggled_substroke = toggled_substroke

    def satisfied_by(self, filtered_strokes: Outline):
        return all(self.__contained_substroke in stroke for stroke in filtered_strokes)
    
    def remove_fold(self, stroke: Stroke):
        return _toggle_substroke(stroke - self.__contained_substroke, self.__toggled_substroke)
    
    @property
    def fold_substroke(self):
        return self.__contained_substroke + self.__toggled_substroke
    
    def __repr__(self):
        return f"_Case(contained={self.__contained_substroke}, toggled={self.__toggled_substroke})"

class Condition:
    def __init__(
        self,
        cases: tuple[Case, ...]
    ):
        self.__cases = cases
    
    def satisifed_cases(self, filtered_strokes: Outline):
        """Returns the case which is satisfied by the given outline, or None if no such case exists."""
        for case in self.__cases:
            if case.satisfied_by(filtered_strokes):
                yield case
    
    def __repr__(self):
        return f"_Condition(cases={self.__cases})"

class _CaseGroup:
    def __init__(self, *cases_and_filters: tuple[Case, StrokeFilter]):
        self.__cases_and_filters = cases_and_filters

    def __iter__(self):
        return self.__cases_and_filters.__iter__()

    def remove_folds(self, strokes: Outline, *, stroke_index_mapping: "dict[Stroke, int] | None"=None):
        new_strokes = list(strokes)
        stroke_index_mapping = stroke_index_mapping or _create_stroke_index_mapping(strokes)
        for case, stroke_filter in self.__cases_and_filters:
            for stroke in stroke_filter(strokes):
                new_strokes[stroke_index_mapping[stroke]] = case.remove_fold(new_strokes[stroke_index_mapping[stroke]])

        return tuple(new_strokes)
    
    def get_folds(self, strokes: Outline, *, folds: "Outline | None"=None, stroke_index_mapping: "dict[Stroke, int] | None"=None):
        if folds is not None:
            new_folds = list(folds)
        else:
            new_folds = [empty_stroke() for _ in strokes]
        
        stroke_index_mapping = stroke_index_mapping or _create_stroke_index_mapping(strokes)
        for case, stroke_filter in self.__cases_and_filters:
            for stroke in stroke_filter(strokes):
                new_folds[stroke_index_mapping[stroke]] += case.fold_substroke

        return tuple(new_folds)
    
    def merge(self, case_group: "_CaseGroup"):
        return _CaseGroup(*self.__cases_and_filters, *case_group.__cases_and_filters)
    
    def __repr__(self):
        return f"_CaseGroup(cases={self.__cases_and_filters})"
    
class Clause:
    """Determines whether a substroke has been folded into a stroke, and what keys comprise that fold."""

    def __init__(
        self,
        stroke_filter: StrokeFilter,
        conditions: tuple[Condition, ...],
    ):
        """A function that returns the strokes to test."""
        self.__stroke_filter = stroke_filter
        self.__conditions = conditions

        # assert not _strokes_overlap(contained_substroke, toggled_substroke)

    def satisfied_case_groups(self, strokes: Outline):
        """Generates all groups of cases which are satisfied by the given outline for each condition."""

        case_combinations = tuple(tuple(condition.satisifed_cases(self.__stroke_filter(strokes))) for condition in self.__conditions)
        for case_group in _case_groups(case_combinations, self.__stroke_filter):
            yield case_group
        
    def __repr__(self):
        return f"_Clause(conditions={self.__conditions})"


class Statement:
    def __init__(self, conjunctive: bool, substatements: "tuple[Statement | Clause, ...]"):
        self.__conjunctive = conjunctive
        self.__substatements = substatements

    def satisfied_case_groups(self, strokes: Outline):
        """Generates all groups of cases which are satisfied by the given outline for each condition."""

        if self.__conjunctive:
            case_group_sequences = tuple(tuple(substatement.satisfied_case_groups(strokes)) for substatement in self.__substatements)

            running_case_group = _CaseGroup()
            for case_group_sequence in _all_combinations(case_group_sequences):
                for case_group in case_group_sequence:
                    running_case_group = running_case_group.merge(case_group)
            
            yield running_case_group
            return

        for substatement in self.__substatements:
            satisfied = False
            
            for case_group in substatement.satisfied_case_groups(strokes):
                satisfied = True
                yield case_group

            if satisfied:
                return

class Prerequisite:
    """Bundles a group of `_Statement`s."""

    def __init__(self, elements: "tuple[Statement | Clause, ...]"):
        self.__elements = elements
    
    def satisfied_folds(self, strokes: Outline):
        """Generates all groups of cases which are satisfied by the given outline for each clause."""
        stroke_index_mapping = _create_stroke_index_mapping(strokes)
        
        for element in self.__elements:
            for case_group in element.satisfied_case_groups(strokes):
                defolded_strokes = case_group.remove_folds(strokes, stroke_index_mapping=stroke_index_mapping)
                folds = case_group.get_folds(strokes, stroke_index_mapping=stroke_index_mapping)

                yield defolded_strokes, folds


_LookupStrategyHandler = Callable[[Outline, Outline, Outline, Translator], "str | None"]

class LookupStrategy:
    """Manipulates the input strokes and folded chords, queries the main translator, and produces new translations."""

    def __init__(self, handler: _LookupStrategyHandler):
        self.__handler = handler

    @staticmethod
    def of(fn: _LookupStrategyHandler):
        return LookupStrategy(fn)
    
    def __call__(self, defolded_strokes: Outline, folds: Outline, strokes: Outline, translator: Translator) -> "str | None":
        return self.__handler(defolded_strokes, folds, strokes, translator)


class Rule:
    def __init__(
        self,
        prerequisite: Prerequisite,
        lookup_strategies: tuple[LookupStrategy, ...],
        additional_rules: "tuple[Rule, ...]"=(),
        alternative_rules: "tuple[Rule, ...]"=(),
        allow_shorter_outline: bool=False,
    ):
        self.__prerequisite = prerequisite
        self.__lookup_strategies = lookup_strategies
        self.__additional_rules = additional_rules
        self.__alternative_rules = alternative_rules
        self.__allow_shorter_outline = allow_shorter_outline


    check_additional_folds = True
    shorter_outline_found = False

    __current_folds: "tuple[Stroke, ...] | None" = None
    __unmatched_rules: "dict[Outline, set[Rule]]" = {}  # for memoization
    @classmethod
    def clear_unmatched_rules(cls):
        cls.__unmatched_rules.clear()

    def __call__(self, strokes: Outline, translator: Translator, shorter_outline_found: bool) -> "str | None":
        if strokes in Rule.__unmatched_rules and self in Rule.__unmatched_rules[strokes]:
            return None

        if len(strokes[0]) == 0:
            return None
        
        if shorter_outline_found and not self.__allow_shorter_outline:
            return None

        for defolded_strokes, folds in self.__prerequisite.satisfied_folds(strokes):
            # Ensure that folds between rules do not overlap
            last_folds = Rule.__current_folds
            if Rule.__current_folds is None:
                Rule.__current_folds = folds
            else:
                new_folds: list[Stroke] = []
                overlap_found = False
                for i, fold in enumerate(Rule.__current_folds):
                    if _strokes_overlap(fold, folds[i]):
                        overlap_found = True
                        break
                    
                    new_folds.append(fold + folds[i])

                if overlap_found:
                    continue

                Rule.__current_folds = tuple(new_folds)

            # Removing folds will not affect rules that already don't match
            if strokes in Rule.__unmatched_rules:
                Rule.__unmatched_rules[defolded_strokes] = set(Rule.__unmatched_rules[strokes])
            else:
                Rule.__unmatched_rules[defolded_strokes] = set()

            # Check additional rules before the main rule
            for additional_rule in self.__additional_rules:
                translation = additional_rule(defolded_strokes, translator, shorter_outline_found)
                if translation is not None:
                    Rule.__current_folds = last_folds
                    return translation

            for lookup in self.__lookup_strategies:
                translation = lookup(defolded_strokes, folds, strokes, translator)
                if translation is not None:
                    Rule.__current_folds = last_folds
                    return translation

            for alternative_rule in self.__alternative_rules:
                translation = alternative_rule(defolded_strokes, translator, shorter_outline_found)
                if translation is not None:
                    Rule.__current_folds = last_folds
                    return translation
                
        
            Rule.__current_folds = last_folds
            del Rule.__unmatched_rules[defolded_strokes]

        if strokes in Rule.__unmatched_rules:
            Rule.__unmatched_rules[strokes].add(self)
        else:
            Rule.__unmatched_rules[strokes] = {self}

        return None
    
    def or_also(self, *alternative_rules: "Rule"):
        return Rule(self.__prerequisite, self.__lookup_strategies, self.__additional_rules, self.__alternative_rules + alternative_rules, self.__allow_shorter_outline)
    
    def unless_also(self, *additional_rules: "Rule"):
        return Rule(self.__prerequisite, self.__lookup_strategies, self.__additional_rules + additional_rules, self.__alternative_rules, self.__allow_shorter_outline)
    
    def preferring_folds(self):
        return Rule(self.__prerequisite, self.__lookup_strategies, self.__additional_rules, self.__alternative_rules, True)
