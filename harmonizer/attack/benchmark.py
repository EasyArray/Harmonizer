"""Larger exact one-event development evaluation; no model calls or test split."""
import argparse
from collections import Counter
from dataclasses import replace
from fractions import Fraction
from hashlib import sha256
import json
import inspect
from itertools import combinations
from pathlib import Path
from time import perf_counter
import numpy as np
from music21 import corpus
from .dsl import parse
from .import_score import read_musicxml
from .inference import CandidateTable, candidates, fit
from .pilot import MELODIC, first_metrics, pitch_counts, pitch_domain, pitch_table, subset
from .score import Key, Pitch, Voice


def selected_starts(score):
  counts = Counter(n.onset for n in score.notes if n.voice in (Voice.A, Voice.T))
  starts = []
  for attacks in (1, 2):
    times = sorted(t for t, count in counts.items() if count == attacks and t > min(counts))
    if times:
      starts.extend(times[i] for i in sorted({0, (len(times)-1)//2, len(times)-1}))
  return sorted(starts)


def validate_manifest(manifest):
  pieces = manifest["pieces"]
  if not pieces or {p["split"] for p in pieces} != {"train", "development"}:
    raise ValueError("Only train/development splits are allowed; both required")
  if len({p["source"] for p in pieces}) != len(pieces) or len({p["sha256"] for p in pieces}) != len(pieces):
    raise ValueError("Duplicated source or content hash")
  for group_field in ("title_group", "melody_group"):
    groups = {}
    for p in pieces:
      group = p[group_field]
      if group in groups and groups[group] != p["split"]:
        raise ValueError(f"Cross-split {group_field} leakage")
      groups[group] = p["split"]


def cached_candidates(score, rules, domains, start, cache_dir, cache_namespace):
  domain_key=json.dumps({v.name:list(map(str,pool)) for v,pool in domains.items()},sort_keys=True)
  identity = sha256(f"{cache_namespace}|{score.source}|{start}|{domain_key}".encode()).hexdigest()
  path = cache_dir / f"{identity}.npz"
  if path.exists():
    with np.load(path, allow_pickle=False) as data:
      return CandidateTable(
        tuple(tuple(Pitch.parse(p) for p in row) for row in data["choices"]), data["features"],
        int(data["gold"]), tuple(data["rule_ids"]), tuple(data["note_ids"]),
        tuple(Fraction(t) for t in data["decision_times"]), Fraction(str(data["stop"])),
        tuple(Fraction(t) for t in data["note_times"]))
  table = candidates(score, rules, domains, start)
  cache_dir.mkdir(parents=True, exist_ok=True)
  temporary = path.with_suffix(".tmp.npz")
  np.savez_compressed(temporary, choices=np.asarray([[str(p) for p in row] for row in table.choices]),
    features=table.features, gold=table.gold, rule_ids=table.rule_ids, note_ids=table.note_ids,
    decision_times=list(map(str, table.decision_times)), stop=str(table.stop), note_times=list(map(str, table.note_times)))
  temporary.replace(path)
  return table


def evaluate_models(records, seed, melodic, proposed, include_pairs=False, inventories_override=None):
  rules = seed + melodic + proposed
  train = [(s,t) for p,s,t in records if p["split"] == "train"]
  dev = [(p,s,t) for p,s,t in records if p["split"] == "development"]
  if not train or not dev:
    raise ValueError("No train/development windows")
  domains = {Voice.A: pitch_domain(48,79), Voice.T: pitch_domain(36,72)}
  counts = pitch_counts(train, domains)
  base = list(range(len(seed)+len(melodic)))
  inventories = {"seed": list(range(len(seed))), "melodic": list(range(len(seed),len(base))), "seed+melodic": base}
  for i, r in enumerate(proposed, len(base)):
    inventories[f"base+proposal:{r.title}"] = base+[i]
  if proposed:
    inventories["base+all-proposals"] = list(range(len(rules)))
  if include_pairs:
    for pair in combinations(range(len(base),len(rules)),2):
      inventories["base+pair:"+" | ".join(rules[i].title for i in pair)]=base+list(pair)
  if inventories_override is not None:
    inventories = inventories_override
  fitted = {name: fit([subset(t, indices) for _,t in train]) for name,indices in inventories.items()}
  rows = []
  for p, score, table in dev:
    by_id = {n.id:n for n in score.notes}
    context = [{"voice":by_id[i].voice.name,"previous":str(score.previous(by_id[i]).pitch) if score.previous(by_id[i]) else None,
                "bach":str(by_id[i].pitch)} for i in table.note_ids]
    models = {"uniform":(table,np.zeros(len(rules))), "pitch":(pitch_table(score,table,counts),[1])}
    models.update({name:(subset(table,indices),fitted[name]) for name,indices in inventories.items()})
    rows.append({"source":p["source"],"start":str(table.decision_times[0]),"context":context,"attacks":table.first_width,
                 "sounding":{v.name:str(score.at(v,table.decision_times[0]).pitch) if score.at(v,table.decision_times[0]) else None for v in Voice},
                 "models":{name:first_metrics(t,w) for name,(t,w) in models.items()}})
  names = list(rows[0]["models"])
  sources = sorted({r["source"] for r in rows})
  by_piece = {source:{name:float(np.mean([r["models"][name]["first_choice_nll"] for r in rows if r["source"]==source]))
                     for name in names} for source in sources}
  summary = {name:{"mean_nll_per_decision":float(np.mean([r["models"][name]["first_choice_nll"] for r in rows])),
                   "mean_piece_nll":float(np.mean([v[name] for v in by_piece.values()])),
                   "mean_nll_single_attack":float(np.mean([r["models"][name]["first_choice_nll"] for r in rows if r["attacks"]==1])),
                   "mean_nll_joint_attack":float(np.mean([r["models"][name]["first_choice_nll"] for r in rows if r["attacks"]==2]))}
             for name in names}
  activity = {r.title:int(sum(np.ptp(t.features[:,i]) > 0 for _,t in train)) for i,r in enumerate(rules)}
  return {"summary":summary,"by_piece":by_piece,"development":rows,
          "added_rules":{name:[rules[i].title for i in indices if i>=len(base)] for name,indices in inventories.items()},
          "weights":{name:{rules[i].title:float(w) for i,w in zip(inventories[name],weights)} for name,weights in fitted.items()},
          "training_windows_with_varying_feature":activity}


def run(manifest_path, rules_path, proposals_path=None, cache_dir=Path("artifacts/feature-cache"), include_pairs=False):
  began=perf_counter()
  manifest=json.loads(Path(manifest_path).read_text())
  validate_manifest(manifest)
  seed=parse(Path(rules_path).read_text())
  melodic=parse(MELODIC)
  proposed=parse(Path(proposals_path).read_text()) if proposals_path else ()
  if len(proposed)>3:
    raise ValueError("At most three proposals per initial round")
  rules=seed+melodic+proposed
  if len({r.id for r in rules})!=len(rules) or len({r.title for r in rules})!=len(rules):
    raise ValueError("Rule IDs and titles must be distinct across inventories")
  domains={Voice.A:pitch_domain(48,79),Voice.T:pitch_domain(36,72)}
  source_files=("score.py","dsl.py","inference.py","import_score.py","benchmark.py","pilot.py")
  code_hash=sha256(b"".join(Path(__file__).with_name(name).read_bytes() for name in source_files)).hexdigest()
  # Feature caches depend on scoring semantics, not report formatting or the
  # weight loader. Keep the full pipeline hash separately for provenance.
  feature_source=b"".join(Path(__file__).with_name(name).read_bytes() for name in ("score.py","dsl.py","import_score.py"))
  feature_source+=inspect.getsource(candidates).encode()+inspect.getsource(pitch_domain).encode()
  feature_hash=sha256(feature_source).hexdigest()
  cache_namespace=sha256((json.dumps(manifest,sort_keys=True)+str([r.id for r in rules])+feature_hash).encode()).hexdigest()
  records=[]; coverage=[]
  for piece in manifest["pieces"]:
    path=Path(corpus.getWork(piece["source"]))
    if sha256(path.read_bytes()).hexdigest()!=piece["sha256"]:
      raise ValueError(f"Source hash changed: {piece['source']}")
    score=read_musicxml(path,Key(Pitch.parse(piece["tonic"]),piece["mode"],"manifest; encoded global key"))
    starts=selected_starts(score)
    for start in starts:
      table=cached_candidates(score,rules,domains,start,Path(cache_dir),cache_namespace)
      records.append((piece,score,table))
      coverage.append({"source":piece["source"],"split":piece["split"],"start":str(start),
                       "attacks":table.first_width,"candidates":len(table.choices),"gold_covered":True})
    print(f"{piece['split']}: {piece['source']}: {len(starts)} decisions",flush=True)
  results=evaluate_models(records,seed,melodic,proposed,include_pairs)
  return {"manifest_sha256":sha256(Path(manifest_path).read_bytes()).hexdigest(),"code_sha256":code_hash,"feature_code_sha256":feature_hash,
          "rules":[{"id":r.id,"title":r.title} for r in rules],"coverage":coverage,"results":results,
          "domains":{v.name:list(map(str,p)) for v,p in domains.items()},
          "policy":"One exact event; supplied global key, S/B, rhythm and past inner pitches. Fit on training only. L2=0.1, nonnegative weights. Equal-piece NLL is primary; development only, no final test.",
          "grouping":manifest["grouping"],"excluded":manifest["excluded"],"runtime_seconds":perf_counter()-began}


def main():
  p=argparse.ArgumentParser(description=__doc__)
  p.add_argument("--manifest",default="experiments/bach-development.json")
  p.add_argument("--rules",default="rules/seed.harmony")
  p.add_argument("--proposals")
  p.add_argument("--output",default="artifacts/bach-development.json")
  p.add_argument("--pairs",action="store_true",help="Exploratory pairwise pruning after the initial round")
  args=p.parse_args()
  report=run(args.manifest,args.rules,args.proposals,include_pairs=args.pairs)
  path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
  path.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
  print(json.dumps(report["results"]["summary"],indent=2))


if __name__=="__main__":
  main()
