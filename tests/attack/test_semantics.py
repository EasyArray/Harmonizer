from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
import pytest
from music21 import stream, note, tie
from harmonizer.attack.score import Degree, Figure, Interval, Key, Note, Pitch, Score, Voice
from harmonizer.attack.dsl import DSLError, evaluate, parse
from harmonizer.attack.import_score import from_music21

KEY = Key(Pitch.parse("C4"), "major")


def n(identity, voice, pitch, start, stop):
  return Note(identity, Voice[voice], Pitch.parse(pitch), F(start), F(stop))


def rule(trigger, body):
  return parse(f'{trigger}:\n  Rule "test":\n' + '\n'.join('    ' + line for line in body.splitlines()))


@pytest.mark.parametrize("attacks,expected", [(4, (4, 6, 0)), (1, (1, 0, 3)), (2, (2, 1, 4))])
def test_trigger_counts_and_order(attacks, expected):
  notes = tuple(n(v, v, p, 1 if i < attacks else 0, 2)
                for i, (v, p) in enumerate(zip("SATB", ("C4", "D4", "E4", "F4"))))
  score = Score(notes, KEY)
  triggers = ("At attack x", "At attack (upper, lower)", "At attack x while y holds")
  actual = [sum(evaluate(rule(t, "penalty 1"), score, F(1)).totals.values()) for t in triggers]
  assert tuple(actual) == expected
  pairs = rule(triggers[1], "if upper.voice is above lower.voice:\n  penalty 1")
  assert sum(evaluate(pairs, score, F(1)).totals.values()) == expected[1]
  assert evaluate(pairs, replace(score, notes=notes[::-1]), F(1)).totals == evaluate(pairs, score, F(1)).totals


def test_missing_history_does_not_erase_siblings_or_make_not_true():
  rules = rule("At attack n", "if not distance(n.previous, n) > 7:\n  penalty 100\nif n.voice == T:\n  penalty -3")
  result = evaluate(rules, Score((n("t", "T", "C4", 0, 1),), KEY))
  assert list(result.totals.values()) == [-3]
  assert result.trace[0]["status"] == "skipped"
  after_rest = Score((n("a", "T", "C4", 0, 1), n("b", "T", "D4", 2, 3)), KEY)
  assert after_rest.previous(after_rest.notes[1]) is None


def test_before_at_and_anchor_onset():
  score = Score((n("old", "A", "C4", 0, 1), n("new", "A", "D4", 1, 2),
                 n("held", "T", "C3", 0, 2)), KEY)
  rules = rule("At alto attack a", "if distance(A before a, A at a) == 2 and A attacks at a:\n  penalty 1")
  assert sum(evaluate(rules, score).totals.values()) == 1
  rules = rule("At attack a while h holds", "if distance(A at h, a) == 2:\n  penalty 1")
  assert sum(evaluate(rules, score).totals.values()) == 1


def test_nested_siblings_negative_penalties_and_scope():
  rules = rule("At attack n", "let d = distance(n, C4)\nif d > 0:\n  if d > 1:\n    penalty d - 1\n  penalty -3\nif d == 2:\n  penalty 5")
  assert sum(evaluate(rules, Score((n("n", "A", "D4", 0, 1),), KEY)).totals.values()) == 3
  with pytest.raises(DSLError):
    rule("At attack n", "if n.voice == A:\n  let local = 1\npenalty local")


def test_minor_degrees_spelling_and_signed_intervals():
  key = Key(Pitch.parse("C4"), "minor")
  assert [key.degree(Pitch.parse(p)) for p in ("Eb3", "E5", "Bb4", "B3")] == [Degree(3), Degree(3, 1), Degree(7), Degree(7, 1)]
  rules = rule("At attack n", "if degree(n) == #3:\n  penalty 1")
  assert sum(evaluate(rules, Score((n("n", "A", "E4", 0, 1),), key)).totals.values()) == 1
  assert Interval.parse("P12") != Interval.parse("P5")


@pytest.mark.parametrize("first,second,expected", [
  (("G4", "C4"), ("A4", "D4"), 1),
  (("C4", "G4"), ("D4", "A4"), 1),
  (("G4", "C4"), ("G4", "C4"), 0),
  (("F##4", "C4"), ("G##4", "D4"), 0),
])
def test_parallel_exact_fifths(first, second, expected):
  rules = tuple(r for r in parse(Path("rules/seed.harmony").read_text()) if r.title == "Parallel exact fifths")
  score = Score(tuple(n(f"{v}{i}", v, pitches[j], i, i+1)
                      for i, pitches in enumerate((first, second)) for j, v in enumerate("AT")), KEY)
  assert sum(evaluate(rules, score).totals.values()) == expected


