# Five basic harmony preferences in Bach chorale completion

On 20 development chorales, the five preferences together multiplied the probability
of Bach’s sounding choice by **11.82** relative to a uniform distribution over written
candidates (95% paired family-bootstrap interval **9.62–14.40**). The probability
improved in all 20 pieces. Gains are geometric means, so doubling the probability
has the same value whether it starts at 1% or 10%.

| Family | Probability multiplier on its own | Multiplier from adding it to the other four | Written alternatives strictly outranked on its own |
|---|---:|---:|---:|
| Alto and tenor range | 2.07× | 1.013× | 55.4% |
| Smaller melodic motion | 5.49× | 1.725× | 90.9% |
| Additional cost beyond a perfect fifth | 2.91× | 0.990× | 69.0% |
| Global diatonicity | 1.36× | 1.171× | 38.7% |
| Consonance with the outer voices | 1.84× | 1.604× | 60.0% |

The standalone column compares each fitted family with uniform. For the second
column, the full and four-family inventories each get their own training fit.
For the separate large-leap penalty the incremental 95% interval spans 1
(0.95–1.02×). The data distinguish a general preference for small motion much
more clearly than a change in slope at seven semitones. The range-only model
ties Bach with 44.6% of written competitors and beats the rest, which captures
exactly what a broad filter can accomplish even when it cannot select a winner.

| What is predicted | Decisions | Bach’s sounding probability under uniform | With five families | Distinct sounding alternatives strictly outranked with five families |
|---|---:|---:|---:|---:|
| One attacking inner voice | 60 | 2.57% | 7.84% | 89.2% |
| Both inner voices together | 60 | 0.077% | 3.52% | 99.0% |

The full model outranks 94.1% of distinct sounding alternatives across events,
or 94.5% of written alternatives. Ties earn zero wins. Mean written negative
log probability falls from 6.150 (uniform) to 3.680. Round two’s full proposal
model scored 4.275 and its simple written pitch-frequency baseline scored 4.171
on these same events. The new inventory thus gives Bach’s written choice
about 1.81× the probability of the previous proposal model. Both experiments
reuse the development set, so this comparison is exploratory.

## Two adjacent decisions from BWV 86.6

These are the first joint and single decisions from a development piece that
passed the key screen, selected in manifest order. At time 1 (quarter notes
from the start), the soprano sounds B4 and the bass D♯3. The alto moves down
from G♯4 to F♯4 and the tenor moves up from E4 to the same F♯4. The model
assigns Bach’s sounding pair **6.46%**, against **0.11%** under uniform and
**1.93%** with the consonance family removed and the other weights refitted.

Half a beat later, the outer notes still sound and the tenor holds F♯4.
Bach moves the alto to G♯4, a compound fourth above D♯3. The full model
gives G♯4 **6.98%**, down from **13.88%** with consonance removed.
Across development, consonance raises joint-attack probability from 1.22%
to 3.52% while lowering single-attack probability from 8.79% to 7.84%.
This suggests testing whether the weight should depend on rhythmic or
contrapuntal context. These events alone cannot identify the explanation.

## What was scored

- Given S/B, the attack schedule, and the observed preceding inner notes,
  predict the next attacking A and/or T pitches. Use the same 40 training
  and 20 development settings, first/middle/last single and joint events,
  and fixed domains as round two. Coverage matched event by event:
  240 training and 120 development decisions, 666,297 written candidates,
  and every observed choice present.
- Soft range limits were G3–D5 (alto) and C3–G4 (tenor), charged per semitone
  outside. Motion costs one unit per semitone from the contiguous previous
  note. Both families fit separate voice weights. The leap family adds one
  unit per semitone beyond seven, shared across A/T.
- Diatonicity charges one unit per attacking note outside the sounding pitch
  classes of the global major or natural-minor scale. This counts the raised
  seventh in minor as outside. The family was active only when the encoded
  and outer-voice key estimates agreed and the final bass sounded the tonic
  (28/40 training and 15/20 development chorales). All five families used
  identical windows. On the eligible development pieces, diatonicity alone
  gave 1.51× uniform. The screen checks global labels and cannot verify a
  passage’s local key.
- Consonance checks each attacking inner note against each sounding outer
  voice, including held notes; silence contributes zero. Unison/octave,
  thirds, fifth and sixths are consonant. A perfect fourth is consonant
  between upper voices and costs one when the bass part is involved.
  Seconds, sevenths and tritones cost one per pair. Classification uses
  absolute semitone distance modulo twelve, ignoring spelling and treating
  the named bass part as bass even if voices cross.
- Normalize exponentials of negative weighted penalties over every written
  choice. Fit nonnegative weights on training data with the existing L2
  coefficient of 0.1. Single and joint attacks each count as one decision.
  Sum probability across enharmonic spellings for the sounding measure.
  Multiple spellings can give a sound more mass even under written uniform.
  All five families ignore spelling, so written and sounding probability
  *multipliers* agree exactly against that baseline.
- Average log probabilities within pieces, then equally over pieces. Rank
  measures compare Bach against all other choices at the event, with a
  log-probability tie tolerance of 1e−10. Intervals resample whole development
  families in pairs across models, using the existing 2,000-replicate
  bootstrap. They do not adjust for reuse of development data.

## Reproduce and inspect

From the repository root in the experiment environment, run
`OPENBLAS_NUM_THREADS=1 python -m harmonizer.attack.foundations`.
The run checks corpus hashes, round-two coverage and the uniform and melodic
controls. The fixed inventory is additive across attacking voices, so the
runner evaluates its DSL rules once per pitch per voice and adds the rows for
joint attacks. Regression tests compare those features to direct joint
enumeration. Changed rulebooks use direct enumeration.

[Seven readable rules in five families](../rules/foundations.harmony) ·
[Scoring and fitting](../harmonizer/attack/foundations.py) ·
[All fitted weights, comparisons, examples and per-piece results](../experiments/results/foundations.json)
