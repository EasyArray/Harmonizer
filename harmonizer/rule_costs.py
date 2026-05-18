"""Scoring engine for declarative rulebooks.

The scorer converts ``ConstraintSet`` objects into per-event costs. It is used
by notebooks, CSV reports, and highlighted-score debugging output.
"""

from __future__ import annotations

from dataclasses import dataclass
import csv
from pathlib import Path
from typing import Literal, Sequence

from .constraints_dsl import ConstraintSet, RuleSpec
from .rules_api import (
    A,
    B,
    S,
    T,
    PitchValue,
    VerticalEvent,
    VoiceInterval,
    VoiceName,
)
from .score_events import load_musicxml_vertical_events

ScoreScope = Literal["hybrid", "anchors", "all"]

VOICE_HEIGHT = {
    B: 0,
    T: 1,
    A: 2,
    S: 3,
}

HARMONIC_SINGLE_EVENT_RULES = {
    "cover_chord_tones",
    "prefer_doublings",
}

MOTION_RULES = {
    "avoid_parallel_perfects",
    "avoid_similar_motion_into_perfects",
    "prefer_independent_motion",
}

SINGLE_EVENT_RULES = {
    "avoid_voice_crossing",
    "prefer_range",
    "prefer_melodic_intervals",
    "recover_leaps",
    "prepare_leaps",
} | HARMONIC_SINGLE_EVENT_RULES


