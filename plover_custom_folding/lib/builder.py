from plover.steno import Stroke
from plover.translation import Translator

from typing import Callable


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

def _empty_stroke():
    return Stroke.from_keys(())

def _create_stroke_index_mapping(strokes: _Outline):
    return {
        stroke: i
        for i, stroke in enumerate(strokes)
    }

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
    
    def first_case_satisfied_by(self, filtered_strokes: _Outline) -> "_Case | None":
        """Returns the case which is satisfied by the given outline, or None if no such case exists."""
        for case in self.__cases:
            if case.satisfied_by(filtered_strokes):
                return case
        
        return None
    
    def __repr__(self):
        return f"_Condition(cases={self.__cases})"

class _Clause:
    """Determines whether a chord has been folded into another, and what keys comprise that fold."""

    def __init__(
        self,
        stroke_filter: _StrokeFilter,
        conditions: tuple[_Condition, ...] = (),
    ):
        """A function that returns the strokes to test."""
        self.__stroke_filter = stroke_filter
        self.__conditions = conditions

        # assert not _strokes_overlap(contained_substroke, toggled_substroke)


    def first_cases_satisfied_by(self, strokes: _Outline) -> "tuple[_Case, ...] | None":
        """Returns a tuple of cases which are satisfied by the given outline for each condition, or None if any
        condition fails."""
        cases: list[_Case] = []
        for condition in self.__conditions:
            case = condition.first_case_satisfied_by(self.__stroke_filter(strokes))
            if case is not None:
                cases.append(case)
            else:
                return None
            
        return cases
    

    def folds(self, *substrokes_steno: str) -> "_Clause":
        """Tests if ANY SINGLE given substroke is folded into a set of strokes."""

        substrokes = tuple(Stroke.from_steno(substroke_steno) for substroke_steno in substrokes_steno)
        cases: list[_Case] = []
        for substroke in sorted(substrokes, key=lambda substroke: len(substroke), reverse=True):
            cases.append(_Case(
                substroke,
                _empty_stroke(),
            ))

        return _Clause(
            self.__stroke_filter,
            self.__conditions + (_Condition(tuple(cases)),),
        )

    fold = folds

    def toggles(self, *substrokes_steno: str) -> "_Clause":
        """Tests if ANY SINGLE given substroke is toggled in a set of strokes."""

        substrokes = tuple(Stroke.from_steno(substroke_steno) for substroke_steno in substrokes_steno)
        cases: list[_Case] = []
        for substroke in sorted(substrokes, key=lambda substroke: len(substroke), reverse=True):
            cases.append(_Case(
                _empty_stroke(),
                substroke,
            ))

        return _Clause(
            self.__stroke_filter,
            self.__conditions + (_Condition(tuple(cases)),),
        )
    
    toggle = toggles
    
    def remove_folds(self, strokes: _Outline, *, stroke_index_mapping: "dict[Stroke, int] | None"=None):
        cases = self.first_cases_satisfied_by(strokes)

        new_strokes = list(strokes)
        stroke_index_mapping = stroke_index_mapping or _create_stroke_index_mapping(strokes)
        for stroke in self.__stroke_filter(strokes):
            new_stroke = stroke
            for case in cases:
                new_stroke = case.remove_fold(new_stroke)
            new_strokes[stroke_index_mapping[stroke]] = new_stroke

        return tuple(new_strokes)
    
    def get_folds(self, strokes: _Outline, *, folds: "_Outline | None"=None, stroke_index_mapping: "dict[Stroke, int] | None"=None):
        cases = self.first_cases_satisfied_by(strokes)

        if folds is not None:
            new_folds = list(folds)
        else:
            new_folds = [_empty_stroke() for _ in strokes]
        stroke_index_mapping = stroke_index_mapping or _create_stroke_index_mapping(strokes)
        for stroke in self.__stroke_filter(strokes):
            for case in cases:
                new_folds[stroke_index_mapping[stroke]] += case.fold_substroke

        return tuple(new_folds)
        
    def __repr__(self):
        return f"_Clause(conditions={self.__conditions})"

class _Prerequisite:
    """Bundles a group of `_Clause`s."""

    def __init__(self, clauses: tuple[_Clause]):
        self.__clauses = clauses

    def first_cases_satisfied_by(self, strokes: _Outline):
        """Returns a tuple of tuples of cases which are satisfied by the given outline for each clause, or None if any
        condition fails."""
        cases_by_clause: list[_Case] = []
        for clause in self.__clauses:
            cases = clause.first_cases_satisfied_by(strokes)
            if cases is not None:
                cases_by_clause.append(cases)
            else:
                return None
            
        return cases_by_clause
    
    def remove_folds(self, strokes: _Outline, *, stroke_index_mapping: "dict[Stroke, int] | None"=None):
        stroke_index_mapping = stroke_index_mapping or _create_stroke_index_mapping(strokes)
        for clause in self.__clauses:
            strokes = clause.remove_folds(strokes, stroke_index_mapping=stroke_index_mapping)
    
        return strokes
    
    def get_folds(self, strokes: _Outline, *, stroke_index_mapping: "dict[Stroke, int] | None"=None):
        folds = tuple(_empty_stroke() for _ in strokes)
        stroke_index_mapping = stroke_index_mapping or _create_stroke_index_mapping(strokes)
        for clause in self.__clauses:
            folds = clause.get_folds(strokes, folds=folds, stroke_index_mapping=stroke_index_mapping)

        return folds


_LookupStrategyHandler = Callable[[_Outline, _Outline, _Outline, Translator], tuple[Formatter, str]]

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
        lookup_strategies: tuple[_LookupStrategy],
        additional_rules: "tuple[Rule]"=(),
        alternative_rules: "tuple[Rule]"=(),
    ):
        self.__prerequisite = prerequisite
        self.__lookup_strategies = lookup_strategies
        self.__additional_rules = additional_rules
        self.__alternative_rules = alternative_rules


    __current_global_folds: "tuple[Stroke] | None" = None

    def __call__(self, strokes: _Outline, translator: Translator) -> str:
        cases_by_clause = self.__prerequisite.first_cases_satisfied_by(strokes)
        if cases_by_clause is None:
            return None
        
        stroke_index_mapping = _create_stroke_index_mapping(strokes)

        defolded_strokes = self.__prerequisite.remove_folds(strokes, stroke_index_mapping=stroke_index_mapping)
        folds = self.__prerequisite.get_folds(strokes, stroke_index_mapping=stroke_index_mapping)


        # Ensure that folds between rules do not overlap
        last_folds = Rule.__current_global_folds
        if Rule.__current_global_folds is None:
            Rule.__current_global_folds = folds
        else:
            new_folds: list[Stroke] = []
            for i, fold in enumerate(Rule.__current_global_folds):
                if _strokes_overlap(fold, folds[i]):
                    return None
                
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
    def when(*clauses: _Clause) -> _LookupStrategyGatherer:
        """Gathers clauses that ALL must be true for this rule to be used."""
        return _LookupStrategyGatherer(_Prerequisite(clauses))

    first_stroke: _Clause = _Clause(lambda strokes: (strokes[0],))
    last_stroke: _Clause = _Clause(lambda strokes: (strokes[-1],))
    all_strokes: _Clause = _Clause(lambda strokes: strokes)
    @staticmethod
    def filtered_strokes(stroke_filter: _StrokeFilter):
        return _Clause(stroke_filter)
    

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

        from plover.system import SUFFIX_KEYS

        return f.when(f.last_stroke.folds(*SUFFIX_KEYS)).then(f.unfold_suffix)

f = FoldingRuleBuildUtils