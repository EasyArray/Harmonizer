# round-002: proposal evaluation

Development evidence only; no final test data. Lower NLL is better.

The reference includes the original seed rules, melodic-motion baselines and the previously retained shared spacing rule. All weights are refitted on the same 40 training chorales; evaluation uses the same 20 development chorales.

| Inventory | Piece NLL | Gain over reference | 95% family-bootstrap interval |
|---|---:|---:|---:|
| uniform | 6.1498 | -1.8095 | [-1.9783, -1.6226] |
| pitch | 4.1706 | +0.1697 | [-0.1748, +0.5136] |
| seed | 4.7083 | -0.3680 | [-0.5085, -0.2290] |
| melodic | 4.4461 | -0.1058 | [-0.1458, -0.0673] |
| seed+melodic | 4.3403 | +0.0000 | [+0.0000, +0.0000] |
| base+proposal:Whole-tone melodic spelling | 4.2870 | +0.0533 | [+0.0500, +0.0567] |
| base+proposal:Overlap without crossing | 4.3374 | +0.0030 | [+0.0018, +0.0041] |
| base+proposal:Leaping into a held-note semitone | 4.3320 | +0.0083 | [+0.0067, +0.0099] |
| base+all-proposals | 4.2748 | +0.0655 | [+0.0611, +0.0698] |

Provisional selection under the pre-existing policy: **base+all-proposals**.
The current default model is not automatically replaced. Intervals do not account for repeated development-set selection.

## Actual model proposals

### Whole-tone melodic spelling

Major-second spelling may be preferred for whole-tone inner-voice motion, distinguishing enharmonic candidates that melodic distance treats identically without constraining repeated pitches or chromatic semitones.

```
At alto or tenor attack n:
  Rule "Whole-tone melodic spelling":
    let motion = interval(n.previous, n)
    if motion.semitones == 2 and motion.steps != 1:
      penalty 1
    if motion.semitones == -2 and motion.steps != -1:
      penalty 1
```

### Overlap without crossing

For simultaneously attacking voices that remain strictly ordered, entering the partner's previous register may weaken line independence in a way not captured by present-time crossing penalties.

```
At attack (upper, lower):
  Rule "Overlap without crossing":
    if upper.previous is above lower.previous and upper is above lower:
      if lower is above upper.previous:
        penalty 1
      if upper is below lower.previous:
        penalty 1
```

### Leaping into a held-note semitone

Approaching an exact semitone clash with a sustained voice by more than two semitones may be less typical than stepwise contact, irrespective of crossing and deliberately excluding repeated pitches and compound intervals.

```
At attack n1 while n2 holds:
  Rule "Leaping into a held-note semitone":
    if n1.voice == A or n1.voice == T:
      if distance(n1, n2) == 1 and distance(n1.previous, n1) > 2:
        penalty 1
```

## Discriminatory training support

- Large leaps: 240 training windows with differing candidate penalties.
- Continuing upward after a large upward leap: 0 training windows with differing candidate penalties.
- Tenor range: 203 training windows with differing candidate penalties.
- Crossing at simultaneous attacks: 169 training windows with differing candidate penalties.
- Parallel exact fifths: 48 training windows with differing candidate penalties.
- Crossing involving a held note: 146 training windows with differing candidate penalties.
- Wide inner voices at figure onset: 0 training windows with differing candidate penalties.
- Inner-voice spacing: 240 training windows with differing candidate penalties.
- Alto motion baseline: 157 training windows with differing candidate penalties.
- Tenor motion baseline: 203 training windows with differing candidate penalties.
- Whole-tone melodic spelling: 240 training windows with differing candidate penalties.
- Overlap without crossing: 142 training windows with differing candidate penalties.
- Leaping into a held-note semitone: 130 training windows with differing candidate penalties.

Complete observed-note coverage: 360/360 decisions.
Elapsed computation: 22.5 minutes. This evaluation made no API calls.
