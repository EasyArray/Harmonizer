# Attack DSL prototype

This branch adds a small experimental implementation alongside the original
notebook tools. Start with [the seven seed rules](../rules/seed.harmony).
They are handwritten hypotheses, not discoveries. The older API is unchanged.

**Latest results:** [60-chorale architecture comparison](expanded-development.md).
See [current status](project-status.md) for the completed Astra proposal call
and its offline evaluation. The first 15-chorale experiment is preserved in
[round 001](discovery-round-001.md).

## Run without installing anything on your computer

Open the repository's **Actions → Attack DSL prototype** workflow. Each branch
push and pull request runs the tests and a synthetic probability/fitting demo.
The run's `attack-reports` artifact contains JSON reports for the synthetic demo
and the [small Bach pilot](bach-pilot-results.md). These jobs use no API
keys and make no model calls. The manual trigger becomes visible once the
workflow is on the default branch; branch pushes run it before then.

For a development environment:

```sh
python -m pip install -e '.[dev,experiment]'
python -m pytest -q
python -m harmonizer.attack.cli validate
python -m harmonizer.attack.cli demo --output artifacts/attack-demo.json
python -m harmonizer.attack.pilot --output artifacts/bach-pilot.json
python -m harmonizer.attack.cli score --score chorale.musicxml --tonic C4 --mode minor
python -m harmonizer.attack.cli predict --score chorale.musicxml --tonic C4 --mode minor --start 1 --horizon 2 --alto C4,Eb4,G4 --tenor C3,Eb3,G3
```

The last command's domains are illustrative. A scientific experiment must
declare broad spelling/pitch domains before inspecting target notes. An
unrepresentable gold note fails explicitly. Prediction uses unit weights for
inspection; the Python `fit` function learns weights from training tables.

## Whole language at a glance

```text
At attack n:
  Rule "Large leaps":
    let leap = distance(n.previous, n)
    if leap > 7:
      penalty leap - 7

At tenor attack t:
  Rule "Low tenor":
    if t is below C3:
      penalty distance(t, C3)

At attack (upper, lower):
  Rule "Crossing":
    if upper is below lower:
      penalty 1

At attack n1 while n2 holds:
  Rule "Crossing with a hold":
    if n1.voice is above n2.voice and n1 is below n2:
      penalty 1
    if n2.voice is above n1.voice and n2 is below n1:
      penalty 1

At figure f:
  Rule "Wide inner voices":
    if distance(T at f, A at f) > 12:
      penalty 1
```

| Data/logic | Meaning |
|---|---|
| `n.previous`, chained | Prior articulated note in that voice; stops at rests |
| `n.voice` | S, A, T, B, ordered by part identity |
| `A at n`, `A before n`, `A attacks at n` | Sounding, just-before, and attack status at the anchor's own onset |
| `key.tonic`, `key.mode` | Explicitly supplied global key |
| `distance(x, y)` | Unsigned semitones |
| `interval(x, y)` | Spelled directional interval; `.steps` and `.semitones` are signed |
| `degree(n)` | Degree relative to tonic and major/natural-minor baseline |
| `P5`, `-P5`, `C4`, `F#4`, `#3`, `b7` | Interval, pitch, altered-degree literals |
| `is above`, `is below` | Pitch height, or part order for voice identities |
| `== != < <= > >=`, `and or not` | Comparisons and conditions; parentheses clarify scope |
| `+ - * /`, `let`, nested/sibling `if`, `penalty` | Numeric contributions with immutable local names |

No loops, quantifiers, `else`, arbitrary Python, or user-defined functions.
Use two-space indentation and double-quoted rule titles. A condition can span
lines until its final colon. `//` comments occupy their own lines. Each named
rule has its own weight; every reached penalty within that rule adds to its
feature. Negative contributions are allowed. Pair bindings use SATB order even
during crossings. Arbitrary lowercase binding names work, with the first pair
slot always the nominally upper part (a small generalization of the design).

Missing notes propagate as unknown: a dependent branch is skipped and traced,
while independent siblings continue. `not unknown` remains unknown. A known
false conjunct or true disjunct determines its condition. Invalid types,
division by zero, and nonfinite values fail rather than becoming skips.

## Probability and timing contract

`candidates` enumerates the full Cartesian product for all A/T attacks in a
selected horizon. It leaves held notes, prior history, rhythm, S/B, and global
key fixed. Unresolved future A/T attacks are removed from candidate scores.
Features include every relevant event from the first decision up to, excluding,
the next unresolved inner decision; this includes intervening S/B and figures.
At the end of a score, the window ends at the final note offset.

