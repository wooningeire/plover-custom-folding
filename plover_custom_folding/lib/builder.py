from plover.steno import Stroke
from plover.translation import Translator

from typing import Callable, Generator, TypeVar


T = TypeVar("T")

Lookup = Callable[[tuple[Stroke], Translator], str]
Formatter = Callable[[str], str]

_Outline = tuple[Stroke, ...]
_StrokeFilter = Callable[[_Outline], _Outline]

def _toggle_substroke(stroke: Stroke, substroke: Stroke):
    if substroke in stroke:
        return stroke - substroke
    else:
        return stroke + substroke
    
def _strokes_overlap(a: Stroke, b: Stroke):
    return ~(~a | ~b) != 0

def _empty_stroke() -> Stroke:
    return Stroke.from_keys(())

def _create_stroke_index_mapping(strokes: _Outline):
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

def _case_groups(options: "tuple[tuple[_Case, ...], ...]", stroke_filter: _StrokeFilter):
    yield from (_CaseGroup(*((case, stroke_filter) for case in cases)) for cases in _all_combinations(options))

class _Case:
    def __init__(
        self,
        contained_substroke: Stroke,
        toggled_substroke: Stroke,
    ):
        self.__contained_substroke = contained_substroke
        self.__toggled_substroke = toggled_substroke

    def satisfied_by(self, filtered_strokes: _Outline):
        return all(self.__contained_substroke in stroke for stroke in filtered_strokes)
    
    def remove_fold(self, stroke: Stroke):
        return _toggle_substroke(stroke - self.__contained_substroke, self.__toggled_substroke)
    
    @property
    def fold_substroke(self):
        return self.__contained_substroke + self.__toggled_substroke
    
    def __repr__(self):
        return f"_Case(contained={self.__contained_substroke}, toggled={self.__toggled_substroke})"

class _Condition:
    def __init__(
        self,
        cases: tuple[_Case, ...]
    ):
        self.__cases = cases
    
    def satisifed_cases(self, filtered_strokes: _Outline):
        """Returns the case which is satisfied by the given outline, or None if no such case exists."""
        for case in self.__cases:
            if case.satisfied_by(filtered_strokes):
                yield case
    
    def __repr__(self):
        return f"_Condition(cases={self.__cases})"

class _CaseGroup:
    def __init__(self, *cases_and_filters: tuple[_Case, _StrokeFilter]):
        self.__cases_and_filters = cases_and_filters

    def __iter__(self):
        return self.__cases_and_filters.__iter__()

    def remove_folds(self, strokes: _Outline, *, stroke_index_mapping: "dict[Stroke, int] | None"=None):
        new_strokes = list(strokes)
        stroke_index_mapping = stroke_index_mapping or _create_stroke_index_mapping(strokes)
        for case, stroke_filter in self.__cases_and_filters:
            for stroke in stroke_filter(strokes):
                new_strokes[stroke_index_mapping[stroke]] = case.remove_fold(new_strokes[stroke_index_mapping[stroke]])

        return tuple(new_strokes)
    
    def get_folds(self, strokes: _Outline, *, folds: "_Outline | None"=None, stroke_index_mapping: "dict[Stroke, int] | None"=None):
        if folds is not None:
            new_folds = list(folds)
        else:
            new_folds = [_empty_stroke() for _ in strokes]
        
        stroke_index_mapping = stroke_index_mapping or _create_stroke_index_mapping(strokes)
        for case, stroke_filter in self.__cases_and_filters:
            for stroke in stroke_filter(strokes):
                new_folds[stroke_index_mapping[stroke]] += case.fold_substroke

        return tuple(new_folds)
    
    def merge(self, case_group: "_CaseGroup"):
        return _CaseGroup(*self.__cases_and_filters, *case_group.__cases_and_filters)
    
    def __repr__(self):
        return f"_CaseGroup(cases={self.__cases_and_filters})"
    
class _Clause:
    """Determines whether a substroke has been folded into a stroke, and what keys comprise that fold."""

    def __init__(
        self,
        stroke_filter: _StrokeFilter,
        conditions: tuple[_Condition, ...],
    ):
        """A function that returns the strokes to test."""
        self.__stroke_filter = stroke_filter
        self.__conditions = conditions

        # assert not _strokes_overlap(contained_substroke, toggled_substroke)

    def satisfied_case_groups(self, strokes: _Outline):
        """Generates all groups of cases which are satisfied by the given outline for each condition."""

        case_combinations = tuple(tuple(condition.satisifed_cases(self.__stroke_filter(strokes))) for condition in self.__conditions)
        for case_group in _case_groups(case_combinations, self.__stroke_filter):
            yield case_group
        
    def __repr__(self):
        return f"_Clause(conditions={self.__conditions})"


