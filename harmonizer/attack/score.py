"""Small immutable musical objects with exact time and spelled pitch."""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from enum import Enum
from fractions import Fraction
import re


class Voice(Enum):
  S = 0
  A = 1
  T = 2
  B = 3


LETTERS = "CDEFGAB"
NATURAL = (0, 2, 4, 5, 7, 9, 11)


@dataclass(frozen=True)
class Pitch:
  letter: str
  alteration: int
  octave: int

  @classmethod
  def parse(cls, text):
    match = re.fullmatch(r"([A-G])([#b]*)(-?\d+)", text)
    if not match:
      raise ValueError(f"Invalid spelled pitch: {text}")
    letter, accidental, octave = match.groups()
    if "#" in accidental and "b" in accidental:
      raise ValueError("Mixed accidentals are not supported")
    return cls(letter, accidental.count("#") - accidental.count("b"), int(octave))

  @property
  def semitones(self):
    return 12 * (self.octave + 1) + NATURAL[LETTERS.index(self.letter)] + self.alteration

  @property
  def steps(self):
    return self.octave * 7 + LETTERS.index(self.letter)

  def __str__(self):
    accidental = "#" * self.alteration if self.alteration >= 0 else "b" * -self.alteration
    return f"{self.letter}{accidental}{self.octave}"


@dataclass(frozen=True)
class Interval:
  steps: int
  semitones: int

  @classmethod
  def parse(cls, text):
    match = re.fullmatch(r"([PMmd])(\d+)", text)
    if not match:
      raise ValueError(f"Unsupported interval literal: {text}")
    quality, number = match.groups()
    steps = int(number) - 1
    if steps < 0:
      raise ValueError("Interval numbers start at 1")
    simple = steps % 7
    perfect = simple in (0, 3, 4)
    if (quality == "P" and not perfect) or (quality in "Mm" and perfect):
      raise ValueError(f"Invalid interval quality: {text}")
    alteration = {"P": 0, "M": 0, "m": -1, "d": -1 if perfect else -2}[quality]
    return cls(steps, NATURAL[simple] + 12 * (steps // 7) + alteration)

  def __neg__(self):
    return Interval(-self.steps, -self.semitones)


@dataclass(frozen=True)
class Degree:
  number: int
  alteration: int = 0

  def __post_init__(self):
    if not 1 <= self.number <= 7:
      raise ValueError("Degree must be 1–7")


@dataclass(frozen=True)
class Key:
  tonic: Pitch
  mode: str
  provenance: str = "supplied"

  def __post_init__(self):
    if self.mode not in ("major", "minor"):
      raise ValueError("Only supplied major/minor keys are supported initially")

  def degree(self, pitch):
    step = (pitch.steps - self.tonic.steps) % 7
    baseline = NATURAL if self.mode == "major" else (0, 2, 3, 5, 7, 8, 10)
    octaves = (pitch.steps - self.tonic.steps) // 7
    alteration = pitch.semitones - self.tonic.semitones - 12 * octaves - baseline[step]
    return Degree(step + 1, alteration)


@dataclass(frozen=True)
class Note:
  id: str
  voice: Voice
  pitch: Pitch
  onset: Fraction
  offset: Fraction
  source_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Figure:
  id: str
  onset: Fraction
  literal: str


@dataclass(frozen=True)
class Score:
  notes: tuple[Note, ...]
  key: Key
  figures: tuple[Figure, ...] = ()
  source: str = "in-memory"

  def __post_init__(self):
    ids = [n.id for n in self.notes] + [f.id for f in self.figures]
    if len(set(ids)) != len(ids):
      raise ValueError("Score item IDs must be unique")
    for note in self.notes:
      if not isinstance(note.onset, Fraction) or not isinstance(note.offset, Fraction):
        raise TypeError("Note times must be exact Fractions")
      if note.offset <= note.onset:
        raise ValueError("Notes must have positive durations")
    for figure in self.figures:
      if not isinstance(figure.onset, Fraction):
        raise TypeError("Figure times must be exact Fractions")
    for voice in Voice:
      notes = sorted((n for n in self.notes if n.voice == voice), key=lambda n: n.onset)
      if any(a.offset > b.onset for a, b in zip(notes, notes[1:])):
        raise ValueError(f"Overlapping notes in {voice.name}: monophonic parts required")

  @cached_property
  def _by_voice(self):
    return {v: tuple(sorted((n for n in self.notes if n.voice == v), key=lambda n: n.onset)) for v in Voice}

  @cached_property
  def _onsets(self):
    return {v: tuple(n.onset for n in notes) for v, notes in self._by_voice.items()}

  @cached_property
  def _ending(self):
    return {(n.voice, n.offset): n for n in self.notes}

  @cached_property
  def _attacks(self):
    by_time = defaultdict(list)
    for n in self.notes:
      by_time[n.onset].append(n)
    return {t: tuple(sorted(notes, key=lambda n: n.voice.value)) for t, notes in by_time.items()}

  def attacks_at(self, time):
    return self._attacks.get(time, ())

  @cached_property
  def _time_points(self):
    return tuple(sorted({t for n in self.notes for t in (n.onset, n.offset)} | {f.onset for f in self.figures}))

  @property
  def times(self):
    return list(self._time_points)

  def at(self, voice, time, before=False):
    search = bisect_left if before else bisect_right
    index = search(self._onsets[voice], time) - 1
    if index < 0:
      return None
    note = self._by_voice[voice][index]
    if (time <= note.offset) if before else (time < note.offset):
      return note
    return None

  def previous(self, note):
    # Exact end boundaries preserve the no-navigation-across-rests contract.
    return self._ending.get((note.voice, note.onset))


def pitch_of(value):
  return value.pitch if isinstance(value, Note) else value


def interval(a, b):
  a, b = pitch_of(a), pitch_of(b)
  return Interval(b.steps - a.steps, b.semitones - a.semitones)
