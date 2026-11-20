# First Bach pilot — 2026-11-15

**The machinery runs on real chorales. This is not yet a reliable estimate of
musical prediction quality.** No API calls were used.

Training: one two-decision window each from BWV 269 and BWV 347. Development:
one window each from BWV 153.1 and BWV 86.6. The source files are bundled with
music21; [the manifest](../experiments/bach-pilot.json) pins their hashes and
declared keys. The first eligible window in each piece is selected by rhythm
alone: one inner voice attacks at each of two consecutive decisions, after the
initial event. This keeps exact two-event enumeration tractable without changing
the candidate domains after seeing the gold notes.

Alto candidates span C3–G5; tenor candidates span C2–C5. Include every natural,
single-flat and single-sharp spelling within these sounding bounds: 56 alto and
65 tenor possibilities. These broad domains intentionally retain bad ranges,
crossings and chromatic choices. Enharmonic spellings are separate candidates.
All eight windows (four pieces × two horizons) include the gold completion.
Joint two-event windows contain 3,136–4,225 candidates, all scored exactly.

## Results

Mean negative log probability of Bach's **first choice**, in natural-log units;
lower is better. Both horizons use the same development starts. Two-event values
sum over all possible second choices; they do not condition on Bach's next note.

| Model | One-event prediction | Two-event first-choice marginal |
|---|---:|---:|
| Uniform guessing | 4.100 | 4.100 |
| Learned pitch frequencies | 3.423 | 3.235 |
| Handwritten seed rules, fitted weights | 3.249 | 3.110 |
| Learned preference for smaller melodic movement | **2.450** | **2.470** |

Each horizon is fitted independently on its training windows. Seed and melodic
models use nonnegative weights with L2 coefficient 0.1. The pitch baseline uses
add-one smoothing on the same training target slots. Horizon two thus sees more
training target slots than horizon one; the comparison does not isolate lookahead
from differences in training objective/data. No development-based tuning occurred.

The seed rules beat uniform guessing on these examples, but the simpler melodic
baseline does better. This is a useful diagnostic, not evidence that the seed
inventory is good or that one horizon is superior.

## Concrete musical examples

These are probabilities of the exact spelled note, not just its sounding pitch.

| Development passage | Bach's choice | Uniform | One-event seed rules | One-event melodic baseline | Two-event seed rules |
|---|---|---:|---:|---:|---:|
| BWV 153.1, tenor after G♯3; soprano C5, bass E3 | A3 | 1.54% | 3.92% | 8.25% | 4.78% |
| BWV 86.6, alto after E4; soprano B4, bass B2 | D♯4 | 1.79% | 3.85% | 9.03% | 4.16% |

The one-event seed model ties Bach's note with 20 other tenor choices in the
first example and 22 other alto choices in the second. Saying that Bach is
"ranked first" would obscure how little these rules discriminate. The melodic
baseline instead favors staying on the previous pitch; it raises Bach's
probability because Bach moves by only one semitone in these examples.

## Limits and next work

There are only two development observations, selected for an unusual rhythmic
configuration. Pieces are separate, but tune-family grouping has not been
audited. Supplied S/B, rhythm, spelling domains and global keys are conditioning
information. This is not free composition, figured-bass realization, or a
population benchmark. No final held-out test set has been opened.

Next: expand training/development with tune-aware grouping, include simultaneous
A/T decisions, measure coverage and runtime, and compare stronger interpretable
rules against these baselines. For a controlled horizon comparison, match the
training target coverage as well as development starts. Then enable bounded
model proposals with durable accounting. Do not infer that zero fitted weight
here means a rule is musically unimportant.

## Reproduce or inspect

```sh
python -m harmonizer.attack.pilot --output artifacts/bach-pilot.json
```

The pilot took about 20 seconds in the development workspace. GitHub Actions
runs it and saves the full JSON report in the `attack-reports` artifact, with
domains, windows, weights, probabilities, ties, hashes and limitations. Ordinary
users do not need to install or run anything to review this summary.
