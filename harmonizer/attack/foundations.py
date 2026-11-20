"""Reproduce the five-family, one-attack-event Bach experiment from the repo root."""
from collections import Counter, defaultdict
from dataclasses import replace
from functools import lru_cache
from hashlib import sha256
from itertools import product
import json
from pathlib import Path

import numpy as np
from music21 import corpus

from .benchmark import selected_starts, validate_manifest
from .dsl import parse
from .expanded import bootstrap
from .import_score import read_musicxml
from .inference import candidates, fit
from .pilot import pitch_domain, subset
from .score import Key, Pitch, Voice

MANIFEST = Path("experiments/bach-expanded.json")
RULEBOOK = Path("rules/foundations.harmony")
GROUPS = {
  "range": ("Alto range", "Tenor range"),
  "motion": ("Alto motion", "Tenor motion"),
  "large leap": ("Large leaps",),
  "diatonicity": ("Global diatonicity",),
  "outer consonance": ("Outer consonance",),
}


@lru_cache(maxsize=6)
def layout(pools):
  choices = tuple(product(*pools))
  sounds = [tuple(p.semitones for p in row) for row in choices]
  _, sound_ids = np.unique(sounds, axis=0, return_inverse=True)
  return choices, sound_ids.reshape(-1)


def event_table(score, start, rules, domains):
  """These seven rules read only the attacked note, its past, S/B and key.
  For a joint attack, add each alto row to each tenor row in product order.
  Rules that inspect the other inner voice require the general candidates().
  """
  outer = [n for v in (Voice.S, Voice.B) if (n := score.at(v, start))]
  targets = [n for n in score.attacks_at(start) if n.voice in domains]
  tables = []
  for note in targets:
    past = score.previous(note)
    notes = outer + ([past] if past else []) + [note]
    local_score = replace(score, notes=tuple(notes), figures=())
    tables.append(candidates(local_score, rules, domains, start))
  pools = tuple(domains[n.voice] for n in targets)
  choices, sound_ids = layout(pools)
  base = tables[0]
  features, gold = base.features, base.gold
  if len(tables) == 2:
    other = tables[1]
    features = (features[:, None, :] + other.features[None, :, :]).reshape(len(choices), -1)
    gold = gold * len(other.choices) + other.gold
  if choices[gold] != tuple(n.pitch for n in targets):
    raise ValueError("Candidate product order disagrees with the observed score")
  later_attacks = (n.onset for n in score.notes if n.voice in domains and n.onset > start)
  stop = min(later_attacks, default=max(n.offset for n in score.notes))
  return replace(base, choices=choices, features=features, gold=gold, stop=stop,
                 note_ids=tuple(n.id for n in targets), note_times=(start,) * len(targets)), sound_ids


def metrics(table, sound_ids, weights):
  logp = table.log_probabilities(weights)
  sound_p = np.bincount(sound_ids, weights=np.exp(logp))
  sound_logp = np.log(sound_p)
  sound_gold = sound_logp[sound_ids[table.gold]]
  gold = logp[table.gold]
  return {
    "written_nll": float(-gold),
    "sound_nll": float(-sound_gold),
    "sound_strict_win": float(np.sum(sound_logp < sound_gold - 1e-10) / (len(sound_p) - 1)),
    "strict_win": float(np.sum(logp < gold - 1e-10) / (len(logp) - 1)),
    "tie": float((np.sum(abs(logp - gold) <= 1e-10) - 1) / (len(logp) - 1)),
  }


def means(rows):
  return {key: float(np.mean([r[key] for r in rows])) for key in rows[0]}


