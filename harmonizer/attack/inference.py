"""Exact finite-candidate conditional MaxEnt, for one or several decisions."""
from dataclasses import dataclass, replace
from itertools import product
from math import prod
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp
from .dsl import evaluate
from .score import Voice


class CoverageError(ValueError):
  """The declared generator cannot represent the observed completion."""


@dataclass(frozen=True)
class CandidateTable:
  choices: tuple
  features: np.ndarray
  gold: int
  rule_ids: tuple[str, ...]
  note_ids: tuple[str, ...]
  decision_times: tuple
  stop: object

  def log_probabilities(self, weights):
    weights = np.asarray(weights, dtype=float)
    if weights.shape != (len(self.rule_ids),) or not np.isfinite(weights).all():
      raise ValueError("Expected one finite weight per rule")
    logits = -self.features @ weights
    if not np.isfinite(logits).all():
      raise ValueError("Nonfinite candidate energies")
    return logits - logsumexp(logits)

  def metrics(self, weights):
    logp = self.log_probabilities(weights)
    # Optimistic rank; ties are explicitly reported.
    return {
      "candidates": len(self.choices), "gold_covered": True,
      "gold_probability": float(np.exp(logp[self.gold])),
      "nll": float(-logp[self.gold]),
      "rank": int(1 + np.sum(logp > logp[self.gold])),
      "tied_at_gold": int(np.sum(logp == logp[self.gold])),
      "constant_rules": [r for r, constant in zip(self.rule_ids, np.ptp(self.features, axis=0) == 0) if constant],
    }

  def first_choice_probabilities(self, weights):
    count = len(self.choices[0]) if len(self.decision_times) == 1 else self.first_width
    logp, groups = self.log_probabilities(weights), {}
    for choice, value in zip(self.choices, logp):
      prefix = choice[:count]
      groups.setdefault(prefix, []).append(value)
    return {prefix: float(np.exp(logsumexp(values))) for prefix, values in groups.items()}

  @property
  def first_width(self):
    # Note IDs are ordered by decision time, then SATB part order.
    return sum(t == self.decision_times[0] for t in self.note_times)

  note_times: tuple = ()


def candidates(score, rules, domains, start, horizon=1, max_candidates=10_000):
  """Hold history, rhythm, S/B and key fixed; hide unresolved future A/T."""
  if horizon < 1:
    raise ValueError("Horizon must be positive")
  times = sorted({n.onset for n in score.notes if n.voice in (Voice.A, Voice.T) and n.onset >= start})
  if not times or times[0] != start or len(times) < horizon:
    raise ValueError("Start/horizon must identify available inner-voice decisions")
  chosen_times = tuple(times[:horizon])
  stop = times[horizon] if len(times) > horizon else max(n.offset for n in score.notes)
  targets = sorted((n for n in score.notes if n.voice in (Voice.A, Voice.T) and n.onset in chosen_times),
                   key=lambda n: (n.onset, n.voice.value))
  pools = [tuple(domains.get(n.voice, ())) for n in targets]
  if any(not p or len(set(p)) != len(p) for p in pools):
    raise ValueError("Every attacking inner voice needs a nonempty, duplicate-free pitch domain")
  size = prod(map(len, pools))
  if size > max_candidates:
    raise ValueError(f"Exact enumeration needs {size} candidates; limit is {max_candidates}")
  gold_choice = tuple(n.pitch for n in targets)
  if any(n.pitch not in pool for n, pool in zip(targets, pools)):
    raise CoverageError("Observed pitches fall outside the declared candidate domain")
  choices, rows = tuple(product(*pools)), []
  for choice in choices:
    replacements = dict(zip((n.id for n in targets), choice))
    # Physically remove unresolved future inner pitches, in addition to the
    # half-open scoring window. Outer voices are supplied conditioning data.
    notes = tuple(replace(n, pitch=replacements[n.id]) if n.id in replacements else n for n in score.notes
                  if n.voice not in (Voice.A, Voice.T) or n.onset < stop)
    candidate = replace(score, notes=notes)
    result = evaluate(rules, candidate, start=start, stop=stop, trace=False)
    rows.append([result.totals[r.id] for r in rules])
  return CandidateTable(choices, np.asarray(rows, dtype=float), choices.index(gold_choice),
                        tuple(r.id for r in rules), tuple(n.id for n in targets),
                        chosen_times, stop, tuple(n.onset for n in targets))


def objective(weights, tables, regularization):
  loss, gradient = 0.0, np.zeros_like(weights)
  for table in tables:
    logp = table.log_probabilities(weights)
    loss -= logp[table.gold]
    gradient += table.features[table.gold] - np.exp(logp) @ table.features
  loss = loss / len(tables) + regularization * np.dot(weights, weights) / 2
  gradient = gradient / len(tables) + regularization * weights
  return float(loss), gradient


def fit(tables, regularization=0.1, nonnegative=True):
  """Fit on caller-supplied training tables only; no split inference."""
  tables = tuple(tables)
  if not tables or regularization <= 0 or not np.isfinite(regularization):
    raise ValueError("Training tables and positive finite regularization are required")
  identities = tables[0].rule_ids
  if any(t.rule_ids != identities for t in tables):
    raise ValueError("All tables must use the same ordered rule inventory")
  bounds = [(0, None)] * len(identities) if nonnegative else None
  result = minimize(objective, np.zeros(len(identities)), args=(tables, regularization),
                    jac=True, method="L-BFGS-B", bounds=bounds)
  if not result.success:
    raise RuntimeError(f"Weight fitting failed: {result.message}")
  return result.x


def load_weights(path, rules_path, rules):
  model = json.loads(Path(path).read_text())
  if model["rules_sha256"] != sha256(Path(rules_path).read_bytes()).hexdigest():
    raise ValueError("Rule file does not match fitted model")
  if set(model["rule_weights"]) != {r.id for r in rules}:
    raise ValueError("Fitted model has a different rule inventory")
  weights = np.asarray([model["rule_weights"][r.id] for r in rules], dtype=float)
  if not np.isfinite(weights).all():
    raise ValueError("Fitted weights must be finite")
  return weights
