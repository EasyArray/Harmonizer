"""Reproducible, deliberately small Bach engineering pilot; no model API calls."""
import argparse
from collections import Counter
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
import numpy as np
from music21 import corpus
from .dsl import parse
from .import_score import read_musicxml
from .inference import candidates, fit
from .score import Key, Pitch, Voice

MELODIC = '''At alto attack a:
  Rule "Alto motion baseline":
    penalty distance(a.previous, a)
At tenor attack t:
  Rule "Tenor motion baseline":
    penalty distance(t.previous, t)
'''


def pitch_domain(low, high):
  return tuple(sorted((Pitch(letter, alteration, octave)
                       for octave in range(1, 7) for letter in "CDEFGAB"
                       for alteration in (-1, 0, 1)
                       if low <= Pitch(letter, alteration, octave).semitones <= high),
                      key=lambda p: (p.semitones, p.steps, p.alteration)))


def select_start(score):
  counts = Counter(n.onset for n in score.notes if n.voice in (Voice.A, Voice.T))
  times = sorted(counts)
  for t, u in zip(times, times[1:]):
    if t > times[0] and counts[t] == counts[u] == 1:
      return t
  raise ValueError("No eligible two-decision window in this piece")


def subset(table, indices):
  return replace(table, features=table.features[:, indices], rule_ids=tuple(table.rule_ids[i] for i in indices))


def pitch_counts(records, domains):
  counts = {voice: Counter({pitch: 1 for pitch in pool}) for voice, pool in domains.items()}
  for score, table in records:
    by_id = {n.id: n for n in score.notes}
    for identity in table.note_ids:
      note = by_id[identity]
      counts[note.voice][note.pitch] += 1
  return counts


def pitch_table(score, table, counts):
  by_id = {n.id: n for n in score.notes}
  voices = [by_id[i].voice for i in table.note_ids]
  totals = {v: sum(c.values()) for v, c in counts.items()}
  features = [[sum(-np.log(counts[v][p] / totals[v]) for v, p in zip(voices, choice))]
              for choice in table.choices]
  return replace(table, features=np.asarray(features), rule_ids=("smoothed-pitch-baseline",))


def first_metrics(table, weights):
  probabilities = table.first_choice_probabilities(weights)
  gold = table.choices[table.gold][:table.first_width]
  p = probabilities[gold]
  return {
    "gold_first_choice": list(map(str, gold)),
    "first_choice_count": len(probabilities),
    "gold_probability": p,
    "first_choice_nll": float(-np.log(p)),
    "rank": 1 + sum(q > p + 1e-12 for q in probabilities.values()),
    "tied_at_gold": sum(abs(q-p) <= 1e-12 for q in probabilities.values()),
    "top": [{"pitches": list(map(str, choice)), "probability": q}
            for choice, q in sorted(probabilities.items(), key=lambda item: -item[1])[:5]],
  }