def run():
  manifest = json.loads(MANIFEST.read_text())
  validate_manifest(manifest)
  rules = parse(RULEBOOK.read_text())
  names = [r.title for r in rules]
  if set(names) != {name for group in GROUPS.values() for name in group}:
    raise ValueError("Rule inventory differs from the five-family study")
  domains = {Voice.A: pitch_domain(48, 79), Voice.T: pitch_domain(36, 72)}
  audits = {a["source"]: a for a in manifest["key_audit"]}
  # Only the published rulebook has been checked for per-voice independence.
  # Edited rules may couple A and T. Use the general scorer for those.
  rule_hash = sha256(RULEBOOK.read_bytes()).hexdigest()
  factorizes = rule_hash == "48ec6d38f8c9204c9b27e767cd7522c85cec45d6f62fbad3549b800e31293f86"
  records = []
  examples = {}
  coverage = []
  screened = {}
  for p in manifest["pieces"]:
    source = p["source"]
    path = Path(corpus.getWork(source))
    if sha256(path.read_bytes()).hexdigest() != p["sha256"]:
      raise ValueError(f"Source changed: {source}")
    key = Key(Pitch.parse(p["tonic"]), p["mode"])
    score = read_musicxml(path, key)
    audit = audits[source]
    final_bass = Pitch.parse(audit["final_bass"])
    screened[source] = not audit["disagreement"] and (key.tonic.semitones - final_bass.semitones) % 12 == 0
    for start in selected_starts(score):
      if factorizes:
        table, sound_ids = event_table(score, start, rules, domains)
      else:
        table = candidates(score, rules, domains, start)
        pools = tuple(domains[n.voice] for n in score.attacks_at(start) if n.voice in domains)
        _, sound_ids = layout(pools)
      # Illustrate the first eligible development event of each width, in manifest order.
      if p["split"] == "development" and screened[source] and table.first_width not in examples:
        examples[table.first_width] = {
          "source": source, "start": str(start), "bach": list(map(str, table.choices[table.gold])),
          "sounding": {v.name: str(n.pitch) for v in Voice if (n := score.at(v, start))},
          "previous": {n.voice.name: str(prev.pitch) if (prev := score.previous(n)) else None
                       for n in score.attacks_at(start) if n.voice in domains},
          "models": {},
        }
      if not screened[source]:
        table.features[:, names.index("Global diatonicity")] = 0
      records.append((p, table, sound_ids))
      coverage.append(dict(source=source, split=p["split"], start=str(start), attacks=table.first_width,
                           candidates=len(table.choices), gold_covered=True))
  previous = json.loads(Path("experiments/results/round-002-summary.json").read_text())
  if coverage != previous["coverage"]:
    raise ValueError("Event or candidate coverage differs from round 002")

  train = [t for p, t, ids in records if p["split"] == "train"]
  development = [(p["source"], t, ids) for p, t, ids in records if p["split"] == "development"]
  all_groups = list(GROUPS)
  inventories = {"uniform": [], **{g: [g] for g in all_groups}, "full": all_groups}
  inventories.update({f"without {g}": [h for h in all_groups if h != g] for g in all_groups})
  weights, summary = {}, {}
  by_piece = defaultdict(dict)
  strata = {}
  for model, families in inventories.items():
    indices = [names.index(title) for g in families for title in GROUPS[g]]
    fitted = fit([subset(t, indices) for t in train]) if indices else []
    weights[model] = {names[i]: float(w) for i, w in zip(indices, fitted)}
    vector = np.zeros(len(rules))
    vector[indices] = fitted
    groups = defaultdict(list)
    pieces = defaultdict(list)
    for source, table, sound_ids in development:
      result = metrics(table, sound_ids, vector)
      example = examples.get(table.first_width)
      if example and (source, str(table.decision_times[0])) == (example["source"], example["start"]):
        example["models"][model] = result
      pieces[source].append(result)
      groups[f"{table.first_width} attacking"].append(result)
      groups["key screened in" if screened[source] else "key screened out"].append(result)
    for source, rows in pieces.items():
      by_piece[source][model] = means(rows)
    summary[model] = means([models[model] for models in by_piece.values()])
    strata[model] = {group: means(rows) for group, rows in groups.items()}
  for name, old in (("motion", "melodic"), ("uniform", "uniform")):
    if (factorizes or name == "uniform") and not np.isclose(summary[name]["written_nll"], previous["results"]["summary"][old]["mean_piece_nll"], atol=1e-7, rtol=0):
      raise ValueError(f"Round 002 control failed to reproduce: {name}")

  # Since all five families ignore spelling, sound and written log gains agree.
  comparison = {"summary": {k: {"mean_piece_nll": v["sound_nll"]} for k, v in summary.items()},
                "by_piece": {s: {k: v["sound_nll"] for k, v in models.items()} for s, models in by_piece.items()}}
  return {"manifest_sha256": sha256(MANIFEST.read_bytes()).hexdigest(),
          "rules_sha256": rule_hash, "examples": examples,
          "domain": {v.name: list(map(str, pool)) for v, pool in domains.items()},
          "decisions": dict(Counter(row["split"] for row in coverage)),
          "candidate_count": sum(row["candidates"] for row in coverage),
          "key_screen": screened, "summary": summary, "strata": strata, "weights": weights,
          "against_uniform": bootstrap(comparison, manifest, reference="uniform"),
          "against_full": bootstrap(comparison, manifest, reference="full"), "by_piece": by_piece}


if __name__ == "__main__":
  results = run()
  path = Path("experiments/results/foundations.json")
  path.write_text(json.dumps(results, indent=2, allow_nan=False) + "\n")
  print(json.dumps(results["summary"], indent=2))
