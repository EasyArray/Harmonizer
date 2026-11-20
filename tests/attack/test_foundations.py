from fractions import Fraction as F

import numpy as np
import pytest

from harmonizer.attack.dsl import parse
from harmonizer.attack.foundations import RULEBOOK, event_table, metrics
from harmonizer.attack.inference import candidates
from harmonizer.attack.score import Key, Note, Pitch, Score, Voice


def note(voice, pitch, start, end):
  return Note(voice + str(start), Voice[voice], Pitch.parse(pitch), F(start), F(end))


@pytest.mark.parametrize("tenor_start", [0, 1])
def test_foundation_product_matches_general_enumerator(tenor_start):
  score = Score((note("A", "D4", 0, 1), note("A", "F4", 1, 2),
                 note("T", "B3", tenor_start, 2), note("B", "C3", 0, 2),
                 note("S", "Bb4", 1, 2), note("A", "A4", 2, 4)),
                Key(Pitch.parse("C4"), "minor"))
  domains = {Voice.A: tuple(map(Pitch.parse, ("F4", "E#4", "Ab4"))),
             Voice.T: tuple(map(Pitch.parse, ("B3", "Bb3")))}
  rules = parse(RULEBOOK.read_text())
  table, sounds = event_table(score, F(1), rules, domains)
  reference = candidates(score, rules, domains, F(1))
  assert (table.choices, table.gold, table.stop) == (reference.choices, reference.gold, reference.stop)
  np.testing.assert_array_equal(table.features, reference.features)
  names = [r.title for r in rules]
  # F above bass C is a dissonant fourth; Bb above alto F is an upper-part fourth.
  # B natural is outside natural minor and clashes with both outer voices.
  gold = table.features[table.gold]
  assert gold[names.index("Outer consonance")] == 1 + 2 * tenor_start
  assert gold[names.index("Global diatonicity")] == tenor_start
  result = metrics(table, sounds, np.zeros(len(rules)))
  assert result["sound_nll"] == pytest.approx(result["written_nll"] - np.log(2))
  assert result["tie"] == 1 and result["strict_win"] == 0
