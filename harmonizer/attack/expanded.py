"""Larger development experiment with explicit architectural comparisons."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
import numpy as np
from music21 import corpus
from .benchmark import cached_candidates, evaluate_models, selected_starts, validate_manifest
from .dataset import build
from .dsl import parse
from .import_score import read_musicxml
from .inference import candidates
from .pilot import MELODIC, pitch_domain
from .score import Key, Pitch, Voice

VARIANTS = '''// Architectural controls, handwritten; not API-discovered rules.
At alto or tenor attack n:
  Rule "Spacing counted once per event":
    if n.voice == A or not A attacks at n:
      if distance((T at n), (A at n)) > 12:
        penalty 1
At alto attack a:
  Rule "Spacing at alto attacks":
    if distance((T at a), (A at a)) > 12:
      penalty 1
At tenor attack t:
  Rule "Spacing at tenor attacks":
    if distance((T at t), (A at t)) > 12:
      penalty 1
'''


def depends_on_key(rule):
  def walk(statements):
    for statement in statements:
      for node in statement.expression.iter_subtrees():
        if node.data == "variable" and str(node.children[0]) == "key":
          return True
        if node.data == "call" and str(node.children[0]) == "degree":
          return True
      if walk(statement.body):
        return True
    return False
  return walk(rule.body)


def process_piece(task):
  piece, rule_source, namespace, cache_dir = task
  rules = parse(rule_source)
  path = Path(corpus.getWork(piece["source"]))
  if sha256(path.read_bytes()).hexdigest() != piece["sha256"]:
    raise ValueError("Corpus content hash changed")
  score = read_musicxml(path, Key(Pitch.parse(piece["tonic"]), piece["mode"], "encoded; unverified tonic"))
  domains = {Voice.A: pitch_domain(48,79), Voice.T: pitch_domain(36,72)}
  alternate = piece["outer_key_estimate"]
  alternate_key = Key(Pitch.parse(alternate["tonic"]), alternate["mode"], "S/B-only estimate; sensitivity control")
  changed = (score.key.tonic.semitones % 12, score.key.mode) != (alternate_key.tonic.semitones % 12, alternate_key.mode)
  dependent = [i for i,r in enumerate(rules) if depends_on_key(r)]
  tables, alternative_tables, coverage = [], [], []
  for start in selected_starts(score):
    table = cached_candidates(score, rules, domains, start, Path(cache_dir), namespace)
    alternate_table = table
    if changed and dependent:
      other = cached_candidates(replace(score, key=alternate_key), tuple(rules[i] for i in dependent),
                                domains, start, Path(cache_dir), namespace+"-outer-key-dependent")
      if other.choices != table.choices or other.gold != table.gold:
        raise ValueError("Key sensitivity changed candidate support")
      features = table.features.copy()
      features[:,dependent] = other.features
      alternate_table = replace(table, features=features)
    tables.append(table)
    alternative_tables.append(alternate_table)
    coverage.append({"source":piece["source"],"split":piece["split"],"start":str(start),
                     "attacks":table.first_width,"candidates":len(table.choices),"gold_covered":True})
  print(f"{piece['split']}: {piece['source']}: {len(tables)} decisions", flush=True)
  return piece, score, tables, alternative_tables, coverage


def bootstrap(results, manifest, reference="seed+melodic", repetitions=2000):
  families = {p["source"]:p["family_group"] for p in manifest["pieces"]}
  groups = sorted({families[source] for source in results["by_piece"]})
  rng = np.random.default_rng(20261116)
  # Whole families are resampled; related settings never count as independent.
  indices = rng.integers(len(groups), size=(repetitions,len(groups)))
  intervals = {}
  for name in results["summary"]:
    sums, counts = [], []
    for group in groups:
      rows = [r for source,r in results["by_piece"].items() if families[source] == group]
      sums.append(sum(r[reference]-r[name] for r in rows))
      counts.append(len(rows))
    means = np.asarray(sums)[indices].sum(axis=1) / np.asarray(counts)[indices].sum(axis=1)
    intervals[name] = {"gain_nats": results["summary"][reference]["mean_piece_nll"]-results["summary"][name]["mean_piece_nll"],
                       "interval95": np.quantile(means,[.025,.975]).tolist(),
                       "development_families":len(groups)}
  return intervals


def render(report):
  r, audit = report["results"], report["manifest"]["key_audit"]
  by_split = {split:sum(p["split"]==split for p in report["manifest"]["pieces"]) for split in ("train","development")}
  rows = [
    "# Expanded development and architecture report", "",
    "**Development evidence, not a final test.** Lower negative log likelihood (NLL) is better.",
    "A gain of 0.10 nats means roughly 10.5% higher geometric probability for the observed completion.", "",
    f"- Chorales: {by_split['train']} training, {by_split['development']} development.",
    f"- Decisions: {len(report['coverage'])}; enumerated candidates: {sum(x['candidates'] for x in report['coverage']):,}.",
    f"- Gold-domain coverage: {sum(x['gold_covered'] for x in report['coverage'])}/{len(report['coverage'])}. Unsupported imports are listed below.",
    f"- Key-label disagreements (encoded versus S/B-only estimate): {sum(a['disagreement'] for a in audit)}/{len(audit)}. Neither label is treated as verified truth.",
    "- Fixed S/B, rhythm and prior inner notes; exact one-event prediction. No rhythm generation or figured-bass data.",
    "- Rules from round 001 are being retested. Spacing-count and separate-weight controls are handwritten architectural comparisons.",
    "- The new voices shorthand shares a weight. Separate alto/tenor rules allow different fitted weights.", "",
    "| Model | Piece NLL | Gain vs seed+melodic | 95% family-bootstrap interval | Pieces improved |",
    "|---|---:|---:|---:|---:|"]
  reference = "seed+melodic"
  for name, value in r["summary"].items():
    interval = report["uncertainty"][name]
    wins = sum(row[name] < row[reference] for row in r["by_piece"].values())
    lo, hi = interval["interval95"]
    rows.append(f"| {name} | {value['mean_piece_nll']:.4f} | {interval['gain_nats']:+.4f} | [{lo:+.4f}, {hi:+.4f}] | {wins}/{len(r['by_piece'])} |")
  rows += ["", "Intervals describe sampling variation in these development families, not uncertainty from repeated model selection.",
           "A result whose interval crosses zero is not clearly distinguished on this sample.", "",
           "## Architecture decisions exposed by this run", "",
           "### One harmonic observation or two note-triggered penalties?", "",
           "The original spacing rule contributes twice when alto and tenor both attack.",
           "The once-per-event variant suppresses the tenor contribution when alto also attacks.",
           "The separate-weights variant retains note counting but fits alto and tenor independently.",
           "All three use exactly the same candidate completions and training/development split.", ""]
  for name in ("spacing-shared","spacing-once","spacing-separate"):
    rows.append(f"- **{name}:** NLL {r['summary'][name]['mean_piece_nll']:.4f}; fitted spacing weights " +
      ", ".join(f"{k}={v:.3f}" for k,v in r["weights"][name].items() if "spacing" in k.lower()) + ".")
  rows += ["", "### Enharmonic candidates", "",
           "Generation still distinguishes spellings. The sounding-pitch metric below sums their probabilities before scoring.",
           "It diagnoses the spelling burden; it is not a deduplicated generator or an equivalent comparison task.", "",
           "| Model | Exact-spelling NLL | Sounding-pitch NLL | Geometric spelling probability given sound |",
           "|---|---:|---:|---:|"]
  for name in (reference,"spacing-shared","spacing-once","spacing-separate"):
    dev = r["development"]
    sound_nll = np.mean([x["models"][name]["sounding_gold_nll"] for x in dev])
    spelling = np.exp(np.mean([np.log(x["models"][name]["gold_spelling_given_sounding"]) for x in dev]))
    rows.append(f"| {name} | {r['summary'][name]['mean_nll_per_decision']:.4f} | {sound_nll:.4f} | {spelling:.1%} |")
  rows += ["", "### Key input sensitivity", "",
           "Weights are refitted on training data after replacing encoded keys by an estimate based only on supplied S/B.",
           "Candidate pitches and all key-independent features are unchanged. This does not decide which labels are correct.", "",
           "| Model | Encoded-key NLL | Outer-estimate NLL |",
           "|---|---:|---:|"]
  for name in ("spacing-shared","leading-tone","spacing+leading"):
    rows.append(f"| {name} | {r['summary'][name]['mean_piece_nll']:.4f} | {report['key_sensitivity']['summary'][name]['mean_piece_nll']:.4f} |")
  rows += ["", "### Previously inspected versus newly added development chorales", "",
           "These are descriptive strata, not a newly sealed test set.", "",
           "| Model | Previous five-piece subset | Added development pieces |",
           "|---|---:|---:|"]
  for name, values in report["development_strata"].items():
    rows.append(f"| {name} | {values['previous']:.4f} | {values['added']:.4f} |")
  rows += ["", "### Where the shared spacing rule helps and hurts", "",
           "Times are exact quarter-note offsets in the source score. A/T pairs are in part order.",
           "The top candidate is illustrative; probability of Bach's completion is the evaluated quantity.", "",
           "| Source / time | Bach target | Sounding S / A / T / B | Probability before → after | Top choice after |",
           "|---|---|---|---:|---|"]
  ordered = sorted(r["development"],key=lambda x:x["models"][reference]["first_choice_nll"]-x["models"]["spacing-shared"]["first_choice_nll"])
  for row in ordered[:3]+ordered[-3:]:
    before, after = row["models"][reference], row["models"]["spacing-shared"]
    rows.append(f"| {row['source']} / {row['start']} | {', '.join(after['gold_first_choice'])} | {' / '.join(str(row['sounding'][v]) for v in 'SATB')} | {before['gold_probability']:.3%} → {after['gold_probability']:.3%} | {', '.join(after['top'][0]['pitches'])} |")
  rows += ["", "### Rules with no discriminatory training evidence", ""]
  inactive = [title for title,count in r["training_windows_with_varying_feature"].items() if count==0]
  rows += [f"- {title}" for title in inactive] or ["None."]
  rows += ["", "A zero-activity rule cannot be assessed on these windows. In particular, absent figures do not test figured-bass rules.", "",
           "## Exclusions and remaining limits", ""]
  rows += [f"- {p['source']}: {p['reason']}" for p in report["manifest"]["excluded"]]
  rows += ["", report["manifest"]["grouping"],
           "A few decisions per chorale still under-sample recoveries and cadences. Whole-piece quality remains untested.",
           f"Measured experiment time: {report['runtime_seconds']/60:.1f} minutes. Model-proposal API spending is recorded separately in api-ledger.json.", ""]
  return "\n".join(rows)


def run(workers=2):
  began = perf_counter()
  manifest = build()
  Path("experiments/bach-expanded.json").write_text(json.dumps(manifest,indent=2)+"\n")
  validate_manifest(manifest)
  seed_source = Path("rules/seed.harmony").read_text()
  original_source = Path("rules/proposals/round-001.harmony").read_text()
  source = seed_source+"\n"+MELODIC+"\n"+original_source+"\n"+VARIANTS
  seed, melodic, proposed = parse(seed_source), parse(MELODIC), parse(original_source+"\n"+VARIANTS)
  rules = seed+melodic+proposed
  code = b"".join(Path(__file__).with_name(name).read_bytes() for name in
                 ("score.py","dsl.py","inference.py","import_score.py","pilot.py","expanded.py","dataset.py"))
  namespace = sha256(code+json.dumps(manifest,sort_keys=True).encode()+source.encode()).hexdigest()
  tasks = [(p,source,namespace,"artifacts/expanded-cache") for p in manifest["pieces"]]
  records, alternatives, coverage = [], [], []
  with ProcessPoolExecutor(max_workers=workers) as pool:
    for piece, score, tables, other_tables, covered in pool.map(process_piece,tasks):
      records.extend((piece,score,t) for t in tables)
      alternatives.extend((piece,score,t) for t in other_tables)
      coverage.extend(covered)
  base = list(range(len(seed)+len(melodic)))
  k = len(base)
  inventories = {"seed":list(range(len(seed))),"melodic":list(range(len(seed),k)),
    "seed+melodic":base, "spacing-shared":base+[k], "leading-tone":base+[k+1],
    "parallel-octaves":base+[k+2], "spacing+leading":base+[k,k+1],
    "all-original-proposals":base+[k,k+1,k+2],
    "spacing-once":base+[k+3], "spacing-separate":base+[k+4,k+5]}
  results = evaluate_models(records,seed,melodic,proposed,inventories_override=inventories)
  sensitivity = evaluate_models(alternatives,seed,melodic,proposed,inventories_override=inventories)
  for name, indices in inventories.items():
    if not any(depends_on_key(rules[i]) for i in indices):
      if not np.isclose(results["summary"][name]["mean_piece_nll"],sensitivity["summary"][name]["mean_piece_nll"],rtol=0,atol=1e-10):
        raise ValueError("Key-independent control changed in key sensitivity analysis")
  old = {p["source"] for p in json.loads(Path("experiments/bach-development.json").read_text())["pieces"] if p["split"]=="development"}
  strata = {name:{group:float(np.mean([row[name] for source,row in results["by_piece"].items()
                                     if (source in old)==(group=="previous")]))
                  for group in ("previous","added")} for name in results["summary"]}
  report = {"manifest":manifest,"code_sha256":sha256(code).hexdigest(),"coverage":coverage,
    "results":results,"key_sensitivity":{"summary":sensitivity["summary"],"by_piece":sensitivity["by_piece"]},
    "development_strata":strata,"uncertainty":bootstrap(results,manifest),
    "runtime_seconds":perf_counter()-began,"rules":[{"id":r.id,"title":r.title} for r in rules]}
  artifacts = Path("artifacts"); artifacts.mkdir(exist_ok=True)
  (artifacts/"bach-expanded.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
  summary = {**report,"results":{k:v for k,v in results.items() if k!="development"}}
  Path("experiments/results/expanded-summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n")
  Path("docs/expanded-development.md").write_text(render(report))
  Path("rules/architecture-controls.harmony").write_text(VARIANTS)
  return report


def main():
  p = argparse.ArgumentParser(description=__doc__)
  p.add_argument("--workers",type=int,default=2)
  args = p.parse_args()
  run(args.workers)


if __name__=="__main__":
  main()