class _Statement:
    def __init__(self, conjunctive: bool, substatements: "tuple[_Statement | _Clause, ...]"):
        self.__conjunctive = conjunctive
        self.__substatements = substatements

    def satisfied_case_groups(self, strokes: _Outline):
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

class _Prerequisite:
    """Bundles a group of `_Statement`s."""

    def __init__(self, elements: "tuple[_Statement | _Clause, ...]"):
        self.__elements = elements
    
    def satisfied_folds(self, strokes: _Outline):
        """Generates all groups of cases which are satisfied by the given outline for each clause, or None if any
        condition fails."""
        stroke_index_mapping = _create_stroke_index_mapping(strokes)
        
        for element in self.__elements:
            for case_group in element.satisfied_case_groups(strokes):
                defolded_strokes = case_group.remove_folds(strokes, stroke_index_mapping=stroke_index_mapping)
                folds = case_group.get_folds(strokes, stroke_index_mapping=stroke_index_mapping)

                yield defolded_strokes, folds


_LookupStrategyHandler = Callable[[_Outline, _Outline, _Outline, Translator], "str | None"]

class _LookupStrategy:
    """Manipulates the input strokes and folded chords, queries the main translator, and produces new translations."""

    def __init__(self, handler: _LookupStrategyHandler):
        self.__handler = handler

    @staticmethod
    def of(fn: _LookupStrategyHandler):
        return _LookupStrategy(fn)
    
    def __call__(self, defolded_strokes: _Outline, folds: _Outline, strokes: _Outline, translator: Translator) -> "str | None":
        return self.__handler(defolded_strokes, folds, strokes, translator)


class Rule:
    def __init__(
        self,
        prerequisite: _Prerequisite,
        lookup_strategies: tuple[_LookupStrategy, ...],
        additional_rules: "tuple[Rule, ...]"=(),
        alternative_rules: "tuple[Rule, ...]"=(),
    ):
        self.__prerequisite = prerequisite
        self.__lookup_strategies = lookup_strategies
        self.__additional_rules = additional_rules
        self.__alternative_rules = alternative_rules


    __current_global_folds: "tuple[Stroke, ...] | None" = None

    def __call__(self, strokes: _Outline, translator: Translator) -> "str | None":
        if len(strokes[0].keys()) == 0:
            return None

        for defolded_strokes, folds in self.__prerequisite.satisfied_folds(strokes):
            # Ensure that folds between rules do not overlap
            last_folds = Rule.__current_global_folds
            if Rule.__current_global_folds is None:
                Rule.__current_global_folds = folds
            else:
                new_folds: list[Stroke] = []
                for i, fold in enumerate(Rule.__current_global_folds):
                    if _strokes_overlap(fold, folds[i]):
                        continue
                    
                    new_folds.append(fold + folds[i])

                Rule.__current_global_folds = tuple(new_folds)


            # Check additional rules before the main rule
            for additional_rule in self.__additional_rules:
                translation = additional_rule(defolded_strokes, translator)
                if translation is not None:
                    Rule.__current_global_folds = None
                    return translation

            for lookup in self.__lookup_strategies:
                translation = lookup(defolded_strokes, folds, strokes, translator)
                if translation is not None:
                    Rule.__current_global_folds = None
                    return translation

            for alternative_rule in self.__alternative_rules:
                translation = alternative_rule(defolded_strokes, translator)
                if translation is not None:
                    Rule.__current_global_folds = None
                    return translation
        
            Rule.__current_global_folds = last_folds

        return None
    
    def or_also(self, *alternative_rules: "Rule"):
        return Rule(self.__prerequisite, self.__lookup_strategies, self.__additional_rules, self.__alternative_rules + alternative_rules)
    
    def unless_also(self, *additional_rules: "Rule"):
        return Rule(self.__prerequisite, self.__lookup_strategies, self.__additional_rules + additional_rules, self.__alternative_rules)


