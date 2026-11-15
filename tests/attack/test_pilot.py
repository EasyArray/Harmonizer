from dataclasses import replace
from fractions import Fraction as F
import numpy as np
import pytest
from harmonizer.attack.dsl import parse
from harmonizer.attack.inference import candidates
from harmonizer.attack.pilot import first_metrics, pitch_counts, pitch_domain, pitch_table, select_start
from harmonizer.attack.score import Key, Note, Pitch, Score, Voice


def test_pitch_domain_retains_enharmonic_alternatives():
  pool = pitch_domain(60, 60)
  assert set(map(str, pool)) == {"C4", "B#3"}
  assert all(p.semitones == 60 for p in pool)


def test_pilot_selection_uses_rhythm_only_and_baseline_normalizes():
  score = Score(tuple(Note(str(i), Voice.A, Pitch.parse(p), F(i), F(i+1))
                      for i, p in enumerate(("C4", "D4", "C4"))), Key(Pitch.parse("C4"), "major"))
  assert select_start(score) == 1
  assert select_start(replace(score, notes=tuple(replace(n, pitch=Pitch.parse("C6")) for n in score.notes))) == 1
  rules = parse('At attack a:\n  Rule "motion":\n    penalty distance(a.previous,a)')
  domains = {Voice.A: (Pitch.parse("C4"), Pitch.parse("D4"))}
  one = candidates(score, rules, domains, F(1))
  two = candidates(score, rules, domains, F(1), horizon=2)
  counts = pitch_counts([(score, one)], domains)
  one_baseline = pitch_table(score, one, counts)
  two_baseline = pitch_table(score, two, counts)
  assert sum(np.exp(two_baseline.log_probabilities([1]))) == pytest.approx(1)
  assert first_metrics(one_baseline, [1])["gold_probability"] == pytest.approx(2/3)
  # Independent pitch priors marginalize identically at horizons one and two.
  assert first_metrics(two_baseline, [1])["gold_probability"] == pytest.approx(2/3)
