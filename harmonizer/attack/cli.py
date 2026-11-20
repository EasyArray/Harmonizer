"""Small offline entry point. No command in this module calls a model API."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys
import numpy as np
from .dsl import evaluate, parse
from .import_score import read_musicxml
from .inference import candidates, fit, load_weights
from .score import Key, Note, Pitch, Score, Voice


def synthetic_score(alto, tenor):
  notes = []
  for voice, pitches in ((Voice.S, ("C5",)*3), (Voice.A, alto), (Voice.T, tenor), (Voice.B, ("C3",)*3)):
    for i, pitch in enumerate(pitches):
      notes.append(Note(f"{voice.name}{i}", voice, Pitch.parse(pitch), Fraction(i), Fraction(i+1)))
  return Score(tuple(notes), Key(Pitch.parse("C4"), "major"), source="synthetic-demo")


def demo(rules):
  domains = {Voice.A: tuple(map(Pitch.parse, ("C3", "C4", "E4", "G4", "C6"))),
             Voice.T: tuple(map(Pitch.parse, ("C2", "C3", "E3", "G3", "C5")))}
  train_scores = [synthetic_score((a,)*3, (t,)*3) for a, t in (("C4", "C3"), ("E4", "E3"))]
  heldout = synthetic_score(("G4",)*3, ("G3",)*3)
  reports = {}
  for horizon in (1, 2):
    train = [candidates(score, rules, domains, Fraction(1), horizon) for score in train_scores]
    test = candidates(heldout, rules, domains, Fraction(1), horizon)
    weights = fit(train)
    reports[str(horizon)] = {
      "weights": {r.title: float(w) for r, w in zip(rules, weights)},
      "uniform": test.metrics(np.zeros(len(rules))),
      "fitted": test.metrics(weights),
      "first_choice_marginal": {" ".join(map(str, choice)): p for choice, p in test.first_choice_probabilities(weights).items()},
      "scoring_window": [str(test.decision_times[0]), str(test.stop)],
    }
  return {
    "purpose": "Synthetic end-to-end software smoke test; not evidence about Bach",
    "conditioning": "Fixed SATB rhythm, S/B pitches, history and C-major global key",
    "domains": {v.name: list(map(str, pool)) for v, pool in domains.items()},
    "weight_policy": "Nonnegative weights, L2 coefficient 0.1; implementation default",
    "api_calls": 0, "horizons": reports,
  }


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("command", choices=("validate", "demo", "score", "predict"))
  parser.add_argument("--rules", default="rules/seed.harmony")
  parser.add_argument("--score", help="Four-part MusicXML file, in SATB part order")
  parser.add_argument("--tonic", default="C4", help="Supplied global tonic, including octave")
  parser.add_argument("--mode", choices=("major", "minor"), default="major")
  parser.add_argument("--start", default="0", help="Exact decision onset in quarter-note units, e.g. 3/2")
  parser.add_argument("--horizon", type=int, default=1)
  parser.add_argument("--alto", help="Comma-separated declared candidate pitches")
  parser.add_argument("--tenor", help="Comma-separated declared candidate pitches")
  parser.add_argument("--weights", help="Saved fitted model JSON, checked against the rule file")
  parser.add_argument("--output", help="Write a JSON report instead of stdout")
  args = parser.parse_args(argv)
  try:
    rules = parse(Path(args.rules).read_text())
    match args.command:
      case "validate":
        report = {"rules": [{"id": r.id, "title": r.title} for r in rules]}
      case "demo":
        report = demo(rules)
      case "score" | "predict":
        if not args.score:
          parser.error("--score is required")
        score = read_musicxml(args.score, Key(Pitch.parse(args.tonic), args.mode))
        if args.command == "score":
          result = evaluate(rules, score)
          report = {"source": score.source, "figure_import": "not implemented", "totals": result.totals, "trace": result.trace}
        else:
          if not args.alto or not args.tenor:
            parser.error("--alto and --tenor must declare pitch domains")
          domains = {Voice.A: tuple(map(Pitch.parse, args.alto.split(","))), Voice.T: tuple(map(Pitch.parse, args.tenor.split(",")))}
          table = candidates(score, rules, domains, Fraction(args.start), args.horizon)
          weights = load_weights(args.weights,args.rules,rules) if args.weights else np.ones(len(rules))
          logp = table.log_probabilities(weights)
          top = np.argsort(-logp, kind="stable")[:10]
          report = {
            "source": score.source, "weights": args.weights or "All ones for inspection; not fitted",
            "figure_import": "not implemented", "metrics": table.metrics(weights),
            "scoring_window": [str(args.start), str(table.stop)],
            "top": [{"pitches": list(map(str, table.choices[i])), "probability": float(np.exp(logp[i]))} for i in top],
          }
    rendered = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
      path = Path(args.output)
      path.parent.mkdir(parents=True, exist_ok=True)
      path.write_text(rendered)
    else:
      print(rendered, end="")
  except (ValueError, OSError, RuntimeError) as error:
    print(f"Error: {error}", file=sys.stderr)
    return 2
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