class _ClauseBuilder:
    def __init__(
        self,
        stroke_filter: _StrokeFilter,
        conditions: tuple[_Condition, ...] = (),
    ):
        """A function that returns the strokes to test."""
        self.__stroke_filter = stroke_filter
        self.__conditions = conditions


    def __call__(self) -> _Clause:
        return _Clause(self.__stroke_filter, self.__conditions)
    

    def folds(self, *substrokes_steno: str):
        """Tests if ANY SINGLE given substroke is folded into a set of strokes."""

        substrokes = tuple(Stroke.from_steno(substroke_steno) for substroke_steno in substrokes_steno)
        cases: list[_Case] = []
        for substroke in sorted(substrokes, key=lambda substroke: len(substroke), reverse=True):
            cases.append(_Case(
                substroke,
                _empty_stroke(),
            ))

        return _ClauseBuilder(
            self.__stroke_filter,
            self.__conditions + (_Condition(tuple(cases)),),
        )

    fold = folds

    def toggles(self, *substrokes_steno: str):
        """Tests if ANY SINGLE given substroke is toggled in a set of strokes."""

        substrokes = tuple(Stroke.from_steno(substroke_steno) for substroke_steno in substrokes_steno)
        cases: list[_Case] = []
        for substroke in sorted(substrokes, key=lambda substroke: len(substroke), reverse=True):
            cases.append(_Case(
                _empty_stroke(),
                substroke,
            ))

        return _ClauseBuilder(
            self.__stroke_filter,
            self.__conditions + (_Condition(tuple(cases)),),
        )
    
    toggle = toggles

class _LookupStrategyGatherer:
    def __init__(self, prerequisite: _Prerequisite):
        self.__prerequisite = prerequisite

    def then(self, *lookup_strategy_creators: Callable[[], _LookupStrategy]):
        """Gathers a list of lookup strategies that are run IN ORDER and INDEPENDENTLY."""
        return Rule(self.__prerequisite, tuple(create_lookup_strategy() for create_lookup_strategy in lookup_strategy_creators))
    
    def and_also(self, *rules: Rule):
        return Rule(self.__prerequisite, ()).unless_also(*rules)
    

class _TranslationModificationGatherer:
    def __init__(
        self,
        modify_translation: Callable[[str], str]=lambda translation: translation,
        modify_outline: Callable[[_Outline], _Outline]=lambda strokes: strokes,
    ):
        self.__modify_outline = modify_outline
        self.__modify_translation = modify_translation


    def __call__(self) -> _LookupStrategy:
        @_LookupStrategy.of
        def handler(defolded_strokes: _Outline, folds: _Outline, strokes: _Outline, translator: Translator):
            foldless_translation = translator.lookup(self.__modify_outline(defolded_strokes))
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
    def __init__(self, modify_outline: Callable[[_Outline], _Outline]=lambda strokes: strokes):
        self.__modify_outline = modify_outline


    def __call__(self) -> _LookupStrategy:
        return self.__to_translation_modification_gatherer()()


    def __to_translation_modification_gatherer(self, modify_translation: Formatter=lambda translation: translation) -> _TranslationModificationGatherer:
        return _TranslationModificationGatherer(modify_translation, self.__modify_outline)


    def modify_translation(self, modify_translation: Formatter=lambda translation: translation) -> _TranslationModificationGatherer:
        """Translates the outline without any folds, and modifies the translation according to the callback."""
        return self.__to_translation_modification_gatherer(modify_translation)
    
    def prefix_translation(self, string: str) -> _TranslationModificationGatherer:
        return self.__to_translation_modification_gatherer().prefix_translation(string)
        
    def suffix_translation(self, string: str) -> _TranslationModificationGatherer:
        return self.__to_translation_modification_gatherer().suffix_translation(string)
    
    def modify_outline(self, modify_outline: Callable[[_Outline], _Outline]) -> "_OutlineModificationGatherer":
        """Translates the outline without any folds, and modifies the translation according to the callback."""
        return _OutlineModificationGatherer(lambda translation: modify_outline(self.__modify_outline(translation)))
    
    def prefix_outline(self, new_strokes_steno: str) -> "_OutlineModificationGatherer":
        new_strokes = tuple(Stroke.from_steno(stroke_steno) for stroke_steno in new_strokes_steno.split("/"))
        return self.modify_outline(lambda strokes: new_strokes[:-1] + (new_strokes[-1] + strokes[0],) + strokes[1:])
        
    def suffix_outline(self, new_strokes_steno: str) -> "_OutlineModificationGatherer":
        new_strokes = tuple(Stroke.from_steno(stroke_steno) for stroke_steno in new_strokes_steno.split("/"))
        return self.modify_outline(lambda strokes: strokes[:-1] + (new_strokes[0] + strokes[-1],) + new_strokes[1:])