@pytest.mark.parametrize("body", ["penalty n", "penalty __import__(\"os\")", "penalty n.pitch", "if 1:\n  penalty 1", "penalty interval(n,n).unknown", "if distance(n,n) > 0 > 1:\n  penalty 1"])
def test_static_type_and_syntax_rejection(body):
  with pytest.raises(DSLError):
    rule("At attack n", body)


def test_division_by_zero_is_failure_not_missing():
  with pytest.raises(DSLError, match="Division by zero"):
    evaluate(rule("At attack n", "penalty 1 / 0"), Score((n("n", "A", "C4", 0, 1),), KEY))


def test_figure_and_title_independent_identity():
  rules = rule("At figure f", "penalty distance(A at f, T at f)")
  renamed = parse('At figure f:\n  Rule "new title":\n    penalty distance(A at f, T at f)')
  assert rules[0].id == renamed[0].id
  score = Score((n("a", "A", "C4", 0, 2), n("t", "T", "C3", 0, 2)), KEY,
                (Figure("fig", F(1), "6/4"),))
  assert sum(evaluate(rules, score).totals.values()) == 12


def test_import_merges_ties_but_not_repeated_notes_and_preserves_tuplets():
  score = stream.Score()
  for pitch in ("C5", "G4", "E4", "C3"):
    part = stream.Part()
    for i in range(3):
      item = note.Note(pitch, quarterLength=F(1,3))
      if i < 2:
        item.tie = tie.Tie("start" if i == 0 else "stop")
      part.append(item)
    score.insert(0, part)
  imported = from_music21(score, KEY)
  assert len(imported.notes) == 8
  assert imported.notes[0].offset == F(2,3)
  assert imported.notes[1].onset == F(2,3)
  assert imported.previous(imported.notes[1]) == imported.notes[0]
  score.parts[0].flatten().notes[1].tie = None
  with pytest.raises(ValueError, match="Unterminated tie"):
    from_music21(score, KEY)

  
def test_voice_union_is_one_binding_per_attacking_note():
  score = Score(tuple(n(v, v, p, 0, 1) for v, p in zip("SATB", ("C5", "G4", "E4", "C3"))), KEY)
  selected = rule("At alto or tenor attack n", "penalty 1")
  generic = rule("At attack n", "if n.voice == A or n.voice == T:\n  penalty 1")
  assert sum(evaluate(selected, score).totals.values()) == 2
  assert sum(evaluate(generic, score).totals.values()) == 2
  reordered = rule("At tenor or alto attack n", "penalty 1")
  assert selected[0].id == reordered[0].id
  assert len(selected[0].trigger.names) == 1
  assert sum(evaluate(rule("At tenor attack n", "penalty 1"), score).totals.values()) == 1
  assert sum(evaluate(rule("At attack n", "penalty 1"), score).totals.values()) == 4
  with pytest.raises(DSLError, match="only once"):
    rule("At alto or alto attack n", "penalty 1")
  with pytest.raises(DSLError):
    rule("At alto or tenor attack a,t", "penalty 1")


def test_indexed_score_boundaries_rests_and_replaced_pitches():
  # Deliberately unordered source notes; a rest separates the second and third.
  notes = (n("late","A","G4",3,4),n("first","A","C4",0,1),n("second","A","D4",1,2))
  score = Score(notes,KEY)
  times = [F(0),F(1,2),F(1),F(2),F(5,2),F(3),F(4)]
  def identities(before):
    return [item.id if (item:=score.at(Voice.A,t,before)) else None for t in times]
  assert identities(False) == ["first","first","second",None,None,"late",None]
  assert identities(True) == [None,"first","first","second",None,None,"late"]
  assert score.previous(notes[0]) is None
  assert score.previous(notes[2]).id == "first"
  assert [x.id for x in score.attacks_at(F(1))] == ["second"]
  changed = replace(score, notes=tuple(replace(x,pitch=Pitch.parse("E4")) if x.id=="first" else x for x in notes))
  assert str(changed.at(Voice.A,F(0)).pitch) == "E4"
  assert str(changed.previous(notes[2]).pitch) == "E4"
  assert str(score.previous(notes[2]).pitch) == "C4"
