# Expanded development and architecture report

**Development evidence, not a final test.** Lower negative log likelihood (NLL) is better.
A gain of 0.10 nats means roughly 10.5% higher geometric probability for the observed completion.

- Chorales: 40 training, 20 development.
- Decisions: 360; enumerated candidates: 666,297.
- Gold-domain coverage: 360/360. Unsupported imports are listed below.
- Key-label disagreements (encoded versus S/B-only estimate): 12/60. Neither label is treated as verified truth.
- Fixed S/B, rhythm and prior inner notes; exact one-event prediction. No rhythm generation or figured-bass data.
- Rules from round 001 are being retested. Spacing-count and separate-weight controls are handwritten architectural comparisons.
- The new voices shorthand shares a weight. Separate alto/tenor rules allow different fitted weights.

| Model | Piece NLL | Gain vs seed+melodic | 95% family-bootstrap interval | Pieces improved |
|---|---:|---:|---:|---:|
| uniform | 6.1498 | -1.7793 | [-1.9601, -1.5825] | 0/20 |
| pitch | 4.1706 | +0.2000 | [-0.1461, +0.5434] | 12/20 |
| seed | 4.7732 | -0.4027 | [-0.5494, -0.2582] | 2/20 |
| melodic | 4.4461 | -0.0756 | [-0.1144, -0.0368] | 5/20 |
| seed+melodic | 4.3705 | +0.0000 | [+0.0000, +0.0000] | 0/20 |
| spacing-shared | 4.3403 | +0.0302 | [+0.0178, +0.0461] | 19/20 |
| leading-tone | 4.3623 | +0.0082 | [+0.0020, +0.0149] | 8/20 |
| parallel-octaves | 4.3704 | +0.0002 | [+0.0001, +0.0003] | 16/20 |
| spacing+leading | 4.3321 | +0.0384 | [+0.0231, +0.0572] | 19/20 |
| all-original-proposals | 4.3319 | +0.0386 | [+0.0232, +0.0574] | 19/20 |
| spacing-once | 4.3538 | +0.0167 | [+0.0104, +0.0243] | 19/20 |
| spacing-separate | 4.3501 | +0.0204 | [+0.0123, +0.0307] | 19/20 |

Intervals describe sampling variation in these development families, not uncertainty from repeated model selection.
A result whose interval crosses zero is not clearly distinguished on this sample.

## Architecture decisions exposed by this run

### One harmonic observation or two note-triggered penalties?

The original spacing rule contributes twice when alto and tenor both attack.
The once-per-event variant suppresses the tenor contribution when alto also attacks.
The separate-weights variant retains note counting but fits alto and tenor independently.
All three use exactly the same candidate completions and training/development split.

**Comparison caveat:** all fits use the same L2 coefficient, but changing feature
scale or splitting one weight into two changes the effective regularization.
These results support retaining the simple shared rule provisionally; they do
not settle which event-counting convention is intrinsically better. A follow-up
comparison should match regularization or select it using training data only.

- **spacing-shared:** NLL 4.3403; fitted spacing weights Inner-voice spacing=0.395.
- **spacing-once:** NLL 4.3538; fitted spacing weights Spacing counted once per event=0.338.
- **spacing-separate:** NLL 4.3501; fitted spacing weights Spacing at alto attacks=0.222, Spacing at tenor attacks=0.266.

### Enharmonic candidates

Generation still distinguishes spellings. The sounding-pitch metric below sums their probabilities before scoring.
It diagnoses the spelling burden; it is not a deduplicated generator or an equivalent comparison task.

| Model | Exact-spelling NLL | Sounding-pitch NLL | Geometric spelling probability given sound |
|---|---:|---:|---:|
| seed+melodic | 4.3705 | 3.6370 | 48.0% |
| spacing-shared | 4.3403 | 3.6067 | 48.0% |
| spacing-once | 4.3538 | 3.6203 | 48.0% |
| spacing-separate | 4.3501 | 3.6165 | 48.0% |

### Key input sensitivity

Weights are refitted on training data after replacing encoded keys by an estimate based only on supplied S/B.
Candidate pitches and all key-independent features are unchanged. This does not decide which labels are correct.

| Model | Encoded-key NLL | Outer-estimate NLL |
|---|---:|---:|
| spacing-shared | 4.3403 | 4.3403 |
| leading-tone | 4.3623 | 4.3643 |
| spacing+leading | 4.3321 | 4.3341 |

### Previously inspected versus newly added development chorales

These are descriptive strata, not a newly sealed test set.

| Model | Previous five-piece subset | Added development pieces |
|---|---:|---:|
| uniform | 6.1523 | 6.1490 |
| pitch | 4.3168 | 4.1218 |
| seed | 4.8175 | 4.7585 |
| melodic | 4.1667 | 4.5393 |
| seed+melodic | 4.1424 | 4.4466 |
| spacing-shared | 4.0975 | 4.4212 |
| leading-tone | 4.1246 | 4.4416 |
| parallel-octaves | 4.1420 | 4.4465 |
| spacing+leading | 4.0797 | 4.4162 |
| all-original-proposals | 4.0793 | 4.4161 |
| spacing-once | 4.1211 | 4.4314 |
| spacing-separate | 4.1126 | 4.4293 |

### Where the shared spacing rule helps and hurts

Times are exact quarter-note offsets in the source score. A/T pairs are in part order.
The top candidate is illustrative; probability of Bach's completion is the evaluated quantity.

| Source / time | Bach target | Sounding S / A / T / B | Probability before → after | Top choice after |
|---|---|---|---:|---|
| bach/bwv40.8.mxl / 151/2 | Ab4 | F5 / Ab4 / F3 / Bb3 | 5.207% → 4.986% | A#4 |
| bach/bwv259.mxl / 1 | B3, G3 | E4 / B3 / G3 / G3 | 2.345% → 2.248% | B3, G3 |
| bach/bwv308.mxl / 1 | F4, D4 | Bb4 / F4 / D4 / Bb2 | 1.664% → 1.596% | E#4, D4 |
| bach/bwv245.11.mxl / 21 | G#4, E4 | B4 / G#4 / E4 / E3 | 0.054% → 0.071% | A4, A3 |
| bach/bwv153.1.mxl / 39 | E4, G#3 | B4 / E4 / G#3 / E3 | 0.106% → 0.176% | A4, F#3 |
| bach/bwv86.6.mxl / 19 | A#4, F#4 | C#5 / A#4 / F#4 / F#3 | 0.001% → 0.003% | B4, F#3 |

### Rules with no discriminatory training evidence

- Continuing upward after a large upward leap
- Wide inner voices at figure onset

A zero-activity rule cannot be assessed on these windows. In particular, absent figures do not test figured-bass rules.

## Exclusions and remaining limits

- bach/bwv41.6.mxl: Exactly four SATB parts required
- bach/bwv8.6.mxl: Exactly four SATB parts required
- bach/bwv248.9-1.mxl: Exactly four SATB parts required
- bach/bwv91.6.mxl: Exactly four SATB parts required

Connected components of normalized titles, transposition-invariant full soprano sequences, and content hashes. Old train/development assignments preserved. New families assigned development iff smallest Riemenschneider number is divisible by three. Related variants may remain undetected.
A few decisions per chorale still under-sample recoveries and cadences. Whole-piece quality remains untested.
Measured experiment time: 17.9 minutes. Model-proposal API spending is recorded separately in api-ledger.json.
