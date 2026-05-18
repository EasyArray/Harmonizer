"""Declarative harmony-rule objects used by notebooks and examples.

This module is deliberately small: each public constructor validates one rule
shape and returns plain data. The scoring engine in ``rule_costs`` can then
interpret those rule specs without executing arbitrary notebook callbacks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Iterable, Literal, Mapping, Sequence

VoiceName = Literal["soprano", "alto", "tenor", "bass"]
IntervalName = Literal[
    "unison",
    "step",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "octave_or_larger",
]

S: VoiceName = "soprano"
A: VoiceName = "alto"
T: VoiceName = "tenor"
B: VoiceName = "bass"

ADJACENT_VOICE_PAIRS: tuple[tuple[VoiceName, VoiceName], ...] = (
    (S, A),
    (A, T),
    (T, B),
)

ALL_VOICE_PAIRS: tuple[tuple[VoiceName, VoiceName], ...] = (
    (S, A),
    (S, T),
    (S, B),
    (A, T),
    (A, B),
    (T, B),
)

VALID_VOICES = {S, A, T, B}
VALID_INTERVALS = {
    "unison",
    "step",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "octave_or_larger",
}
VALID_THRESHOLDS = {"step", "third", "fourth", "fifth", "sixth", "seventh", "octave"}
VALID_MOTION_TYPES = {"contrary", "oblique", "similar"}
VALID_CHORD_TONE_ROLES = {"root", "third", "fifth", "seventh", "ninth", "explicit", "other"}
VALID_REQUIREMENTS = {
    "step_opposite",
    "stepwise_opposite",
    "step_opposite_or_hold",
    "custom",
}
PITCH_RE = re.compile(r"^(?P<letter>[A-Ga-g])(?P<accidental>bb|##|x|b|#|-|n|nat)?(?P<octave>\d+)$")


@dataclass(frozen=True)
class RuleSpec:
    """A validated rule declaration.

    ``kind`` names the scoring behavior, while ``params`` contains only plain
    JSON-serializable values. Labels and notes are optional presentation fields.
    """

    kind: str
    params: dict[str, Any]
    enabled: bool = True
    label: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "kind": self.kind,
            "enabled": self.enabled,
            "params": _plain_data(self.params),
        }
        if self.label:
            payload["label"] = self.label
        if self.notes:
            payload["notes"] = self.notes
        return payload


@dataclass(frozen=True)
class ConstraintSet:
    """A named collection of rule declarations."""

    name: str
    rules: tuple[RuleSpec, ...]
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def enabled_rules(self) -> tuple[RuleSpec, ...]:
        return tuple(rule for rule in self.rules if rule.enabled)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "rules": [rule.to_dict() for rule in self.rules],
        }
        if self.description:
            payload["description"] = self.description
        if self.metadata:
            payload["metadata"] = _plain_data(self.metadata)
        return payload

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def rulebook(
    name: str,
    *rules: RuleSpec,
    description: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ConstraintSet:
    """Build a named rulebook from already-validated rule specs."""

    if not name.strip():
        raise ValueError("Constraint-set name must not be empty.")
    return ConstraintSet(
        name=name.strip(),
        rules=tuple(rules),
        description=description.strip() if description else None,
        metadata=dict(metadata or {}),
    )


def cover_chord_tones(
    *,
    missing_required: int | None = None,
    root: int | None = None,
    third: int | None = None,
    fifth: int | None = None,
    seventh: int | None = None,
    ninth: int | None = None,
    explicit: int | None = None,
    other: int | None = None,
    unfigured_scale: float = 1.0,
    chromatic_same_letter_ok: bool = True,
    by_inversion: Mapping[str, Mapping[str, int]] | None = None,
    enabled: bool = True,
    label: str | None = None,
    notes: str | None = None,
) -> RuleSpec:
    """Require important pitch classes implied by the bass and figures.

    Costs can be role-specific, so omitted thirds may matter much more than
    omitted fifths. Unfigured default events can also be downweighted.
    """

    fallback = 500 if missing_required is None else _nonnegative(missing_required, "missing_required")
    return RuleSpec(
        kind="cover_chord_tones",
        enabled=enabled,
        label=label,
        notes=notes,
        params={
            "missing_required": fallback,
            "costs": {
                "root": _nonnegative(root, "root") if root is not None else fallback,
                "third": _nonnegative(third, "third") if third is not None else fallback,
                "fifth": _nonnegative(fifth, "fifth") if fifth is not None else fallback,
                "seventh": _nonnegative(seventh, "seventh") if seventh is not None else fallback,
                "ninth": _nonnegative(ninth, "ninth") if ninth is not None else fallback,
                "explicit": _nonnegative(explicit, "explicit") if explicit is not None else fallback,
                "other": _nonnegative(other, "other") if other is not None else fallback,
            },
            "costs_by_inversion": _normalize_inversion_costs(by_inversion),
            "unfigured_scale": _nonnegative_float(unfigured_scale, "unfigured_scale"),
            "chromatic_same_letter_ok": bool(chromatic_same_letter_ok),
        },
    )


def avoid_voice_crossing(
    *,
    penalty: int,
    pairs: Sequence[tuple[VoiceName, VoiceName]] = ADJACENT_VOICE_PAIRS,
    allow_equal: bool = True,
    enabled: bool = True,
    label: str | None = None,
    notes: str | None = None,
) -> RuleSpec:
    """Penalize strict voice crossing between selected voice pairs."""

    return RuleSpec(
        kind="avoid_voice_crossing",
        enabled=enabled,
        label=label,
        notes=notes,
        params={
            "penalty": _nonnegative(penalty, "penalty"),
            "pairs": _normalize_pairs(pairs),
            "allow_equal": bool(allow_equal),
        },
    )


def prefer_range(
    *,
    alto: str | None = None,
    tenor: str | None = None,
    cost_per_semitone: int,
    free_semitones: int = 0,
    enabled: bool = True,
    label: str | None = None,
    notes: str | None = None,
) -> RuleSpec:
    """Prefer soft center pitches for selected voices."""

    centers: dict[str, str] = {}
    if alto is not None:
        centers[A] = _normalize_pitch_literal(alto)
    if tenor is not None:
        centers[T] = _normalize_pitch_literal(tenor)
    if not centers:
        raise ValueError("prefer_range() needs at least one target voice center.")

    return RuleSpec(
        kind="prefer_range",
        enabled=enabled,
        label=label,
        notes=notes,
        params={
            "centers": centers,
            "cost_per_semitone": _nonnegative(cost_per_semitone, "cost_per_semitone"),
            "free_semitones": _nonnegative(free_semitones, "free_semitones"),
        },
    )


def prefer_doublings(
    *,
    root: int,
    fifth: int,
    third: int,
    seventh: int,
    enabled: bool = True,
    label: str | None = None,
    notes: str | None = None,
) -> RuleSpec:
    """Penalize duplicated harmonic roles such as doubled thirds or sevenths."""

    return RuleSpec(
        kind="prefer_doublings",
        enabled=enabled,
        label=label,
        notes=notes,
        params={
            "costs": {
                "root": _nonnegative(root, "root"),
                "fifth": _nonnegative(fifth, "fifth"),
                "third": _nonnegative(third, "third"),
                "seventh": _nonnegative(seventh, "seventh"),
            }
        },
    )


def prefer_melodic_intervals(
    *,
    voices: Sequence[VoiceName],
    unison: int,
    step: int,
    third: int,
    fourth: int,
    fifth: int,
    sixth: int,
    seventh: int,
    octave_or_larger: int,
    enabled: bool = True,
    label: str | None = None,
    notes: str | None = None,
) -> RuleSpec:
    """Assign costs to melodic interval sizes for selected voices."""

    return RuleSpec(
        kind="prefer_melodic_intervals",
        enabled=enabled,
        label=label,
        notes=notes,
        params={
            "voices": _normalize_voices(voices),
            "costs": _interval_costs(
                unison=unison,
                step=step,
                third=third,
                fourth=fourth,
                fifth=fifth,
                sixth=sixth,
                seventh=seventh,
                octave_or_larger=octave_or_larger,
            ),
        },
    )


def recover_leaps(
    *,
    voices: Sequence[VoiceName],
    leap_gt: str,
    require: str,
    penalty: int,
    enabled: bool = True,
    label: str | None = None,
    notes: str | None = None,
) -> RuleSpec:
    """Penalize large leaps that are not recovered by opposite stepwise motion."""

    return RuleSpec(
        kind="recover_leaps",
        enabled=enabled,
        label=label,
        notes=notes,
        params={
            "voices": _normalize_voices(voices),
            "leap_gt": _normalize_threshold(leap_gt),
            "require": _normalize_requirement(require),
            "penalty": _nonnegative(penalty, "penalty"),
        },
    )


def prepare_leaps(
    *,
    voices: Sequence[VoiceName],
    leap_gt: str,
    require: str,
    penalty: int,
    enabled: bool = True,
    label: str | None = None,
    notes: str | None = None,
) -> RuleSpec:
    """Penalize large leaps that are not prepared by opposite stepwise motion."""

    return RuleSpec(
        kind="prepare_leaps",
        enabled=enabled,
        label=label,
        notes=notes,
        params={
            "voices": _normalize_voices(voices),
            "leap_gt": _normalize_threshold(leap_gt),
            "require": _normalize_requirement(require),
            "penalty": _nonnegative(penalty, "penalty"),
        },
    )


def avoid_parallel_perfects(
    *,
    pairs: Sequence[tuple[VoiceName, VoiceName]],
    fifth: int,
    octave: int,
    unison: int | None = None,
    enabled: bool = True,
    label: str | None = None,
    notes: str | None = None,
) -> RuleSpec:
    """Penalize parallel fifths, octaves, and optionally unisons."""

    costs = {
        "fifth": _nonnegative(fifth, "fifth"),
        "octave": _nonnegative(octave, "octave"),
    }
    if unison is not None:
        costs["unison"] = _nonnegative(unison, "unison")
    return RuleSpec(
        kind="avoid_parallel_perfects",
        enabled=enabled,
        label=label,
        notes=notes,
        params={
            "pairs": _normalize_pairs(pairs),
            "costs": costs,
        },
    )


def avoid_similar_motion_into_perfects(
    *,
    pairs: Sequence[tuple[VoiceName, VoiceName]],
    fifth: int,
    octave: int,
    unison: int | None = None,
    require_upper_leap: bool = False,
    enabled: bool = True,
    label: str | None = None,
    notes: str | None = None,
) -> RuleSpec:
    """Penalize similar motion into perfect intervals."""

    costs = {
        "fifth": _nonnegative(fifth, "fifth"),
        "octave": _nonnegative(octave, "octave"),
    }
    if unison is not None:
        costs["unison"] = _nonnegative(unison, "unison")
    return RuleSpec(
        kind="avoid_similar_motion_into_perfects",
        enabled=enabled,
        label=label,
        notes=notes,
        params={
            "pairs": _normalize_pairs(pairs),
            "costs": costs,
            "require_upper_leap": bool(require_upper_leap),
        },
    )


def prefer_independent_motion(
    *,
    pairs: Sequence[tuple[VoiceName, VoiceName]],
    contrary: int = 0,
    oblique: int = 0,
    similar: int = 0,
    ignore_if_perfect_rule_applies: bool = True,
    enabled: bool = True,
    label: str | None = None,
    notes: str | None = None,
) -> RuleSpec:
    """Nudge selected voice pairs toward contrary or oblique motion."""

    return RuleSpec(
        kind="prefer_independent_motion",
        enabled=enabled,
        label=label,
        notes=notes,
        params={
            "pairs": _normalize_pairs(pairs),
            "costs": {
                "contrary": _nonnegative(contrary, "contrary"),
                "oblique": _nonnegative(oblique, "oblique"),
                "similar": _nonnegative(similar, "similar"),
            },
            "ignore_if_perfect_rule_applies": bool(ignore_if_perfect_rule_applies),
        },
    )


def _nonnegative(value: int, label: str) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{label} must be an integer, got {type(value).__name__}.")
    if value < 0:
        raise ValueError(f"{label} must be nonnegative, got {value}.")
    return value


def _nonnegative_float(value: float, label: str) -> float:
    if not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a number, got {type(value).__name__}.")
    if value < 0:
        raise ValueError(f"{label} must be nonnegative, got {value}.")
    return float(value)


def _normalize_voices(voices: Iterable[VoiceName]) -> tuple[VoiceName, ...]:
    normalized = tuple(voice for voice in voices)
    if not normalized:
        raise ValueError("At least one voice is required.")
    for voice in normalized:
        if voice not in VALID_VOICES:
            raise ValueError(f"Unsupported voice {voice!r}. Use one of {sorted(VALID_VOICES)}.")
    return normalized


def _normalize_pairs(
    pairs: Sequence[tuple[VoiceName, VoiceName]],
) -> tuple[tuple[VoiceName, VoiceName], ...]:
    normalized: list[tuple[VoiceName, VoiceName]] = []
    seen: set[tuple[VoiceName, VoiceName]] = set()
    for left, right in pairs:
        if left not in VALID_VOICES or right not in VALID_VOICES:
            raise ValueError(f"Unsupported voice pair {(left, right)!r}.")
        if left == right:
            raise ValueError(f"Voice pair {(left, right)!r} must use two distinct voices.")
        canonical = tuple(sorted((left, right)))  # type: ignore[arg-type]
        if canonical in seen:
            continue
        seen.add(canonical)
        normalized.append((left, right))
    if not normalized:
        raise ValueError("At least one voice pair is required.")
    return tuple(normalized)


def _interval_costs(**costs: int) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for interval_name, value in costs.items():
        if interval_name not in VALID_INTERVALS:
            raise ValueError(f"Unsupported interval bucket {interval_name!r}.")
        normalized[interval_name] = _nonnegative(value, interval_name)
    return normalized


def _normalize_inversion_costs(
    costs_by_inversion: Mapping[str, Mapping[str, int]] | None,
) -> dict[str, dict[str, int]]:
    normalized: dict[str, dict[str, int]] = {}
    if costs_by_inversion is None:
        return normalized
    for inversion, role_costs in costs_by_inversion.items():
        cleaned_inversion = inversion.strip()
        if not cleaned_inversion:
            raise ValueError("Inversion-specific cost names must not be empty.")
        normalized[cleaned_inversion] = {}
        for role, value in role_costs.items():
            if role not in VALID_CHORD_TONE_ROLES:
                raise ValueError(f"Unsupported chord-tone role {role!r}.")
            normalized[cleaned_inversion][role] = _nonnegative(value, f"{cleaned_inversion}.{role}")
    return normalized


def _normalize_threshold(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned not in VALID_THRESHOLDS:
        raise ValueError(f"Unsupported leap threshold {value!r}.")
    return cleaned


def _normalize_requirement(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned not in VALID_REQUIREMENTS:
        raise ValueError(f"Unsupported leap requirement {value!r}.")
    return cleaned


def _normalize_pitch_literal(value: str) -> str:
    cleaned = value.strip()
    match = PITCH_RE.fullmatch(cleaned)
    if not match:
        raise ValueError(
            f"Unsupported pitch literal {value!r}. Use forms like 'C4', 'F#4', or 'Bb3'."
        )
    letter = match.group("letter").upper()
    accidental = (match.group("accidental") or "").replace("-", "b").replace("nat", "n")
    octave = match.group("octave")
    return f"{letter}{accidental}{octave}"


def _plain_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _plain_data(inner) for key, inner in value.items()}
    if isinstance(value, tuple):
        return [_plain_data(inner) for inner in value]
    if isinstance(value, list):
        return [_plain_data(inner) for inner in value]
    return value
