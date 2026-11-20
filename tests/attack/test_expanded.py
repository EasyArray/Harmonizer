from fractions import Fraction as F
import numpy as np
from harmonizer.attack.dsl import evaluate, parse
from harmonizer.attack.expanded import VARIANTS, bootstrap, depends_on_key
from harmonizer.attack.inference import CandidateTable
from harmonizer.attack.pilot import first_metrics
from harmonizer.attack.score import Key, Note, Pitch, Score, Voice


def test_spacing_counts_once_at_joint_and_once_at_single_attack():
  rules = parse(VARIANTS)
  score = Score((Note("a",Voice.A,Pitch.parse("C5"),F(0),F(2)),
                 Note("t",Voice.T,Pitch.parse("C3"),F(0),F(1)),
                 Note("t2",Voice.T,Pitch.parse("D3"),F(1),F(2))),
                 Key(Pitch.parse("C4"),"major"))
  result = evaluate(rules,score)
  assert result.totals[rules[0].id] == 2
  assert result.totals[rules[1].id] == 1
  assert result.totals[rules[2].id] == 2


def test_nested_degree_and_key_dependencies():
  rules = parse('At attack n:\n  Rule "x":\n    if n.voice == A:\n      if degree(n) == 1:\n        penalty 1')
  assert depends_on_key(rules[0])
  assert not any(depends_on_key(r) for r in parse(VARIANTS))


def test_sounding_probability_sums_spelling_alternatives():
  choices = tuple((Pitch.parse(p),) for p in ("C#4","Db4","D4"))
  table = CandidateTable(choices,np.zeros((3,1)),0,("r",),("n",),(F(0),),F(1),(F(0),))
  metrics = first_metrics(table,[0])
  assert np.isclose(metrics["gold_probability"],1/3)
  assert np.isclose(metrics["sounding_gold_probability"],2/3)
  assert np.isclose(metrics["gold_spelling_given_sounding"],.5)
  assert metrics["distinct_sounding_choices"] == 2


def test_family_bootstrap_reports_family_count():
  results = {"summary":{"seed+melodic":{"mean_piece_nll":2},"model":{"mean_piece_nll":1}},
             "by_piece":{s:{"seed+melodic":2,"model":1} for s in ("a","b","c")}}
  manifest = {"pieces":[{"source":s,"family_group":"one" if s in ("a","b") else "two"} for s in ("a","b","c")]}
  interval = bootstrap(results,manifest)["model"]
  assert interval["development_families"] == 2
  assert interval["interval95"] == [1,1]
