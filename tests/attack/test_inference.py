from dataclasses import replace
from fractions import Fraction as F
import numpy as np
import pytest
from harmonizer.attack.dsl import parse
from harmonizer.attack.inference import CoverageError, candidates, fit, objective
from harmonizer.attack.score import Figure, Key, Note, Pitch, Score, Voice


def fixture():
  notes = tuple(Note(f"{v}{i}", Voice[v], Pitch.parse(p), F(i), F(i+1))
                for i, pitches in enumerate((("G4", "C4"), ("A4", "D4"), ("G4", "C4")))
                for v, p in zip("AT", pitches))
  rules = parse('At attack n:\n  Rule "Motion":\n    penalty distance(n.previous, n)')
  score = Score(notes, Key(Pitch.parse("C4"), "major"))
  domains = {Voice.A: tuple(map(Pitch.parse, ("G4", "A4"))), Voice.T: tuple(map(Pitch.parse, ("C4", "D4")))}
  return score, rules, domains


def test_exact_joint_probabilities_and_first_marginal():
  score, rules, domains = fixture()
  one = candidates(score, rules, domains, F(1))
  two = candidates(score, rules, domains, F(1), horizon=2)
  assert len(one.choices) == 4 and len(two.choices) == 16
  assert np.exp(one.log_probabilities([0])).tolist() == [0.25]*4
  assert np.exp(two.log_probabilities([2])).sum() == pytest.approx(1)
  marginal = two.first_choice_probabilities([2])
  assert len(marginal) == 4 and sum(marginal.values()) == pytest.approx(1)
  for prefix, probability in marginal.items():
    expected = sum(np.exp(p) for choice, p in zip(two.choices, two.log_probabilities([2])) if choice[:2] == prefix)
    assert probability == pytest.approx(expected)


def test_no_future_gold_leakage():
  score, rules, domains = fixture()
  first = candidates(score, rules, domains, F(1))
  changed = replace(score, notes=tuple(replace(n, pitch=Pitch.parse("C8")) if n.onset == 2 else n for n in score.notes))
  second = candidates(changed, rules, domains, F(1))
  np.testing.assert_array_equal(first.features, second.features)
  assert first.choices == second.choices


def test_outer_only_and_figure_events_in_window_and_held_inner_note():
  score, _, domains = fixture()
  notes = tuple(n for n in score.notes if n.voice == Voice.A) + (
    Note("held", Voice.T, Pitch.parse("C4"), F(0), F(3)),
    Note("s", Voice.S, Pitch.parse("G5"), F(3,2), F(2)))
  score = replace(score, notes=notes, figures=(Figure("f", F(7,4), "6"),))
  rules = parse('At soprano attack s:\n  Rule "outer":\n    penalty distance(A at s, s)\nAt figure f:\n  Rule "fig":\n    penalty distance(A at f, T at f)')
  table = candidates(score, rules, domains, F(1))
  assert table.note_ids == ("A1",)
  assert table.features.tolist() == [[12,7],[10,9]]


def test_generator_failures_are_not_silent():
  score, rules, domains = fixture()
  with pytest.raises(ValueError, match="limit"):
    candidates(score, rules, domains, F(1), horizon=2, max_candidates=4)
  domains[Voice.A] = (Pitch.parse("C3"),)
  with pytest.raises(CoverageError):
    candidates(score, rules, domains, F(1))


def test_gradient_and_training_improvement():
  score, rules, domains = fixture()
  table = candidates(score, rules, domains, F(1))
  # This synthetic training example prefers motion; permit signed weights.
  w = np.array([0.2])
  loss, gradient = objective(w, (table,), 0.1)
  epsilon = 1e-6
  numerical = (objective(w + epsilon, (table,), 0.1)[0] - objective(w - epsilon, (table,), 0.1)[0]) / (2*epsilon)
  assert gradient[0] == pytest.approx(numerical, abs=1e-7)
  fitted = fit((table,), nonnegative=False)
  assert fitted[0] < 0
  assert table.metrics(fitted)["nll"] < table.metrics([0])["nll"]
  assert np.isfinite(table.log_probabilities([1e4])).all()
  assert fit((table,))[0] >= 0


def test_constant_rules_are_reported():
  score, _, domains = fixture()
  rules = parse('At attack n:\n  Rule "constant":\n    penalty 1')
  table = candidates(score, rules, domains, F(1))
  assert table.metrics([1])["constant_rules"] == [rules[0].id]
  np.testing.assert_allclose(table.log_probabilities([100]), table.log_probabilities([0]))