def run(manifest_path, rules_path):
  started = perf_counter()
  manifest = json.loads(Path(manifest_path).read_text())
  pieces = manifest["pieces"]
  if len({p["source"] for p in pieces}) != len(pieces) or len({p["sha256"] for p in pieces}) != len(pieces):
    raise ValueError("Each source/hash must appear in only one split")
  if any(p["split"] not in ("train", "development") for p in pieces):
    raise ValueError("This inspectable pilot accepts train/development only, never a final test split")
  seed = parse(Path(rules_path).read_text())
  melodic = parse(MELODIC)
  rules = seed + melodic
  # Same fixed domains in every piece/key/horizon, including out-of-range and
  # chromatic possibilities. Never add the gold note after inspecting coverage.
  domains = {Voice.A: pitch_domain(48, 79), Voice.T: pitch_domain(36, 72)}
  records = {1: [], 2: []}
  coverage = []
  for piece in manifest["pieces"]:
    path = Path(corpus.getWork(piece["source"]))
    if sha256(path.read_bytes()).hexdigest() != piece["sha256"]:
      raise ValueError(f"Corpus hash mismatch: {piece['source']}")
    score = read_musicxml(path, Key(Pitch.parse(piece["tonic"]), piece["mode"], "declared in manifest from encoded global key"))
    start = select_start(score)
    for horizon in (1, 2):
      table = candidates(score, rules, domains, start, horizon)
      records[horizon].append((piece, score, table))
      coverage.append({"source": piece["source"], "split": piece["split"], "horizon": horizon,
                       "start": str(start), "stop": str(table.stop), "candidates": len(table.choices),
                       "gold_covered": True})
      print(f"{piece['source']} horizon {horizon}: {len(table.choices)} candidates", flush=True)
  results, weights_report = {}, {}
  for horizon, items in records.items():
    training = [(score, table) for piece, score, table in items if piece["split"] == "train"]
    development = [(piece, score, table) for piece, score, table in items if piece["split"] == "development"]
    if not training or not development:
      raise ValueError("Separate training and development pieces are required")
    seed_indices = list(range(len(seed)))
    melodic_indices = list(range(len(seed), len(rules)))
    seed_weights = fit([subset(t, seed_indices) for _, t in training])
    melodic_weights = fit([subset(t, melodic_indices) for _, t in training])
    counts = pitch_counts(training, domains)
    weights_report[str(horizon)] = {
      "seed": {r.title: float(w) for r, w in zip(seed, seed_weights)},
      "melodic_baseline": {r.title: float(w) for r, w in zip(melodic, melodic_weights)},
    }
    rows = []
    for piece, score, table in development:
      by_id = {n.id: n for n in score.notes}
      context = []
      for identity in table.note_ids[:table.first_width]:
        note = by_id[identity]
        previous = score.previous(note)
        context.append({"voice": note.voice.name, "previous": str(previous.pitch) if previous else None,
                        "bach": str(note.pitch)})
      row = {"source": piece["source"], "start": str(table.decision_times[0]), "context": context,
             "sounding_outer": {v.name: str(score.at(v, table.decision_times[0]).pitch) if score.at(v, table.decision_times[0]) else None for v in (Voice.S, Voice.B)}}
      models = {
        "uniform": (table, np.zeros(len(rules))),
        "seed": (subset(table, seed_indices), seed_weights),
        "melodic_baseline": (subset(table, melodic_indices), melodic_weights),
        "pitch_baseline": (pitch_table(score, table, counts), [1]),
      }
      row["models"] = {name: first_metrics(t, w) for name, (t, w) in models.items()}
      rows.append(row)
    results[str(horizon)] = {
      "development": rows,
      "mean_first_choice_nll": {name: float(np.mean([r["models"][name]["first_choice_nll"] for r in rows]))
                                for name in rows[0]["models"]},
    }
  return {
    "purpose": manifest["purpose"], "selection": manifest["selection"],
    "manifest_sha256": sha256(Path(manifest_path).read_bytes()).hexdigest(),
    "rules_sha256": sha256(Path(rules_path).read_bytes()).hexdigest(),
    "domains": {v.name: list(map(str, pool)) for v, pool in domains.items()},
    "coverage": coverage, "weights": weights_report, "results": results,
    "training_policy": "Fit each horizon on training windows only; L2=0.1, nonnegative weights. Pitch baseline has add-one smoothing on the same target slots.",
    "limitations": ["Only two training windows and two development windows per horizon",
                    "Rhythm-selected windows have one inner voice attacking at each decision",
                    "Different pieces, but tune-family grouping has not been audited",
                    "No final test set opened; these development examples are now inspectable",
                    "Global key and future S/B/rhythm supplied; no figured bass or rhythm generation",
                    "Averaged first-choice NLL is comparable across horizons on these same starts; not a population estimate"],
    "runtime_seconds": perf_counter() - started, "api_calls": 0,
  }


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--manifest", default="experiments/bach-pilot.json")
  parser.add_argument("--rules", default="rules/seed.harmony")
  parser.add_argument("--output", default="artifacts/bach-pilot.json")
  args = parser.parse_args()
  report = run(args.manifest, args.rules)
  path = Path(args.output)
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
  print(json.dumps({h: r["mean_first_choice_nll"] for h, r in report["results"].items()}, indent=2))


if __name__ == "__main__":
  main()
