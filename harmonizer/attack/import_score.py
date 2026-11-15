"""Strict MusicXML/music21 boundary: four monophonic parts, explicit key."""
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from music21 import chord, converter, note
from .score import Note, Pitch, Score, Voice


def rational(value):
  if isinstance(value, float):
    exact = Fraction(str(value)).limit_denominator(1_000_000)
    if abs(float(exact) - value) > 1e-10:
      raise ValueError(f"Cannot recover rational musical time: {value}")
    return exact
  return Fraction(value)


def from_music21(source, key, source_id="music21", part_order=tuple(Voice)):
  if len(source.parts) != 4 or len(set(part_order)) != 4 or set(part_order) != set(Voice):
    raise ValueError("Exactly four parts with an explicit SATB mapping are required")
  result = []
  for part, voice in zip(source.parts, part_order):
    pending = None
    for index, item in enumerate(part.flatten().notesAndRests):
      if isinstance(item, chord.Chord):
        raise ValueError("Chords inside a part are unsupported; supply monophonic SATB")
      if item.duration.isGrace:
        raise ValueError("Grace notes need an explicit timing policy")
      if isinstance(item, note.Rest):
        if pending:
          raise ValueError("A tie cannot cross a rest")
        continue
      if not isinstance(item, note.Note):
        raise ValueError("Unsupported pitched score object")
      p = item.pitch
      alteration = p.accidental.alter if p.accidental else 0
      if int(alteration) != alteration or p.octave is None or p.microtone.cents:
        raise ValueError("Microtonal or octave-less pitches are unsupported")
      pitch = Pitch(p.step, int(alteration), p.octave)
      onset = rational(item.offset)
      offset = onset + rational(item.quarterLength)
      identity = f"{source_id}:{voice.name}:{index}"
      # Preserve imported IDs only if they are textual; music21's generated
      # numeric object IDs are process-specific and cannot be used as stable IDs.
      source_ids = (identity,) + ((item.id,) if isinstance(item.id, str) else ())
      current = Note(identity, voice, pitch, onset, offset, source_ids)
      tie = item.tie.type if item.tie else None
      if tie in ("continue", "stop"):
        if pending is None or pending.pitch != pitch or pending.offset != onset:
          raise ValueError("Broken tie chain")
        pending = Note(pending.id, voice, pitch, pending.onset, offset,
                       pending.source_ids + source_ids)
        if tie == "stop":
          result.append(pending)
          pending = None
      elif pending:
        raise ValueError("Unterminated tie chain")
      elif tie == "start":
        pending = current
      elif tie is None:
        result.append(current)
      else:
        raise ValueError(f"Unsupported tie type {tie}")
    if pending:
      raise ValueError("Unterminated tie chain at end of part")
  return Score(tuple(result), key, source=source_id)


def read_musicxml(path, key, part_order=tuple(Voice)):
  path = Path(path)
  source_id = sha256(path.read_bytes()).hexdigest()[:16]
  # The source file remains authoritative for key signatures and figure XML.
  # Figure-content import/interpretation is deliberately not yet implemented.
  return from_music21(converter.parse(path), key, source_id, part_order)
