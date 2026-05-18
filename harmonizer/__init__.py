"""Public convenience imports for the Harmonizer Workbench package."""

from .constraints_dsl import (
    A,
    ADJACENT_VOICE_PAIRS,
    ALL_VOICE_PAIRS,
    B,
    S,
    T,
    ConstraintSet,
    RuleSpec,
    avoid_parallel_perfects,
    avoid_similar_motion_into_perfects,
    avoid_voice_crossing,
    cover_chord_tones,
    prepare_leaps,
    prefer_doublings,
    prefer_independent_motion,
    prefer_melodic_intervals,
    prefer_range,
    recover_leaps,
    rulebook,
)
from .rules_api import Note
from .rules_api import FiguredBassFigure
from .rules_api import HarmonyEvent
from .rules_api import HarmonyTone
from .rules_api import PitchValue
from .rules_api import RuleSet
from .rules_api import ScoreBreakdown
from .rules_api import VerticalEvent
from .rules_api import VoiceInterval
from .score_events import load_musicxml_vertical_events
from .score_events import resolve_bcfb_musicxml_path
from .score_events import select_anchor_events
from .score_events import sort_events_by_strength
from .rule_costs import RuleAnalysis
from .rule_costs import analyze_events
from .rule_costs import analyze_musicxml_rules
from .rule_costs import write_cost_rows_csv
from .score_debug import HighlightedScore
from .score_debug import write_cost_highlighted_musicxml

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "A",
    "ADJACENT_VOICE_PAIRS",
    "ALL_VOICE_PAIRS",
    "B",
    "ConstraintSet",
    "RuleSpec",
    "S",
    "T",
    "avoid_parallel_perfects",
    "avoid_similar_motion_into_perfects",
    "avoid_voice_crossing",
    "cover_chord_tones",
    "FiguredBassFigure",
    "HarmonyEvent",
    "HarmonyTone",
    "prefer_range",
    "prefer_doublings",
    "prefer_melodic_intervals",
    "PitchValue",
    "recover_leaps",
    "prepare_leaps",
    "prefer_independent_motion",
    "rulebook",
    "analyze_events",
    "analyze_musicxml_rules",
    "HighlightedScore",
    "load_musicxml_vertical_events",
    "Note",
    "resolve_bcfb_musicxml_path",
    "RuleAnalysis",
    "RuleSet",
    "ScoreBreakdown",
    "select_anchor_events",
    "sort_events_by_strength",
    "VerticalEvent",
    "VoiceInterval",
    "write_cost_highlighted_musicxml",
    "write_cost_rows_csv",
]