`P(candidate) = exp(-weights · features) / sum(exp(-weights · features))`.
Normalization uses log-sum-exp. Two-event prediction normalizes over complete
pairs, and its first-choice marginal sums over second choices. It is not two
successive one-event predictions. Exact enumeration stops at 10,000 candidates
by default; it never silently switches to a beam or sampled denominator.

Fitting minimizes mean conditional negative log likelihood plus L2/2. The
implementation default is nonnegative weights and L2 coefficient 0.1; signed
weights are available through `fit(..., nonnegative=False)`. This is an explicit
implementation choice, not a settled research conclusion. Constant features
are reported. Gold rank is optimistic among exact ties, with tie count shown.
Joint-window NLL is not directly comparable to one-event NLL; compare first-choice
marginals or report per-decision joint NLL with its distinct conditioning.

## What is and is not ready

- Ready: parser/interpreter, five triggers, strict four-part music21/MusicXML
  import, tie merging, rational time, seed rules, exact candidate tables,
  normalization, first-choice marginals, regularized fitting, traces and CI.
- The demo fits on two synthetic pieces and evaluates a third. It tests software
  plumbing only. It is not a Bach benchmark or evidence for the seed rules.
- MusicXML parts must be SATB in order (the Python importer accepts an explicit
  mapping). Chords inside parts, broken ties, grace notes and microtones fail.
- MusicXML figure import/content interpretation is not implemented. Figure
  triggers work on explicitly constructed `Figure` objects. The source XML
  remains authoritative for notation/key signatures; the compact model does not
  yet retain all notation metadata.
- Traces record bindings, expression, line, contribution or skip reason, but
  do not yet capture every intermediate measurement. Rule IDs survive title
  changes, but are not a semantic-equivalence hash.
- The expanded benchmark now includes 15 pieces, title/fingerprint split guards,
  learned baselines, saved fitted models, and a development-only proposal round.
  A bounded OpenAI adapter and durable ledger are implemented. Still needed:
  broader tune-family auditing, corpus-scale evaluation, a U-M adapter, and
  independent final testing. Never expose a final test split to a proposal model.

## Credentials and approved budget

U-M Toolkit is the first cloud-test provider; `UM_TOOLKIT_API_KEY` is already
reported as installed in GitHub Actions secrets. The user reports a $25 monthly
provider quota. **The initial project ceiling is $10 total across providers**,
not $10 per run or key. A separate OpenAI development key may live in an ignored
workspace env file. Keys must never enter source, artifacts, logs or chat.

The first bounded OpenAI request is complete; the conservative ledger accounts
$0.005758. [API experiment instructions](api-experiments.md) describe reservations,
pricing, single-use tickets and response checkpoints. Unknown charges remain
reserved. A missing ledger, stale prices or unpriced model stops paid work.
CI, scoring and fitting remain offline; they do not use the API.

## Next reproducible milestone

Expand the pinned pilot to tune-aware splits and simultaneous A/T decisions.
Keep declared domains and global-key provenance, audit coverage, fit on training
only, and compare first-choice probabilities on development. Match training
coverage when isolating horizon effects. A final held-out test remains untouched
during discovery. Live proposals still require durable spending controls.

## A shared rule for selected voices

```
At alto or tenor attack n:
  Rule "Inner-voice spacing":
    if distance((T at n), (A at n)) > 12:
      penalty 1
```

This binds one note at a time: either an alto attack or a tenor attack.
When both attack, it runs twice. It does not bind two notes or require
coincident attacks. Use separate alto/tenor rules when separate fitted weights
are wanted; this shorthand shares one weight. Voice order in the header does
not matter; repeated voices are rejected. Existing rule identities are unchanged.

## Key labels need review

Encoded MusicXML keys are not verified analytical tonics. In the first fifteen
pieces, a soprano/bass-only key estimator disagreed with five encoded labels.
Neither source is treated as ground truth. The leading-tone result is provisional.
The key-independent selection policy excludes that proposal from the default
model; the original experiment and fitted inventories remain reproducible.

## Sounding-pitch predicates used in the foundations experiment

`in_scale(n)` accepts a note or pitch. Its sounding pitch class must occur in
the supplied global major or natural-minor scale. Enharmonic spellings agree.

`dissonant(n, m)` accepts two notes. Reduce their absolute semitone distance
modulo 12. Unisons/octaves, thirds, fifths and sixths count as consonant.
A fourth counts as dissonant when either note belongs to the bass part.
This is a deliberately coarse two-note predicate. A silent voice yields a
missing value and skips that comparison. See [the rulebook](../rules/foundations.harmony).