@dataclass(frozen=True)
class RuleAnalysis:
    """Per-event rule-cost table plus metadata about the analyzed score."""

    events: tuple[VerticalEvent, ...]
    rows: tuple[dict[str, object], ...]
    rule_columns: tuple[str, ...]
    anchor_indices: tuple[int, ...]
    anchor_threshold: float
    score_scope: ScoreScope

    def totals_by_rule(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for row in self.rows:
            for column in self.rule_columns:
                totals[column] = totals.get(column, 0.0) + float(row[column])
        return totals

    def high_cost_rows(
        self,
        *,
        limit: int = 20,
        minimum_cost: float = 0.0,
        anchors_only: bool = False,
    ) -> tuple[dict[str, object], ...]:
        rows = [
            row
            for row in self.rows
            if float(row["total_cost"]) > minimum_cost
            and (not anchors_only or row["is_anchor"] == "yes")
        ]
        rows.sort(key=lambda row: float(row["total_cost"]), reverse=True)
        return tuple(rows[:limit])


def analyze_musicxml_rules(
    musicxml_path: str | Path,
    rules: ConstraintSet,
    *,
    anchor_threshold: float = 0.45,
    score_scope: ScoreScope = "hybrid",
) -> RuleAnalysis:
    """Load MusicXML and analyze it with a declarative rulebook."""

    events = load_musicxml_vertical_events(musicxml_path)
    return analyze_events(
        events,
        rules,
        anchor_threshold=anchor_threshold,
        score_scope=score_scope,
    )


def analyze_events(
    events: Sequence[VerticalEvent],
    rules: ConstraintSet,
    *,
    anchor_threshold: float = 0.45,
    score_scope: ScoreScope = "hybrid",
) -> RuleAnalysis:
    """Analyze an in-memory event stream with a declarative rulebook.

    ``score_scope`` controls whether harmony and motion rules use all events,
    only strong anchor events, or a hybrid of both.
    """

    if score_scope not in ("hybrid", "anchors", "all"):
        raise ValueError("score_scope must be 'hybrid', 'anchors', or 'all'.")

    normalized_events = tuple(events)
    anchor_indices = tuple(
        index for index, event in enumerate(normalized_events) if event.is_anchor(anchor_threshold)
    )
    anchor_index_set = set(anchor_indices)

    change_indices = {
        voice: [index for index, event in enumerate(normalized_events) if event.voice_changed(voice)]
        for voice in (S, A, T, B)
    }
    change_positions = {
        voice: {event_index: position for position, event_index in enumerate(indices)}
        for voice, indices in change_indices.items()
    }

    costs_by_index: list[dict[str, float]] = [dict() for _ in normalized_events]
    rule_columns: list[str] = []

    def add_column(column: str) -> None:
        if column not in rule_columns:
            rule_columns.append(column)

    def add_cost(event_index: int, column: str, cost: float) -> None:
        if cost == 0:
            return
        add_column(column)
        costs_by_index[event_index][column] = costs_by_index[event_index].get(column, 0.0) + cost

    for rule in rules.enabled_rules():
        if rule.kind not in SINGLE_EVENT_RULES and rule.kind not in MOTION_RULES:
            raise ValueError(f"Unsupported rule kind for analysis: {rule.kind!r}")

        for column in _columns_for_rule(rule):
            add_column(column)

        if rule.kind in SINGLE_EVENT_RULES:
            for event_index, event in enumerate(normalized_events):
                if not _include_event_for_single_rule(rule, event_index, anchor_index_set, score_scope):
                    continue
                for column, cost in _single_event_costs(
                    rule,
                    normalized_events,
                    event_index,
                    change_indices,
                    change_positions,
                ):
                    add_cost(event_index, column, cost)

        if rule.kind in MOTION_RULES:
            motion_indices = _motion_event_indices(normalized_events, anchor_index_set, score_scope)
            for before_index, after_index in zip(motion_indices, motion_indices[1:]):
                cost = _motion_rule_cost(rule, normalized_events[before_index], normalized_events[after_index])
                add_cost(after_index, _rule_column(rule), cost)

    rows = tuple(
        _row_for_event(
            event,
            event_index,
            costs_by_index[event_index],
            rule_columns,
            anchor_index_set,
        )
        for event_index, event in enumerate(normalized_events)
    )

    return RuleAnalysis(
        events=normalized_events,
        rows=rows,
        rule_columns=tuple(rule_columns),
        anchor_indices=anchor_indices,
        anchor_threshold=anchor_threshold,
        score_scope=score_scope,
    )


def write_cost_rows_csv(path: str | Path, analysis: RuleAnalysis, *, rows: Sequence[dict[str, object]] | None = None) -> Path:
    """Write analysis rows to a CSV file and return the output path."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected_rows = tuple(rows) if rows is not None else analysis.rows
    fieldnames = list(selected_rows[0].keys()) if selected_rows else []
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(selected_rows)
    return output_path


def _include_event_for_single_rule(
    rule: RuleSpec,
    event_index: int,
    anchor_index_set: set[int],
    score_scope: ScoreScope,
) -> bool:
    if score_scope == "all":
        return True
    if score_scope == "anchors":
        return event_index in anchor_index_set
    if rule.kind in HARMONIC_SINGLE_EVENT_RULES:
        return event_index in anchor_index_set
    return True


def _motion_event_indices(
    events: Sequence[VerticalEvent],
    anchor_index_set: set[int],
    score_scope: ScoreScope,
) -> tuple[int, ...]:
    if score_scope in ("hybrid", "anchors"):
        return tuple(index for index in range(len(events)) if index in anchor_index_set)
    return tuple(range(len(events)))


def _single_event_costs(
    rule: RuleSpec,
    events: Sequence[VerticalEvent],
    event_index: int,
    change_indices: dict[VoiceName, list[int]],
    change_positions: dict[VoiceName, dict[int, int]],
) -> list[tuple[str, float]]:
    event = events[event_index]
    if rule.kind == "cover_chord_tones":
        return [(_rule_column(rule), _missing_required_chord_tones(event, rule))]
    if rule.kind == "avoid_voice_crossing":
        return [(_rule_column(rule), _voice_crossing(event, rule))]
    if rule.kind == "prefer_range":
        return _range_costs(event, rule)
    if rule.kind == "prefer_doublings":
        return [(_rule_column(rule), _doubling_preference(event, rule))]
    if rule.kind == "prefer_melodic_intervals":
        return _melodic_interval_costs(event, rule)
    if rule.kind == "recover_leaps":
        return _leap_costs(events, event_index, rule, change_indices, change_positions, look="after")
    if rule.kind == "prepare_leaps":
        return _leap_costs(events, event_index, rule, change_indices, change_positions, look="before")
    raise ValueError(f"Unsupported single-event rule: {rule.kind!r}")


def _missing_required_chord_tones(event: VerticalEvent, rule: RuleSpec) -> float:
    harmony = event.harmony()
    if harmony is None:
        return 0.0

    present_pcs = {pitch.pitch_class for pitch in event.sounding_pitches() if pitch is not None}
    present_letters = {pitch.letter for pitch in event.sounding_pitches() if pitch is not None}
    costs = rule.params.get("costs", {})
    inversion_costs = rule.params.get("costs_by_inversion", {}).get(harmony.inversion or "", {})
    chromatic_same_letter_ok = bool(rule.params.get("chromatic_same_letter_ok", True))
    unfigured_scale = float(rule.params.get("unfigured_scale", 1.0))
    scale = unfigured_scale if not harmony.explicit_intervals else 1.0

    total = 0.0
    for tone in harmony.tones:
        if _tone_is_present(
            tone.pitch,
            present_pcs=present_pcs,
            present_letters=present_letters,
            chromatic_same_letter_ok=chromatic_same_letter_ok,
            require_exact=tone.accidental is not None,
        ):
            continue
        role = tone.role or ("explicit" if tone.explicit else "other")
        cost = inversion_costs.get(role, costs.get(role, rule.params["missing_required"]))
        total += float(cost)
    return total * scale


def _tone_is_present(
    pitch: PitchValue,
    *,
    present_pcs: set[int],
    present_letters: set[str],
    chromatic_same_letter_ok: bool,
    require_exact: bool,
) -> bool:
    if pitch.pitch_class in present_pcs:
        return True
    if require_exact or not chromatic_same_letter_ok:
        return False
    return pitch.letter in present_letters


def _voice_crossing(event: VerticalEvent, rule: RuleSpec) -> float:
    penalty = float(rule.params["penalty"])
    allow_equal = bool(rule.params.get("allow_equal", True))
    total = 0.0

    for left, right in rule.params["pairs"]:
        upper, lower = _upper_lower(left, right)
        upper_pitch = event.pitch(upper)
        lower_pitch = event.pitch(lower)
        if upper_pitch is None or lower_pitch is None:
            continue
        if allow_equal:
            crosses = upper_pitch.midi < lower_pitch.midi
        else:
            crosses = upper_pitch.midi <= lower_pitch.midi
        if crosses:
            total += penalty
    return total


def _range_costs(event: VerticalEvent, rule: RuleSpec) -> list[tuple[str, float]]:
    cost_per_semitone = float(rule.params["cost_per_semitone"])
    free_semitones = float(rule.params.get("free_semitones", 0))
    costs: list[tuple[str, float]] = []
    for voice, center_text in rule.params["centers"].items():
        pitch = event.pitch(voice)
        if pitch is None:
            continue
        center = PitchValue.parse(center_text)
        distance = max(0.0, abs(center - pitch) - free_semitones)
        costs.append((_rule_column(rule, voice), distance * cost_per_semitone))
    return costs


def _doubling_preference(event: VerticalEvent, rule: RuleSpec) -> float:
    harmony = event.harmony()
    if harmony is None:
        return 0.0

    role_counts: dict[str, int] = {}
    for voice in (S, A, T, B):
        role = harmony.role_for_pitch(event.pitch(voice))
        if role is not None:
            role_counts[role] = role_counts.get(role, 0) + 1

    costs = rule.params["costs"]
    total = 0.0
    for role, count in role_counts.items():
        if count > 1:
            total += float(costs.get(role, 0.0)) * (count - 1)
    return total


def _melodic_interval_costs(event: VerticalEvent, rule: RuleSpec) -> list[tuple[str, float]]:
    costs: list[tuple[str, float]] = []
    interval_costs = rule.params["costs"]
    for voice in rule.params["voices"]:
        if not event.voice_changed(voice):
            continue
        previous_pitch = event.previous_pitch(voice)
        current_pitch = event.pitch(voice)
        if previous_pitch is None or current_pitch is None:
            continue
        interval = VoiceInterval(voice, voice, previous_pitch, current_pitch)
        costs.append((_rule_column(rule, voice), float(interval_costs.get(_melodic_bucket(interval), 0.0))))
    return costs


def _leap_costs(
    events: Sequence[VerticalEvent],
    event_index: int,
    rule: RuleSpec,
    change_indices: dict[VoiceName, list[int]],
    change_positions: dict[VoiceName, dict[int, int]],
    *,
    look: Literal["before", "after"],
) -> list[tuple[str, float]]:
    if rule.params["require"] not in ("step_opposite", "stepwise_opposite", "step_opposite_or_hold"):
        raise ValueError(f"Unsupported leap requirement: {rule.params['require']!r}")

    costs: list[tuple[str, float]] = []
    for voice in rule.params["voices"]:
        cost = _single_voice_leap_cost(
            events,
            event_index,
            voice,
            rule,
            change_indices,
            change_positions,
            look=look,
        )
        costs.append((_rule_column(rule, voice), cost))
    return costs


def _single_voice_leap_cost(
    events: Sequence[VerticalEvent],
    event_index: int,
    voice: VoiceName,
    rule: RuleSpec,
    change_indices: dict[VoiceName, list[int]],
    change_positions: dict[VoiceName, dict[int, int]],
    *,
    look: Literal["before", "after"],
) -> float:
    event = events[event_index]
    if not event.voice_changed(voice):
        return 0.0

    previous_pitch = event.previous_pitch(voice)
    current_pitch = event.pitch(voice)
    if previous_pitch is None or current_pitch is None:
        return 0.0

    current_motion = VoiceInterval(voice, voice, previous_pitch, current_pitch)
    if not _larger_than_threshold(current_motion, rule.params["leap_gt"]):
        return 0.0

    position = change_positions[voice].get(event_index)
    if position is None:
        return 0.0

    comparison_motion: VoiceInterval | None = None
    if look == "before" and position >= 2:
        previous_event_index = change_indices[voice][position - 1]
        previous_previous_event_index = change_indices[voice][position - 2]
        first = events[previous_previous_event_index].pitch(voice)
        second = events[previous_event_index].pitch(voice)
        if first is not None and second is not None:
            comparison_motion = VoiceInterval(voice, voice, first, second)
    elif look == "after" and position + 1 < len(change_indices[voice]):
        next_event = events[change_indices[voice][position + 1]]
        next_pitch = next_event.pitch(voice)
        if next_pitch is not None:
            comparison_motion = VoiceInterval(voice, voice, current_pitch, next_pitch)

    if comparison_motion is None:
        return 0.0

    allows_hold = rule.params["require"] == "step_opposite_or_hold"
    first_motion = comparison_motion if look == "before" else current_motion
    second_motion = current_motion if look == "before" else comparison_motion
    if _is_stepwise_opposite(first_motion, second_motion, allows_hold=allows_hold):
        return 0.0
    return float(rule.params["penalty"])


def _motion_rule_cost(rule: RuleSpec, before_event: VerticalEvent, after_event: VerticalEvent) -> float:
    total = 0.0
    for voice_a, voice_b in rule.params["pairs"]:
        motion = _pair_motion_between(before_event, after_event, voice_a, voice_b)
        if motion is None:
            continue

        if rule.kind == "avoid_parallel_perfects":
            if motion.is_parallel:
                total += _perfect_interval_cost(rule, motion.after)
        elif rule.kind == "avoid_similar_motion_into_perfects":
            if not motion.is_parallel and motion.is_similar_into_perfect:
                if rule.params.get("require_upper_leap", False) and not _upper_voice_leaped(
                    before_event,
                    after_event,
                    voice_a,
                    voice_b,
                ):
                    continue
                total += _perfect_interval_cost(rule, motion.after)
        elif rule.kind == "prefer_independent_motion":
            ignore_if_perfect = bool(rule.params.get("ignore_if_perfect_rule_applies", True))
            if ignore_if_perfect and (motion.is_parallel or motion.is_similar_into_perfect):
                continue
            total += float(rule.params["costs"].get(motion.motion_type, 0.0))
        else:
            raise ValueError(f"Unsupported motion rule: {rule.kind!r}")
    return total


def _pair_motion_between(
    before_event: VerticalEvent,
    after_event: VerticalEvent,
    voice_a: VoiceName,
    voice_b: VoiceName,
):
    before_a = before_event.pitch(voice_a)
    before_b = before_event.pitch(voice_b)
    after_a = after_event.pitch(voice_a)
    after_b = after_event.pitch(voice_b)
    if before_a is None or before_b is None or after_a is None or after_b is None:
        return None
    previous_interval = VoiceInterval(voice_a, voice_b, before_a, before_b)
    current_interval = VoiceInterval(voice_a, voice_b, after_a, after_b)
    return previous_interval.motion_to(current_interval)


def _perfect_interval_cost(rule: RuleSpec, interval: VoiceInterval) -> float:
    costs = rule.params["costs"]
    if interval.is_unison:
        return float(costs.get("unison", 0.0))
    if interval.is_octave:
        return float(costs.get("octave", 0.0))
    if interval.is_fifth:
        return float(costs.get("fifth", 0.0))
    return 0.0


def _upper_voice_leaped(
    before_event: VerticalEvent,
    after_event: VerticalEvent,
    voice_a: VoiceName,
    voice_b: VoiceName,
) -> bool:
    upper, _ = _upper_lower(voice_a, voice_b)
    before_pitch = before_event.pitch(upper)
    after_pitch = after_event.pitch(upper)
    if before_pitch is None or after_pitch is None:
        return False
    melodic_interval = VoiceInterval(upper, upper, before_pitch, after_pitch)
    return melodic_interval.simple_number > 2


def _row_for_event(
    event: VerticalEvent,
    event_index: int,
    costs: dict[str, float],
    rule_columns: Sequence[str],
    anchor_index_set: set[int],
) -> dict[str, object]:
    harmony = event.harmony()
    strength_components = dict(event.metadata.get("strength_components", {}))
    row: dict[str, object] = {
        "index": event.index if event.index is not None else event_index,
        "offset": round(event.offset or 0.0, 3),
        "measure": event.measure,
        "beat": round(event.beat or 0.0, 3),
        "beat_strength": round(event.beat_strength, 3),
        "event_strength": round(event.event_strength, 3),
        "is_anchor": "yes" if event_index in anchor_index_set else "no",
        "changed_voices": ",".join(event.changed_voices),
        "figure_changed": "yes" if event.figure_changed else "no",
        "figures": harmony.figure_text if harmony is not None else "",
        "required_pitch_classes": _pitch_classes_text(harmony.required_pitch_classes() if harmony else ()),
        "soprano": str(event.soprano) if event.soprano else "",
        "alto": str(event.alto) if event.alto else "",
        "tenor": str(event.tenor) if event.tenor else "",
        "bass": str(event.bass) if event.bass else "",
        "strength_from_beat": round(float(strength_components.get("beat", 0.0)), 3),
        "strength_from_figure": round(float(strength_components.get("figure", 0.0)), 3),
        "strength_from_soprano": round(float(strength_components.get("soprano", 0.0)), 3),
        "strength_from_bass": round(float(strength_components.get("bass", 0.0)), 3),
        "strength_from_alto": round(float(strength_components.get("alto", 0.0)), 3),
        "strength_from_tenor": round(float(strength_components.get("tenor", 0.0)), 3),
    }
    for column in rule_columns:
        row[column] = round(costs.get(column, 0.0), 3)
    row["total_cost"] = round(sum(float(row[column]) for column in rule_columns), 3)
    return row


def _rule_column(rule: RuleSpec, suffix: str | None = None) -> str:
    base = rule.label or rule.kind
    if suffix:
        return f"{base}:{suffix}"
    return base


def _columns_for_rule(rule: RuleSpec) -> tuple[str, ...]:
    if rule.kind in ("prefer_range", "prefer_melodic_intervals", "recover_leaps", "prepare_leaps"):
        key = "centers" if rule.kind == "prefer_range" else "voices"
        return tuple(_rule_column(rule, voice) for voice in rule.params[key])
    return (_rule_column(rule),)


def _upper_lower(left: VoiceName, right: VoiceName) -> tuple[VoiceName, VoiceName]:
    if VOICE_HEIGHT[left] >= VOICE_HEIGHT[right]:
        return left, right
    return right, left


def _melodic_bucket(interval: VoiceInterval) -> str:
    if interval.simple_number == 1:
        return "unison"
    size = interval.simple_number
    if size == 2:
        return "step"
    if size == 3:
        return "third"
    if size == 4:
        return "fourth"
    if size == 5:
        return "fifth"
    if size == 6:
        return "sixth"
    if size == 7:
        return "seventh"
    return "octave_or_larger"


def _larger_than_threshold(interval: VoiceInterval, threshold: str) -> bool:
    threshold_numbers = {
        "step": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "octave": 8,
    }
    return interval.simple_number > threshold_numbers[threshold]


def _is_stepwise_opposite(
    first_motion: VoiceInterval,
    second_motion: VoiceInterval,
    *,
    allows_hold: bool,
) -> bool:
    if allows_hold and _direction(second_motion.pitch_a, second_motion.pitch_b) == 0:
        return True
    if second_motion.simple_number != 2:
        return False
    first_direction = _direction(first_motion.pitch_a, first_motion.pitch_b)
    second_direction = _direction(second_motion.pitch_a, second_motion.pitch_b)
    return first_direction != 0 and second_direction == -first_direction


def _direction(before: PitchValue, after: PitchValue) -> int:
    if after.midi > before.midi:
        return 1
    if after.midi < before.midi:
        return -1
    return 0


def _pitch_classes_text(pitch_classes: Sequence[int]) -> str:
    return "/".join(str(pc) for pc in pitch_classes)
