"""Code-first musical primitives for writing custom Python rules.

The declarative DSL is best for editable rulebooks. This module is the escape
hatch for old-school Python rules: it exposes pitch values, figured-bass
figures, harmony events, vertical events, and a simple ``RuleSet`` evaluator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import inspect
import itertools
import re
from typing import Any, Iterable, Literal, Mapping, Sequence

VoiceName = Literal["soprano", "alto", "tenor", "bass"]

S: VoiceName = "soprano"
A: VoiceName = "alto"
T: VoiceName = "tenor"
B: VoiceName = "bass"

VOICE_ORDER: tuple[VoiceName, ...] = (B, T, A, S)
VOICE_INDEX = {voice: index for index, voice in enumerate(VOICE_ORDER)}

_PITCH_TOKEN_RE = re.compile(
    r"^(?P<letter>[A-Ga-g])(?P<accidental>bb|ff|##|ss|x|b|f|#|s|n|nat)?(?P<octave>-?\d+)$"
)

_STEP_TO_PC = {
    "C": 0,
    "D": 2,
    "E": 4,
    "F": 5,
    "G": 7,
    "A": 9,
    "B": 11,
}

_STEP_TO_INDEX = {
    "C": 0,
    "D": 1,
    "E": 2,
    "F": 3,
    "G": 4,
    "A": 5,
    "B": 6,
}

_INDEX_TO_STEP = {value: key for key, value in _STEP_TO_INDEX.items()}

_ACCIDENTAL_TO_ALTER = {
    "": 0,
    "#": 1,
    "s": 1,
    "##": 2,
    "ss": 2,
    "x": 2,
    "b": -1,
    "f": -1,
    "bb": -2,
    "ff": -2,
    "n": 0,
    "nat": 0,
}

_ALTER_TO_ACCIDENTAL = {
    -2: "bb",
    -1: "b",
    0: "",
    1: "#",
    2: "##",
}

_FIGURE_ACCIDENTAL_MAP = {
    "sharp": "#",
    "flat": "b",
    "natural": "n",
    "double-sharp": "##",
    "sharp-sharp": "##",
    "double-flat": "bb",
    "flat-flat": "bb",
    "cross": "#",
    "backslash": "#",
    "slash": "b",
}

_SHARP_ORDER = ("F", "C", "G", "D", "A", "E", "B")
_FLAT_ORDER = ("B", "E", "A", "D", "G", "C", "F")

_ROOT_POSITION_TRIAD = (3, 5)
_FIRST_INVERSION_TRIAD = (3, 6)
_SECOND_INVERSION_TRIAD = (4, 6)
_ROOT_POSITION_SEVENTH = (3, 5, 7)
_FIRST_INVERSION_SEVENTH = (3, 5, 6)
_SECOND_INVERSION_SEVENTH = (3, 4, 6)
_THIRD_INVERSION_SEVENTH = (2, 4, 6)


@dataclass(frozen=True, order=True)
class PitchValue:
    """A MIDI pitch with a stable spelling such as ``Bb3`` or ``F#4``."""

    midi: int
    spelling: str = field(compare=False)

    @classmethod
    def parse(cls, value: "PitchValue | str | int") -> "PitchValue":
        """Parse a pitch literal, MIDI integer, or existing ``PitchValue``."""

        if isinstance(value, PitchValue):
            return value
        if isinstance(value, int):
            return cls(value, cls._spelling_from_midi(value))
        if not isinstance(value, str):
            raise TypeError(f"Unsupported pitch literal type: {type(value).__name__}")

        text = value.strip()
        match = _PITCH_TOKEN_RE.fullmatch(text)
        if not match:
            raise ValueError(
                f"Could not parse pitch literal {value!r}. Use forms like 'C4', 'Bb3', 'F#4', or 'Fs4'."
            )

        letter = match.group("letter").upper()
        accidental_token = (match.group("accidental") or "").lower()
        octave = int(match.group("octave"))
        alter = _ACCIDENTAL_TO_ALTER[accidental_token]
        midi = (octave + 1) * 12 + _STEP_TO_PC[letter] + alter
        spelling = f"{letter}{_normalize_accidental_text(accidental_token)}{octave}"
        return cls(midi=midi, spelling=spelling)

    @classmethod
    def from_components(cls, letter: str, accidental: str, octave: int) -> "PitchValue":
        spelling = f"{letter.upper()}{_normalize_accidental_text(accidental)}{octave}"
        midi = (octave + 1) * 12 + _STEP_TO_PC[letter.upper()] + _ACCIDENTAL_TO_ALTER[accidental]
        return cls(midi=midi, spelling=spelling)

    @property
    def octave(self) -> int:
        return (self.midi // 12) - 1

    @property
    def pitch_class(self) -> int:
        return self.midi % 12

    @property
    def letter(self) -> str:
        return self.spelling[0]

    @property
    def accidental(self) -> str:
        match = _PITCH_TOKEN_RE.fullmatch(self.spelling)
        if match is None:
            raise ValueError(f"Could not recover accidental from {self.spelling!r}.")
        return _normalize_accidental_text((match.group("accidental") or "").lower())

    @property
    def alter(self) -> int:
        return _ACCIDENTAL_TO_ALTER[self.accidental]

    def __sub__(self, other: "PitchValue | str | int") -> int:
        return self.midi - PitchValue.parse(other).midi

    def __str__(self) -> str:
        return self.spelling

    def __repr__(self) -> str:
        return f"PitchValue({self.spelling})"

    @staticmethod
    def _spelling_from_midi(midi: int) -> str:
        octave = (midi // 12) - 1
        pc = midi % 12
        names = {
            0: "C",
            1: "C#",
            2: "D",
            3: "Eb",
            4: "E",
            5: "F",
            6: "F#",
            7: "G",
            8: "Ab",
            9: "A",
            10: "Bb",
            11: "B",
        }
        return f"{names[pc]}{octave}"


class _NoteNamespace(type):
    def __getattr__(cls, name: str) -> PitchValue:
        return PitchValue.parse(name)


class Note(metaclass=_NoteNamespace):
    """Namespace for pitch literals such as Note.C4, Note.Bb3, or Note.Fs4."""


@dataclass(frozen=True)
class FiguredBassFigure:
    """One figured-bass symbol parsed from MusicXML."""

    number: int | None = None
    accidental: str | None = None
    prefix: str | None = None
    suffix: str | None = None

    @classmethod
    def from_musicxml(
        cls,
        *,
        number: str | None,
        prefix: str | None,
        suffix: str | None,
    ) -> "FiguredBassFigure":
        accidental = _figure_accidental_from_musicxml(prefix=prefix, suffix=suffix)
        normalized_number = int(number) if number not in (None, "") else None
        return cls(
            number=normalized_number,
            accidental=accidental,
            prefix=prefix,
            suffix=suffix,
        )

    @property
    def effective_number(self) -> int | None:
        if self.number is not None:
            return self.number
        if self.accidental is not None:
            return 3
        return None

    @property
    def is_blank(self) -> bool:
        return self.number is None and self.accidental is None

    @property
    def token(self) -> str:
        if self.is_blank:
            return "blank"
        number = "" if self.number is None else str(self.number)
        accidental = self.accidental or ""
        if self.prefix:
            return f"{accidental}{number}" or "blank"
        if self.suffix and number:
            return f"{number}{accidental}"
        return f"{accidental}{number}" or "blank"


@dataclass(frozen=True)
class HarmonyTone:
    """One required tone implied by a bass note and figured-bass interval."""

    interval: int
    pitch: PitchValue
    explicit: bool
    accidental: str | None = None
    role: str | None = None


@dataclass(frozen=True)
class HarmonyEvent:
    """The local harmony implied by a bass note, figures, and key signature."""

    bass: PitchValue
    figures: tuple[FiguredBassFigure, ...]
    key_signature_fifths: int
    explicit_intervals: tuple[int, ...]
    required_intervals: tuple[int, ...]
    tones: tuple[HarmonyTone, ...]
    figure_text: str
    role_by_interval: Mapping[int, str] = field(default_factory=dict)
    inversion: str | None = None
    root_interval: int | None = None

    def required_pitches(self) -> tuple[PitchValue, ...]:
        pitches: list[PitchValue] = []
        if 1 in self.role_by_interval:
            pitches.append(self.bass)
        pitches.extend(tone.pitch for tone in self.tones)
        return tuple(pitches)

    def required_pitch_classes(self) -> tuple[int, ...]:
        return tuple(sorted({pitch.pitch_class for pitch in self.required_pitches()}))

    def role_pitches(self) -> dict[str, PitchValue]:
        pitches: dict[str, PitchValue] = {}
        pitches_by_interval = {1: self.bass}
        pitches_by_interval.update({tone.interval: tone.pitch for tone in self.tones})
        for interval, role in self.role_by_interval.items():
            pitch = pitches_by_interval.get(interval)
            if pitch is not None and role not in pitches:
                pitches[role] = pitch
        return pitches

    def missing_required_pitch_classes(
        self,
        sounding_pitches: Iterable[PitchValue | None],
    ) -> tuple[int, ...]:
        present = {pitch.pitch_class for pitch in sounding_pitches if pitch is not None}
        return tuple(pc for pc in self.required_pitch_classes() if pc not in present)

    def role_for_pitch(self, pitch: PitchValue | None) -> str | None:
        if pitch is None:
            return None
        for role, role_pitch in self.role_pitches().items():
            if pitch.pitch_class == role_pitch.pitch_class:
                return role
        return None


@dataclass(frozen=True)
class IntervalMotion:
    """Motion from one voice interval to the next."""

    before: "VoiceInterval"
    after: "VoiceInterval"

    @property
    def motion_type(self) -> str:
        left_motion = self.after.pitch_a.midi - self.before.pitch_a.midi
        right_motion = self.after.pitch_b.midi - self.before.pitch_b.midi

        if left_motion == 0 and right_motion == 0:
            return "static"
        if left_motion == 0 or right_motion == 0:
            return "oblique"
        if (left_motion > 0 and right_motion > 0) or (left_motion < 0 and right_motion < 0):
            return "similar"
        return "contrary"

    @property
    def is_parallel(self) -> bool:
        return (
            self.motion_type == "similar"
            and self.before.is_perfect_consonance
            and self.after.is_perfect_consonance
            and self.before.type == self.after.type
        )

    @property
    def is_similar_into_perfect(self) -> bool:
        return self.motion_type == "similar" and self.after.is_perfect_consonance


@dataclass(frozen=True)
class VoiceInterval:
    """A melodic or harmonic interval between two named voices."""

    voice_a: VoiceName
    voice_b: VoiceName
    pitch_a: PitchValue
    pitch_b: PitchValue

    def voices(self) -> tuple[VoiceName, VoiceName]:
        return (self.voice_a, self.voice_b)

    @property
    def semitones(self) -> int:
        return abs(self.pitch_b.midi - self.pitch_a.midi)

    @property
    def number(self) -> int:
        letter_a = self.pitch_a.spelling[0]
        letter_b = self.pitch_b.spelling[0]
        diatonic_steps = abs(
            (self.pitch_b.octave - self.pitch_a.octave) * 7
            + (_STEP_TO_INDEX[letter_b] - _STEP_TO_INDEX[letter_a])
        )
        return diatonic_steps + 1

    @property
    def simple_number(self) -> int:
        if self.number == 1:
            return 1
        reduced = ((self.number - 1) % 7) + 1
        if reduced == 1 and self.semitones >= 12:
            return 8
        return reduced

    @property
    def type(self) -> int:
        return self.simple_number

    @property
    def is_fifth(self) -> bool:
        return self.type == 5

    @property
    def is_unison(self) -> bool:
        return self.number == 1 and self.semitones == 0

    @property
    def is_octave(self) -> bool:
        return self.type == 8

    @property
    def is_octave_or_unison(self) -> bool:
        return self.is_unison or self.is_octave

    @property
    def is_perfect_consonance(self) -> bool:
        return self.is_fifth or self.is_octave_or_unison

    def motion_to(self, other: "VoiceInterval") -> IntervalMotion:
        if self.voices() != other.voices():
            raise ValueError("Cannot compare interval motion across different voice pairs.")
        return IntervalMotion(before=self, after=other)


@dataclass(frozen=True)
class VerticalEvent:
    """A SATB snapshot at one score offset.

    Events carry the current sounding pitches plus enough context for scoring:
    figured-bass symbols, changed voices, previous pitches, key signature, and
    notebook-friendly location metadata.
    """

    soprano: PitchValue | None
    alto: PitchValue | None
    tenor: PitchValue | None
    bass: PitchValue | None
    index: int | None = None
    offset: float | None = None
    measure: str | None = None
    beat: float | None = None
    beat_strength: float = 0.0
    event_strength: float = 0.0
    figures: tuple[FiguredBassFigure, ...] = field(default_factory=tuple)
    figure_changed: bool = False
    key_signature_fifths: int = 0
    changed_voices: tuple[VoiceName, ...] = field(default_factory=tuple)
    previous_pitches: Mapping[VoiceName, PitchValue | None] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "soprano", _optional_pitch(self.soprano))
        object.__setattr__(self, "alto", _optional_pitch(self.alto))
        object.__setattr__(self, "tenor", _optional_pitch(self.tenor))
        object.__setattr__(self, "bass", _optional_pitch(self.bass))
        object.__setattr__(self, "figures", _normalize_figures(self.figures))
        object.__setattr__(self, "changed_voices", tuple(self.changed_voices))
        object.__setattr__(self, "previous_pitches", _normalize_previous_pitches(self.previous_pitches))
        object.__setattr__(self, "metadata", dict(self.metadata))

    @classmethod
    def from_literals(
        cls,
        *,
        soprano: PitchValue | str | int | None = None,
        alto: PitchValue | str | int | None = None,
        tenor: PitchValue | str | int | None = None,
        bass: PitchValue | str | int | None = None,
        index: int | None = None,
        offset: float | None = None,
        measure: str | None = None,
        beat: float | None = None,
        beat_strength: float = 0.0,
        event_strength: float = 0.0,
        figures: Sequence[FiguredBassFigure] | None = None,
        figure_changed: bool = False,
        key_signature_fifths: int = 0,
        changed_voices: Sequence[VoiceName] | None = None,
        previous_pitches: Mapping[VoiceName, PitchValue | str | int | None] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "VerticalEvent":
        return cls(
            soprano=_optional_pitch(soprano),
            alto=_optional_pitch(alto),
            tenor=_optional_pitch(tenor),
            bass=_optional_pitch(bass),
            index=index,
            offset=offset,
            measure=measure,
            beat=beat,
            beat_strength=beat_strength,
            event_strength=event_strength,
            figures=tuple(figures or ()),
            figure_changed=figure_changed,
            key_signature_fifths=key_signature_fifths,
            changed_voices=tuple(changed_voices or ()),
            previous_pitches=dict(previous_pitches or {}),
            metadata=dict(metadata or {}),
        )

    def pitch(self, voice: VoiceName) -> PitchValue | None:
        return getattr(self, voice)

    def previous_pitch(self, voice: VoiceName) -> PitchValue | None:
        return self.previous_pitches.get(voice)

    def voice_changed(self, voice: VoiceName) -> bool:
        return voice in self.changed_voices

    def present_voices(self) -> tuple[VoiceName, ...]:
        return tuple(voice for voice in VOICE_ORDER if self.pitch(voice) is not None)

    def sounding_pitches(self) -> tuple[PitchValue | None, ...]:
        return (self.soprano, self.alto, self.tenor, self.bass)

    def is_anchor(self, threshold: float = 0.45) -> bool:
        return self.event_strength >= threshold

    def harmony(self) -> HarmonyEvent | None:
        """Derive the local figured-bass harmony, if a bass pitch is present."""

        if self.bass is None:
            return None
        return _derive_harmony_event(
            bass=self.bass,
            figures=self.figures,
            key_signature_fifths=self.key_signature_fifths,
        )

    def intervals(
        self,
        pairs: Sequence[tuple[VoiceName, VoiceName]] | None = None,
    ) -> list[VoiceInterval]:
        """Return currently sounding intervals for the requested voice pairs."""

        intervals: list[VoiceInterval] = []
        if pairs is None:
            candidate_pairs = list(itertools.combinations(self.present_voices(), 2))
        else:
            candidate_pairs = list(pairs)

        for voice_a, voice_b in candidate_pairs:
            pitch_a = self.pitch(voice_a)
            pitch_b = self.pitch(voice_b)
            if pitch_a is None or pitch_b is None:
                continue
            intervals.append(
                VoiceInterval(
                    voice_a=voice_a,
                    voice_b=voice_b,
                    pitch_a=pitch_a,
                    pitch_b=pitch_b,
                )
            )
        return intervals

    def previous_intervals(
        self,
        pairs: Sequence[tuple[VoiceName, VoiceName]] | None = None,
    ) -> list[VoiceInterval]:
        intervals: list[VoiceInterval] = []
        if pairs is None:
            candidate_pairs = list(itertools.combinations(VOICE_ORDER, 2))
        else:
            candidate_pairs = list(pairs)

        for voice_a, voice_b in candidate_pairs:
            pitch_a = self.previous_pitch(voice_a)
            pitch_b = self.previous_pitch(voice_b)
            if pitch_a is None or pitch_b is None:
                continue
            intervals.append(
                VoiceInterval(
                    voice_a=voice_a,
                    voice_b=voice_b,
                    pitch_a=pitch_a,
                    pitch_b=pitch_b,
                )
            )
        return intervals


@dataclass(frozen=True)
class RuleHit:
    rule: str
    cost: float
    event_indices: tuple[int, ...]


@dataclass(frozen=True)
class ScoreBreakdown:
    total_cost: float
    hits: tuple[RuleHit, ...]

    def by_rule(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for hit in self.hits:
            totals[hit.rule] = totals.get(hit.rule, 0.0) + hit.cost
        return totals


class RuleSet:
    """Base class for code-first rules written directly against musical events.

    Public instance methods are interpreted as scoring rules:
    - `rule(ev)` is applied to every vertical event.
    - `rule(ev1, ev2)` is applied to every consecutive pair of events.
    - `rule(ev1, ev2, ev3)` is applied to every consecutive triple, and so on.
    """

    def evaluate(self, events: Sequence[VerticalEvent]) -> ScoreBreakdown:
        normalized_events = _normalize_events(events)
        hits: list[RuleHit] = []

        for rule_name, method in self._rule_methods():
            arity = _event_arity(method)
            if arity <= 0:
                continue
            if len(normalized_events) < arity:
                continue

            for start in range(len(normalized_events) - arity + 1):
                window = normalized_events[start : start + arity]
                raw_cost = method(*window)
                cost = _coerce_cost(raw_cost)
                if cost:
                    hits.append(
                        RuleHit(
                            rule=rule_name,
                            cost=cost,
                            event_indices=tuple(
                                event.index if event.index is not None else start + offset
                                for offset, event in enumerate(window)
                            ),
                        )
                    )

        total_cost = sum(hit.cost for hit in hits)
        return ScoreBreakdown(total_cost=total_cost, hits=tuple(hits))

    def _rule_methods(self) -> list[tuple[str, Any]]:
        methods: list[tuple[str, Any]] = []
        for name in dir(self):
            if name.startswith("_"):
                continue
            if name in RuleSet.__dict__:
                continue
            attribute = getattr(self, name)
            if not callable(attribute):
                continue
            methods.append((name, attribute))
        return methods


def _optional_pitch(value: PitchValue | str | int | None) -> PitchValue | None:
    if value is None:
        return None
    return PitchValue.parse(value)


def _normalize_previous_pitches(
    previous_pitches: Mapping[VoiceName, PitchValue | str | int | None],
) -> dict[VoiceName, PitchValue | None]:
    normalized: dict[VoiceName, PitchValue | None] = {}
    for voice, pitch in previous_pitches.items():
        normalized[voice] = _optional_pitch(pitch)
    return normalized


def _normalize_figures(figures: Sequence[FiguredBassFigure]) -> tuple[FiguredBassFigure, ...]:
    normalized: list[FiguredBassFigure] = []
    for figure in figures:
        if not isinstance(figure, FiguredBassFigure):
            raise TypeError(f"Expected FiguredBassFigure, got {type(figure).__name__}.")
        normalized.append(figure)
    return tuple(normalized)


def _normalize_events(events: Sequence[VerticalEvent]) -> tuple[VerticalEvent, ...]:
    normalized: list[VerticalEvent] = []
    for index, event in enumerate(events):
        if not isinstance(event, VerticalEvent):
            raise TypeError(f"Expected VerticalEvent, got {type(event).__name__}.")
        if event.index is None:
            normalized.append(
                VerticalEvent(
                    soprano=event.soprano,
                    alto=event.alto,
                    tenor=event.tenor,
                    bass=event.bass,
                    index=index,
                    offset=event.offset,
                    measure=event.measure,
                    beat=event.beat,
                    beat_strength=event.beat_strength,
                    event_strength=event.event_strength,
                    figures=event.figures,
                    figure_changed=event.figure_changed,
                    key_signature_fifths=event.key_signature_fifths,
                    changed_voices=event.changed_voices,
                    previous_pitches=event.previous_pitches,
                    metadata=event.metadata,
                )
            )
        else:
            normalized.append(event)
    return tuple(normalized)


def _event_arity(method: Any) -> int:
    signature = inspect.signature(method)
    parameters = list(signature.parameters.values())
    positional = [
        parameter
        for parameter in parameters
        if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return len(positional)


def _coerce_cost(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    raise TypeError(f"Rule methods must return a number or None, got {type(value).__name__}.")


def _normalize_accidental_text(token: str) -> str:
    return {
        "": "",
        "#": "#",
        "s": "#",
        "##": "##",
        "ss": "##",
        "x": "##",
        "b": "b",
        "f": "b",
        "bb": "bb",
        "ff": "bb",
        "n": "n",
        "nat": "n",
    }[token]


def _figure_accidental_from_musicxml(prefix: str | None, suffix: str | None) -> str | None:
    raw = prefix or suffix
    if raw is None:
        return None
    normalized = _FIGURE_ACCIDENTAL_MAP.get(raw)
    if normalized is None:
        raise ValueError(f"Unsupported figured-bass accidental token: {raw!r}.")
    return normalized


def _format_figures(figures: Sequence[FiguredBassFigure]) -> str:
    if not figures:
        return "5/3"
    tokens = [figure.token for figure in figures if not figure.is_blank]
    if not tokens:
        return "5/3"
    return "/".join(tokens)


def _derive_harmony_event(
    *,
    bass: PitchValue,
    figures: Sequence[FiguredBassFigure],
    key_signature_fifths: int,
) -> HarmonyEvent:
    figure_map: dict[int, FiguredBassFigure] = {}
    explicit_intervals: list[int] = []

    for figure in figures:
        number = figure.effective_number
        if number is None:
            continue
        figure_map[number] = figure
        explicit_intervals.append(number)

    required_intervals = _normalize_required_intervals(explicit_intervals)
    role_by_interval, inversion, root_interval = _role_map_for_intervals(required_intervals)

    tones: list[HarmonyTone] = []
    for interval in required_intervals:
        figure = figure_map.get(interval)
        accidental = figure.accidental if figure else None
        pitch = _pitch_for_interval(
            bass=bass,
            interval=interval,
            accidental=accidental,
            key_signature_fifths=key_signature_fifths,
        )
        tones.append(
            HarmonyTone(
                interval=interval,
                pitch=pitch,
                explicit=interval in explicit_intervals,
                accidental=accidental,
                role=role_by_interval.get(interval),
            )
        )

    return HarmonyEvent(
        bass=bass,
        figures=tuple(figures),
        key_signature_fifths=key_signature_fifths,
        explicit_intervals=tuple(explicit_intervals),
        required_intervals=required_intervals,
        tones=tuple(tones),
        figure_text=_format_figures(figures),
        role_by_interval=role_by_interval,
        inversion=inversion,
        root_interval=root_interval,
    )


def _normalize_required_intervals(explicit_intervals: Sequence[int]) -> tuple[int, ...]:
    numbers = set(explicit_intervals)
    if not numbers:
        return _ROOT_POSITION_TRIAD

    if numbers == {6}:
        return _FIRST_INVERSION_TRIAD
    if numbers == {5}:
        return _ROOT_POSITION_TRIAD
    if numbers == {7}:
        return _ROOT_POSITION_SEVENTH
    if numbers == {4}:
        return _SECOND_INVERSION_TRIAD
    if numbers == {2}:
        return _THIRD_INVERSION_SEVENTH
    if numbers == {8}:
        return (3, 5, 8)
    if numbers == {9}:
        return (3, 5, 9)
    if numbers == {6, 4}:
        return _SECOND_INVERSION_TRIAD
    if numbers == {6, 5}:
        return _FIRST_INVERSION_SEVENTH
    if numbers == {4, 3}:
        return _SECOND_INVERSION_SEVENTH
    if numbers == {4, 2}:
        return _THIRD_INVERSION_SEVENTH

    return tuple(sorted(numbers))


def _role_map_for_intervals(
    intervals: Sequence[int],
) -> tuple[dict[int, str], str | None, int | None]:
    core = tuple(sorted(interval for interval in intervals if interval not in (8, 9)))
    role_map: dict[int, str]
    inversion: str | None = None
    root_interval: int | None = None

    if core == _ROOT_POSITION_TRIAD:
        role_map = {1: "root", 3: "third", 5: "fifth", 8: "root"}
        inversion = "root-position-triad"
        root_interval = 1
    elif core == _FIRST_INVERSION_TRIAD:
        role_map = {1: "third", 3: "fifth", 6: "root"}
        inversion = "first-inversion-triad"
        root_interval = 6
    elif core == _SECOND_INVERSION_TRIAD:
        role_map = {1: "fifth", 4: "root", 6: "third"}
        inversion = "second-inversion-triad"
        root_interval = 4
    elif core == _ROOT_POSITION_SEVENTH:
        role_map = {1: "root", 3: "third", 5: "fifth", 7: "seventh", 8: "root"}
        inversion = "root-position-seventh"
        root_interval = 1
    elif core == _FIRST_INVERSION_SEVENTH:
        role_map = {1: "third", 3: "fifth", 5: "seventh", 6: "root"}
        inversion = "first-inversion-seventh"
        root_interval = 6
    elif core == _SECOND_INVERSION_SEVENTH:
        role_map = {1: "fifth", 3: "seventh", 4: "root", 6: "third"}
        inversion = "second-inversion-seventh"
        root_interval = 4
    elif core == _THIRD_INVERSION_SEVENTH:
        role_map = {1: "seventh", 2: "root", 4: "third", 6: "fifth"}
        inversion = "third-inversion-seventh"
        root_interval = 2
    else:
        role_map = {}

    if 9 in intervals:
        role_map[9] = "ninth"
    if 8 in intervals:
        role_map.setdefault(8, "root")

    return role_map, inversion, root_interval


def _pitch_for_interval(
    *,
    bass: PitchValue,
    interval: int,
    accidental: str | None,
    key_signature_fifths: int,
) -> PitchValue:
    if interval == 1:
        return bass

    step_distance = interval - 1
    bass_index = _STEP_TO_INDEX[bass.letter]
    target_index = bass_index + step_distance
    letter = _INDEX_TO_STEP[target_index % 7]
    octave = bass.octave + (target_index // 7)
    if accidental is None:
        alter = _key_signature_alter(letter, key_signature_fifths)
    else:
        alter = _ACCIDENTAL_TO_ALTER[accidental]
    accidental_text = _ALTER_TO_ACCIDENTAL.get(alter)
    if accidental_text is None:
        raise ValueError(f"Unsupported chromatic alteration {alter} for figured-bass realization.")
    return PitchValue.from_components(letter=letter, accidental=accidental_text, octave=octave)


def _key_signature_alter(letter: str, fifths: int) -> int:
    if fifths > 0 and letter in _SHARP_ORDER[:fifths]:
        return 1
    if fifths < 0 and letter in _FLAT_ORDER[: abs(fifths)]:
        return -1
    return 0
