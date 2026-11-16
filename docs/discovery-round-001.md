# First complete proposal-and-evaluation cycle

November 16, 2026. **The full pipeline now works:** a bounded model request
proposes readable rules, the parser validates them, deterministic code fits
their weights on training data, and development results select a provisional
inventory that can be loaded for prediction. No further account setup is needed.

## What was evaluated

- 15 chorales: ten training pieces and five development pieces.
- Six rhythm-selected decisions per piece: three single inner-voice attacks and
  three simultaneous A/T attacks, at first/middle/last eligible positions.
- 60 training decisions, 30 development decisions; 166,581 candidate completions
  enumerated exactly. Every gold completion was covered.
- Same fixed domains throughout: 56 spelled alto pitches, 65 tenor pitches;
  simultaneous decisions have 3,640 alternatives. Chromatic and out-of-range
  choices remain possible rather than being excluded by the stylistic rules.
- Supplied soprano/bass, rhythm, past inner pitches and encoded global key.
- First 16 Riemenschneider entries from music21; BWV 41.6 is explicitly excluded
  because its encoding does not satisfy the four-part importer.
- Split guards use normalized titles and exact transposition-invariant soprano
  fingerprints. No matching groups cross splits. These checks do not detect
  every possible tune variant. Previously inspected pieces stay in development.

The manifest, source hashes, selection policies, saved model response, usage
ledger and fitted weights are committed. No final test set has been opened.

## Main comparison

Mean negative log probability of Bach's observed choice, averaged equally by
chorale (lower is better). A joint A/T choice is one decision. The development
sample has the same number of decisions per piece, so decision- and piece-level
means happen to agree.

| Model | Mean NLL |
|---|---:|
| Uniform guessing | 6.1523 |
| Learned pitch frequencies | 4.7063 |
| Original seed rules alone | 4.8172 |
| Learned melodic-distance baseline | 4.1599 |
| Seeds + melodic baseline (reference) | 4.1420 |
| Reference + proposed spacing rule | 4.1000 |
| Reference + proposed leading-tone rule | 4.0871 |
| Reference + proposed octave rule | 4.1414 |
| Reference + all three proposals | 4.0449 |
| Reference + spacing and leading-tone rules | **4.0454** |

The two-rule addition raises Bach's probability by a **geometric mean factor of
1.101**, about 10.1%, relative to the reference model. It helps on four of the
five development pieces. This is a relative probability improvement, not a
10-point accuracy increase or a claim that Bach is usually the top choice.
The resulting geometric mean gold probability is only about 1.75%; some
individual choices still receive extremely low probabilities.

The original frozen policy compared singles and all three together, requiring
at least 0.02 nats improvement and wins on at least 60% of development pieces.
It selected all three. After seeing the octave rule's very small contribution,
an explicitly exploratory pairwise ablation found that omitting it costs only
0.00056 nats. The simpler two-rule addition is therefore the provisional model.
Both the original result and the subsequent pruning policy are preserved; this
is disclosed development-set tuning, not independent confirmation.

## The two retained proposals

```text
At attack n:
  Rule "Inner-voice spacing":
    if n.voice == A or n.voice == T:
      if distance((T at n), (A at n)) > 12:
        penalty 1

At attack n:
  Rule "Inner leading-tone resolution":
    if n.voice == A or n.voice == T:
      if key.mode == "major" and degree(n.previous) == 7:
        if degree(n) != 1:
          penalty 1
      if key.mode == "minor" and degree(n.previous) == #7:
        if degree(n) != 1:
          penalty 1
```

Their fitted weights are about 0.360 and 0.499 respectively. They complement the
seed and melodic rules; they are not a complete harmonization grammar.

Limitations deliberately retained and tested:

- The spacing rule counts twice when A and T both attack. Its single weight
  therefore imposes a fixed relationship between single and joint attacks.
- The leading-tone rule uses global degree, accepts a tonic in any octave, and
  penalizes a repeated leading tone. It does not mean “resolve upward by a
  semitone at the next appropriate harmonic opportunity.”
- The discarded octave proposal only checks exact positive octaves, with no
  compound-interval or crossed-voice case.
- Several seed features are constant or inactive in this small training sample;
  a zero weight here is not evidence of musical unimportance.

## Examples, including a failure

These probabilities concern the complete spelled A/T choice at the indicated
quarter-note offset, not each note separately.

| Passage | Bach's choice | Reference probability | With the two proposals |
|---|---|---:|---:|
| BWV 153.1, offset 39 | Alto A4→E4; tenor F♯3→G♯3 | 0.1044% | 0.1680% |
| BWV 311, offset 35 | Alto A♯4→B4; tenor E4→F♯4 | 0.5337% | 0.8352% |
| BWV 65.2, offset 46 | Alto E4→E4; tenor B3→C♯4 | 0.6088% | 0.5738% |

The last case becomes worse: the global leading-tone tendency is too crude for
some actual contexts. This is precisely why the software measures probabilities
and development losses rather than declaring all textbook rules correct.

## Use the fitted model

The small model file is [round-001-pruned.json](../experiments/models/round-001-pruned.json).
Its matching readable inventory is [round-001-pruned.harmony](../rules/learned/round-001-pruned.harmony).
The CLI's `predict` command accepts `--weights` and verifies the rule-file hash.
A local prediction loaded from these files reproduced the benchmark probability.

For developer reproduction (the user need not run these):

```sh
OPENBLAS_NUM_THREADS=1 python -m harmonizer.attack.benchmark --proposals rules/proposals/round-001.harmony --pairs
python -m harmonizer.attack.select_model
python -m harmonizer.attack.select_model --policy experiments/pruning-policy.json --rules-output rules/learned/round-001-pruned.harmony --model-output experiments/models/round-001-pruned.json
```

GitHub's **Bach development experiment** workflow runs the offline benchmark and
exports both models. **Attack DSL prototype** runs the tests and smaller smoke
pilots. Neither workflow receives a model API key or makes paid requests.

## Spending and implementation checks

One GPT-6.1 Terra request, low reasoning, produced three syntactically valid
rules. Usage: 1,025 input tokens and 639 output tokens, including 314 reasoning
tokens. Estimated standard token cost is **$0.00422**; the conservative ledger
accounts **$0.005758**, less than one cent of the $10 total ceiling. No U-M API
requests were made. The prompt and full response are saved for replay.

There are 49 passing local tests, including accounting failures, single-use
request handling, saved-response replay, split guards, feature caching, model
selection and fitted-weight validation. A report serialization failure was
fixed with a regression test; cached features allowed recovery without repeating
the expensive scoring or the paid request.

The current evidence remains exploratory: 30 development decisions from five
pieces, several candidate inventories compared, and no independent final test.
The next scientific questions are whether the improvement survives broader
sampling and whether more precise versions of these rules improve probabilities
without sacrificing readability. The completed software and saved model make
those experiments possible; no additional human setup is required.
