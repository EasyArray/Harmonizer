from fractions import Fraction as F
from pathlib import Path
import pytest
from harmonizer.attack.dsl import evaluate, parse
from harmonizer.attack.score import Key, Note, Pitch, Score, Voice


def note(identity, voice, pitch, onset, offset):
  return Note(identity, Voice[voice], Pitch.parse(pitch), F(onset), F(offset))


def total(title, notes):
  rules = tuple(r for r in parse(Path('rules/proposals/round-002.harmony').read_text()) if r.title == title)
  assert len(rules) == 1
  score = Score(tuple(notes), Key(Pitch.parse('C4'), 'major'))
  return sum(evaluate(rules, score, start=F(1)).totals.values())


@pytest.mark.parametrize('pitch,expected', [('D#4',0),('Eb4',1),('C#4',0)])
def test_astra_whole_tone_spelling(pitch, expected):
  assert total('Whole-tone melodic spelling',
    [note('a0','A','C#4',0,1),note('a1','A',pitch,1,2)]) == expected


@pytest.mark.parametrize('tenor,expected', [('D4',1),('B3',0)])
def test_astra_overlap_without_current_crossing(tenor, expected):
  assert total('Overlap without crossing',
    [note('a0','A','C4',0,1),note('t0','T','G3',0,1),
     note('a1','A','G4',1,2),note('t1','T',tenor,1,2)]) == expected


@pytest.mark.parametrize('previous,expected', [('C3',1),('E3',0)])
def test_astra_leap_into_held_semitone(previous, expected):
  assert total('Leaping into a held-note semitone',
    [note('a','A','G3',0,2),note('t0','T',previous,0,1),note('t1','T','F#3',1,2)]) == expected
