from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
import pytest
from harmonizer.attack.benchmark import selected_starts, validate_manifest, cached_candidates
from harmonizer.attack.dsl import parse, evaluate
from harmonizer.attack.score import Key, Note, Pitch, Score, Voice


def note(identity, voice, pitch, start, stop):
  return Note(identity, Voice[voice], Pitch.parse(pitch), F(start), F(stop))


def test_stratified_selection_and_cache_roundtrip(tmp_path):
  score=Score(tuple(note(str(i),"A","C4",i,i+1) for i in range(8)),Key(Pitch.parse("C4"),"major"))
  assert selected_starts(score)==[F(1),F(4),F(7)]
  rules=parse('At attack a:\n  Rule "distance":\n    penalty distance(a.previous,a)')
  domains={Voice.A:(Pitch.parse("C4"),Pitch.parse("D4"))}
  first=cached_candidates(score,rules,domains,F(1),tmp_path,"test")
  second=cached_candidates(score,rules,domains,F(1),tmp_path,"test")
  assert first.choices==second.choices
  assert first.features.tolist()==second.features.tolist()
  assert first.note_ids==second.note_ids and first.decision_times==second.decision_times
  larger={Voice.A:domains[Voice.A]+(Pitch.parse("E4"),)}
  assert len(cached_candidates(score,rules,larger,F(1),tmp_path,"test").choices)==3


def test_group_split_guard():
  pieces=[{"source":"a","sha256":"1","split":"train","title_group":"a","melody_group":"x"},
          {"source":"b","sha256":"2","split":"development","title_group":"b","melody_group":"y"}]
  validate_manifest({"pieces":pieces})
  pieces[1]["melody_group"]="x"
  with pytest.raises(ValueError,match="leakage"):
    validate_manifest({"pieces":pieces})
  pieces[1]["split"]="test"
  with pytest.raises(ValueError,match="splits"):
    validate_manifest({"pieces":pieces})


def test_generated_spacing_counts_each_inner_attack():
  rules=parse(Path("rules/proposals/round-001.harmony").read_text())
  spacing=tuple(r for r in rules if r.title=="Inner-voice spacing")
  score=Score((note("a","A","G4",0,1),note("t","T","C3",0,1)),Key(Pitch.parse("C4"),"major"))
  assert list(evaluate(spacing,score).totals.values())==[2]
  close=replace(score,notes=(replace(score.notes[0],pitch=Pitch.parse("G3")),score.notes[1]))
  assert list(evaluate(spacing,close).totals.values())==[0]


def test_generated_leading_tone_rule_has_documented_global_and_octave_scope():
  rules=tuple(r for r in parse(Path("rules/proposals/round-001.harmony").read_text()) if r.title=="Inner leading-tone resolution")
  # The proposal checks degree, not a one-semitone upward resolution.
  score=Score((note("a0","A","B4",0,1),note("a1","A","C4",1,2)),Key(Pitch.parse("C4"),"major"))
  assert list(evaluate(rules,score).totals.values())==[0]
  repetition=replace(score,notes=(score.notes[0],replace(score.notes[1],pitch=Pitch.parse("B4"))))
  assert list(evaluate(rules,repetition).totals.values())==[1]


def test_benchmark_metrics_are_json_serializable(tmp_path):
  import json
  from harmonizer.attack.benchmark import evaluate_models
  from harmonizer.attack.pilot import MELODIC, pitch_domain
  from harmonizer.attack.inference import candidates
  seed=parse('At attack n:\n  Rule "large":\n    if distance(n.previous,n)>7:\n      penalty 1')
  melodic=parse(MELODIC)
  score=Score((note("a0","A","C4",0,1),note("a1","A","D4",1,2),note("a2","A","E4",2,3),
               note("t0","T","C3",0,2),note("t1","T","D3",2,3)),Key(Pitch.parse("C4"),"major"))
  domains={Voice.A:tuple(map(Pitch.parse,("C4","D4","E4"))),Voice.T:tuple(map(Pitch.parse,("C3","D3")))}
  tables=[candidates(score,seed+melodic,domains,F(i)) for i in (1,2)]
  records=[({"source":split,"split":split},score,t) for split in ("train","development") for t in tables]
  report=evaluate_models(records,seed,melodic,())
  assert json.loads(json.dumps(report,allow_nan=False))["training_windows_with_varying_feature"]["large"]==0