class FoldingRuleBuildUtils:
    @staticmethod
    def when(*builders: "Callable[[], _Statement | _Clause]") -> _LookupStrategyGatherer:
        """Gathers statements at least one of which must be true for this rule to be used."""
        return _LookupStrategyGatherer(_Prerequisite(tuple(create() for create in builders)))
    
    @staticmethod
    def when_all(*builders: "Callable[[], _Statement | _Clause]") -> _LookupStrategyGatherer:
        """Gathers statements all of which must be true for this rule to be used."""
        return f.when(f.all(*builders))

    first_stroke: _ClauseBuilder = _ClauseBuilder(lambda strokes: (strokes[0],))
    last_stroke: _ClauseBuilder = _ClauseBuilder(lambda strokes: (strokes[-1],))
    all_strokes: _ClauseBuilder = _ClauseBuilder(lambda strokes: strokes)
    @staticmethod
    def nth_stroke(index: int):
        return _ClauseBuilder(lambda strokes: (strokes[index],))
    
    @staticmethod
    def filtered_strokes(stroke_filter: _StrokeFilter):
        return _ClauseBuilder(stroke_filter)
    

    @staticmethod
    def all(*builders: "Callable[[], _Statement | _Clause]"):
        return lambda: _Statement(True, tuple(create() for create in builders))

    @staticmethod
    def any_single(*builders: "Callable[[], _Statement | _Clause]"):
        return lambda: _Statement(False, tuple(create() for create in builders))
    

    @staticmethod
    def modify_translation(modify_translation: Formatter=lambda translation: translation) -> _TranslationModificationGatherer:
        """Translates the outline without any folds, and modifies the translation according to the callback."""
        return _TranslationModificationGatherer(modify_translation)
    
    @staticmethod
    def prefix_translation(string: str) -> _TranslationModificationGatherer:
        return _TranslationModificationGatherer().prefix_translation(string)
        
    @staticmethod
    def suffix_translation(string: str) -> _TranslationModificationGatherer:
        return _TranslationModificationGatherer().suffix_translation(string)
    
    @staticmethod
    def modify_outline(modify_outline: Callable[[_Outline], _Outline]) -> _OutlineModificationGatherer:
        """Translates the outline without any folds, and modifies the outline according to the callback."""
        return _OutlineModificationGatherer(modify_outline)
    
    @staticmethod
    def prefix_outline(new_strokes_steno: str) -> _OutlineModificationGatherer:
        return _OutlineModificationGatherer().prefix_outline(new_strokes_steno)
        
    @staticmethod
    def suffix_outline(new_strokes_steno: str) -> _OutlineModificationGatherer:
        return _OutlineModificationGatherer().suffix_outline(new_strokes_steno)
    
    @staticmethod
    def group_rules(*rules: Rule) -> Rule:
        return Rule(_Prerequisite(()), (), rules)
    
    
    @staticmethod
    def unfold_suffix():
        """Default folding behavior. Removes the fold from the final stroke and appends the folded chord as a new
        stroke, using the chord's dictionary entry."""

        @_LookupStrategy.of
        def handler(defolded_strokes: _Outline, folds: _Outline, strokes: _Outline, translator: Translator):
            foldless_translation = translator.lookup(defolded_strokes)
            if foldless_translation is None:
                return None
            
            fold_chord_translation = translator.lookup((folds[-1],))
            if fold_chord_translation is None:
                return None
            
            return f"{foldless_translation} {fold_chord_translation}"

        return handler
    
    @staticmethod
    def unfold_prefix():
        @_LookupStrategy.of
        def handler(defolded_strokes: _Outline, folds: _Outline, strokes: _Outline, translator: Translator):
            foldless_translation = translator.lookup(defolded_strokes)
            if foldless_translation is None:
                return None
            
            fold_chord_translation = translator.lookup((folds[0],))
            if fold_chord_translation is None:
                return None
        
            return f"{fold_chord_translation} {foldless_translation}"
        
        return handler
    

    @staticmethod
    def use_defolded_translation():
        @_LookupStrategy.of
        def handler(defolded_strokes: _Outline, folds: _Outline, strokes: _Outline, translator: Translator):
            return translator.lookup(defolded_strokes)
        
        return handler
    

    @staticmethod
    def default_system_rules():
        """Plover's default folding rules, depend on the current system."""

        from plover.system import SUFFIX_KEYS # type: ignore

        return f.when(f.last_stroke.folds(*SUFFIX_KEYS)).then(f.unfold_suffix)

f = FoldingRuleBuildUtils