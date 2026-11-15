# Harmony DSL and experiment plan

Version 0.1 — 2026-11-15
Owner: Ezra Keshet
Purpose: preserve the discussion sufficiently for a later implementation agent to continue without reconstructing it from chat.

## Implementation update — 2026-11-15

Subsequent decisions: reuse EasyArray/Harmonizer on `attack-dsl-prototype`; preserve
the original code. U-M Toolkit first, with an optional separate OpenAI development
key. The initial API ceiling is **$10 total across providers**; the user reports
a $25/month U-M quota. The core now exists; see [implementation status and usage](attack-prototype.md).
Section 9 below is the historical proposal, superseded by these decisions.

## 1. Status and priorities

The user accepted the latest DSL direction as good enough to begin, and accepted the staged evaluation approach: exact next-event prediction first, joint next-two-event prediction as the first substantive comparison, and longer horizons only after measuring benefits and cost.

This is a design record, not a claim that software exists. Sections 2–8 capture the working design. Explicitly labeled defaults fill gaps needed for implementation but are not independently ratified theoretical commitments. Section 9 contains new architecture recommendations awaiting selection. No repository, credentials, budgets, or paid runs have been created by this document.

Priorities:
- Readable by non-programmers.
- Small, simple prototype over maximal expressive coverage.
- General musical observations rather than atomic textbook prohibitions.
- Numerical, potentially graded rule contributions; not Boolean violations only.
- An extensible core, avoiding unrelated special-purpose syntax.
- Cloud execution; little or no installation on the user's computer.
- Bounded autonomous testing after one-time credential setup.
- Lightweight code, two-space indentation, match/case where appropriate.

The research goal is to discover interpretable regularities that make Bach's observed choices more probable among alternatives. Exact reproduction is not the primary criterion.

## 2. Score model

Initial target: monophonic SATB chorales, predicting inner-voice pitches with soprano and bass supplied.

Preserve:
- Spelled pitches, including octave; enharmonic spelling is not discarded.
- Voice identity S, A, T, B, ordered by part identity in that order.
- Exact rational musical onset/offset times, original note identifiers and tie relationships.
- Rests, note attacks versus continued sounding.
- Global tonic and mode with provenance.
- Actual notated key signature separately from the analytical global key.
- Figured-bass annotations, onset, literal content, and source provenance.
- Original notation for later extensions, without exposing every field in the prototype DSL.

Attack means a new articulated note. A repeated pitch attacks again. A tied continuation does not.
For navigation, a tie chain is one articulated note while source segments remain available internally.
At an event time, all simultaneous starts and endings must be resolved before evaluation. No dependence on voice processing order.

Implementation default: sounding spans are half-open [onset, offset). 'Before' is the state just before the event. A note ending at the event is available before it but not at it, unless a continuation/new note supplies the current sound.

Initially the inner-voice attack schedule, durations, ties and rests are supplied. This is pitch completion conditional on rhythm, not joint composition of pitch and rhythm.

## 3. Five trigger families

Trigger sections contain separately named rules:

~~~text
At attack n:
  Rule "Large leaps":
    let leap = distance(n.previous, n)
    if leap > 7:
      penalty leap - 7
~~~

1. Generic single attack:
~~~text
At attack n:
~~~
One match for each newly articulated note in any voice.

2. Voice-specific single attack:
~~~text
At tenor attack t:
~~~
Likewise soprano, alto and bass. One match when the named voice attacks.

3. Two simultaneous attacks:
~~~text
At attack (upper, lower):
~~~
Select each distinct pair of attacking voices once. Bind notes in SATB part order, not sounding pitch order. More than two voices may attack; that does not prevent a match. At a four-voice attack there are six matches.

For the prototype, upper/lower are the canonical role names in this form. A future grammar can allow arbitrary names with first slot = nominally upper part.

4. An attack against a held note:
~~~text
At attack n1 while n2 holds:
~~~
Bind each newly articulated note to each sounding, non-attacking note in another voice. n1 is always the attacker, n2 the held note; neither variable implies a higher part or pitch. Additional voices may attack. Rearticulated identical pitches do not count as held. If one voice attacks and three hold there are three matches. If all four attack there are none.

This final formulation supersedes separate 'upper attacks/lower holds' and 'lower attacks/upper holds' trigger forms.

5. Figure onset:
~~~text
At figure f:
~~~
One match per figured-bass annotation at its beginning. A stack of figures is one item, not a separate trigger per numeral. Figure parsing, implied tones, temporal resolutions and compatibility semantics remain to be designed.

The generic and voice-specific forms overlap intentionally: distinct rules can contribute in both. Both-attack and attack/hold pair matches are disjoint. No general loops, exists/all quantifiers, or arbitrary multi-trigger lists are included initially.

## 4. Rule identity, scope and accumulation

A named Rule is the unit with an independently fitted weight. Sharing a trigger section is organizational only; it does not tie weights of different rules.

Within one rule:
- let names an immutable local value.
- if can be nested.
- Multiple sibling if blocks are independent.
- Every reached penalty expression adds to that rule's score.
- Negative contributions are allowed.
- A false condition contributes zero.
- Do not infer an else-if chain.
- All contributions inside a rule share one fitted weight.

Thus conditions contributing +1 and -3 inside one rule have a fixed 1:-3 relative scaling. To learn independent importance, make them distinct rules.

No else, user-defined functions, recursion, arbitrary Python execution, or general aggregation is required for v0.1.

Implementation default: lexical block scope; trigger bindings visible throughout their section; locals do not leak between rules, bindings or events. Duplicate names in one scope should be rejected. Preserve a stable rule identifier independent of a cosmetic title.

## 5. Expressions

### Notes, voices and temporal access

- n.voice: voice identity.
- n.previous: preceding articulated note in the same voice.
- n.previous.previous: two notes back.
- A at n: alto note sounding when the anchor note begins.
- A before n: alto note immediately before that onset.
- A attacks at n: Boolean indicating an alto attack at that onset.
- Analogous S, T, B lookups; figure f may also be a time anchor.
- key.tonic and key.mode expose declared global context.
- n1 is above n2 / is below: sounding pitch-height comparison.
- n1.voice is above n2.voice / is below: SATB part-order comparison.

Important distinction: a held note's own onset is not the current evaluation event. Do not interpret 'A at n2' as 'A now' when n2 is a held-note binding. Use the attacking anchor n1, the triggering figure f, or an explicit evaluator event internally.

### Measurements

- distance(x, y): unsigned chromatic semitone distance, ignoring direction.
- interval(x, y): exact spelled directional interval from x to y.
- interval(...).semitones: signed chromatic displacement.
- interval(...).steps: signed diatonic letter transitions; C to D = 1, C to G = 4.
- degree(x): octave-independent degree relative to global tonic, with alteration relative to the global key's diatonic baseline.
- Named exact interval values include P1, m3, M3, P4, P5, P8, P12 and negative descending values.
- Exact P5 is not automatically octave-equivalent to P12.

A proposed optional extension, NOT part of the minimal required implementation, is simple(interval(...)): remove extra octaves while preserving spelling and direction. Precise unison/octave and chromatically altered-unison cases need definition before enabling it.

Pitch names such as C4 or F#4 may be supported as literals if needed; they were illustrative rather than central to the agreed first examples. Final lexer needs to distinguish pitch and interval tokens from identifiers.

### Scale-degree correction

The earlier major-relative convention was withdrawn because it did not fit the user's intended analogy with bass figures.

Working convention:
- Global tonic determines degree number.
- Major or natural-minor baseline, as appropriate to global mode, determines its unaltered pitch.
- Prefix # means one semitone above that baseline, b one below.
- In C minor: Eb = 3, E natural = #3, Bb = 7, B natural = #7.
- The degree calculation is independent of local candidate-dependent key inference.
- This relative alteration syntax is a normalized DSL convention, not a transcription of all historical figured-bass accidental practices.

### Operators and readability

Comparisons: ==, !=, <, <=, >, >=.
Logic: and, or, not; parentheses permitted.
Arithmetic: +, -, *, /; parentheses permitted.
Function calls delimit arguments: distance(x, y), interval(x, y), degree(x).

Do not initially expose max/abs just to require users to decode them: distance supplies unsigned distance and if can gate excess penalties.
Do not initially add English aliases such as distance(between x and y). They are possible sugar later, not necessary semantics.

Implementation default: conventional arithmetic precedence; comparison before not/and/or; not > and > or; disallow chained comparisons initially to avoid surprise. Multiline conditions continue until their terminating colon. Keywords may be case-insensitive to accommodate prose-style examples; ordinary identifiers remain case-sensitive.

## 6. Missing data and deterministic execution

Provisional convention from discussion:
- n.previous does not cross a rest.
- A required unavailable note skips the affected evaluation occurrence; skipped is not evidence of satisfaction.
- Missing history at a score boundary is not a failed resolution.
- All real-valued outputs must be finite.

Implementation recommendation requiring documentation: handle missing values at the penalty-branch level so that an unavailable value in one independent branch does not erase a valid sibling contribution. Use explicit internal missing/unknown propagation, ordinary short-circuiting where the result is already known, and trace skipped branches. Do not silently make 'not missing' true. Decide and test these details before scientific evaluation.

Type errors, nonfinite penalties, division by zero and invalid DSL are validation failures, not ordinary missing data.
Use a parser and typed AST/interpreter; never eval generated Python.

Each contribution trace should include rule ID, event time, bound note/source IDs, branch location, measurements, raw contribution, and skip reason if applicable.

## 7. Representative rules and counting

These are illustrative manually supplied hypotheses, NOT discovered rules.

~~~text
At attack n:
  Rule "Large leaps":
    let leap = distance(n.previous, n)
    if leap > 7:
      penalty leap - 7

  Rule "Continuing upward after a large upward leap":
    let previous = n.previous
    let earlier = previous.previous
    if previous is above earlier
      and distance(earlier, previous) > 7
      and n is above previous:
        penalty 1

At attack (upper, lower):
  Rule "Crossing at simultaneous attacks":
    if upper is below lower:
      penalty 1

  Rule "Parallel exact fifths":
    let previous = interval(lower.previous, upper.previous)
    let current = interval(lower, upper)
    if distance(upper.previous, upper) > 0:
      if previous == P5 and current == P5:
        penalty 1
      if previous == -P5 and current == -P5:
        penalty 1

At attack n1 while n2 holds:
  Rule "Crossing involving a held note":
    if n1.voice is above n2.voice
      and n1 is below n2:
        penalty 1
    if n2.voice is above n1.voice
      and n2 is below n1:
        penalty 1

At figure f:
  Rule "Wide inner voices at figure onset":
    let alto = A at f
    let tenor = T at f
    if distance(tenor, alto) > 12:
      penalty 1
~~~

For exact signed interval preservation, both voices have equal semitone displacement, so checking one nonzero displacement excludes stationary rearticulation. The two signs represent pitch ordering, not movement direction.

If interval comparison is octave-reduced, same-direction motion needs an additional check. Counterexample: C3/G4 -> D3/A3 has simple P5 at both ends but contrary motion.

Crossing is counted at relevant pair events, not only at the first entry into a crossing. Crossing in two-attack and attack/hold configurations is represented by separate rules and weights unless later explicitly tied. Generic melodic rules and voice-specific rules can coexist; assess redundancy when fitting.

Suggested semantic regression fixtures:
- All four voices attack: four generic single matches, six two-attack matches, no attack/hold matches.
- One attacks and three hold: one generic single match, zero two-attack matches, three attack/hold matches.
- Two attack and two hold: two generic singles, one two-attack pair, four attack/hold pairs.
- Repeated pitches attack; tied continuation does not.
- Voice ordering is unchanged by crossing.
- Simultaneous processing order does not affect results.
- Nested and sibling penalties accumulate correctly.
- Exact fifths exclude stationary repetitions and spelled non-fifths.
- Boundary and rest navigation produce explicit skipped traces.

## 8. Accepted experimental direction

### Candidates and input

Fix supplied S/B, global key, and inner-voice rhythmic skeleton. Predict pitches of whichever inner voices attack at a decision time; jointly predict A and T when both attack. Held notes are not reassigned.

A prediction event is a time with at least one inner-voice attack. Other musical events can still trigger scores. Do not drop soprano-only, bass-only or figure contributions that depend on candidate inner pitches.

Declare broad finite pitch and spelling domains independent of the gold realization at a particular event. Preserve possible range violations, crossings, chromaticism and parallels if those are to be learned. Hard structural conditions and supplied figures are distinct from learned stylistic preferences.

Gold inclusion must be audited; a missing gold candidate is a reported generator failure, not a silent exclusion. Pin corpus, encoding provenance, splits, pitch domains, and transposition policy. Rhythmic skeletons derived from the gold score are explicit conditioning information, not hidden claims of unrestricted generation.

### Probability model

For context x, candidate y, rule scores C_r(y,x), and weights w_r:
E(y,x) = sum_r w_r C_r(y,x).
P(y|x) = exp(-E(y,x)) / sum_z exp(-E(z,x)), over the entire declared candidate set.

Use log-sum-exp for numerical stability.
Fit weights by regularized negative log likelihood. Negative raw penalties are allowed. Whether fitted weights are restricted to nonnegative values remains OPEN; document the chosen interpretation and regularizer before fitting.

A rule whose score is constant across candidates cannot change that conditional distribution. Detect and report this; never advertise it as predictive success.

### Staged horizons

1. Exact next-event prediction first: validate implementation, candidates, probabilities, feature traces and weight fitting.
2. Joint next-two-event prediction as first substantive comparison, using the same rule inventory and input information.
3. Longer horizons only after measured benefit and computational profiling.

Joint next-two scoring is not the same as making two locally normalized one-event predictions. Score complete two-event candidates and normalize jointly. Sum over second-event alternatives to get the marginal probability of the next choice.

Lookback length and prediction horizon are independent. One-event prediction can apply a three-note recovery rule using two supplied past notes. Two-event prediction can assess recovery from a leap currently being proposed. Two global decision events need not include two attacks in the same voice.

Fixed input information should be the same across horizon comparisons. Supplied future S/B and rhythm are permissible conditioning; gold future A/T pitches are not.

Boundary convention needs a precise implementation: no penalties for unobserved future resolutions. Define a consistent half-open scoring window, including intervening fixed outer-voice/figure events before the next unresolved inner choice, and charge every occurrence once. Record this policy in experiment metadata. This is an implementation recommendation, not a separately ratified timing theory.

### Evaluation and discovery

Primary: held-out negative log likelihood, averaged per prediction decision.
Secondary: gold rank, top-k accuracy, first-choice marginal from joint horizons, full-window log likelihood per event, calibration, and generation inspection.

Baselines: uniform over identical candidates, simple voice pitch preferences, and simple melodic transition model. Keep manually supplied seed rules distinct from LLM-discovered rules.

Split by chorale and group related settings of a tune where identifiable. Keep test data inaccessible to the proposal loop. Fit weights on train; propose/select using development evidence; report final frozen test results without using them to revise rules.

Repeated development optimization can overfit; bound discovery rounds and consider inner validation/resampling for scientific claims.
Prefer simpler rule sets when predictive improvements are negligible.
Compare scores paired by chorale and account for overlapping windows rather than treating every window as independent evidence.

Generation: sampling and high-probability search are separate outputs. Report exact probabilities only when normalization is exact. Probability within a sampled candidate list or beam is not global model probability.
Rolling two-step generation is not automatically a whole-phrase MaxEnt distribution.
Whole-phrase dynamic programming is a future option if sufficient state can be bounded; arbitrary per-voice history can make that state large.

### Figured bass

Initial general voice-leading learning can use chorales without figures.
Later supplied figures can condition candidate compatibility through a deterministic, independently specified interpreter.
Do not assume every passing note must always belong to the written chord.
Figure contents, implied tones, resolutions, later attacks under a held figure, and malformed/uncertain figures remain open work.
The At figure trigger alone does not implement universal chord-tone completeness.

## 9. Architecture proposal — not yet approved

Recommendation: separate private repository under EasyArray, provisionally harmony-lab. Keep Telemann OMR as a transcription/review producer. Import accepted exports via a documented versioned interface; do not put learned inner voices into the authoritative OMR transcription.

No local installation for the user:
- Assistant develops in the cloud workspace.
- GitHub Actions installs dependencies on disposable cloud runners and runs reproducible tests/experiments.
- Small HTML/Markdown reports, JSON metrics, examples and optionally rendered scores are available through browser/download.
- No custom dashboard, always-on server, GPU, or cloud database required initially.
- Ordinary tests and fitting use no paid model calls.
- A small provider adapter supports U-M Toolkit and direct OpenAI, but initialize only one provider first.

Proposed implementation:
- Python core with music21 at import/export boundaries, compact internal typed objects, a small DSL parser, numerical arrays, and a standard optimizer.
- Precompute/cache rule features; do not perform slow music-library object operations for every candidate.
- Package candidate generation, scoring, fitting, evaluation, reporting and discovery as separate modules with one small command-line entry point for automation.
- Checkpoint source often; persist reproducible corpus manifests, split IDs, rules, fitted weights, run configuration and summary metrics.
- Persist nonreproducible paid responses and accounting state durably. GitHub Actions caches and expiring artifacts are not the sole ledger or sole copy of paid work.

Autonomous bounded research loop:
1. Load current train/development results and frozen DSL specification.
2. Ask an allowed model for a small batch of rule proposals.
3. Parse and validate; reject unsupported syntax and resource-excessive expressions.
4. Evaluate deterministically and refit on train.
5. Compare on development and update experiment records.
6. Save checkpoint/report, then stop at iteration, cost or runtime limits.
7. Never modify DSL semantics, test splits, billing limits, workflow privileges or secrets through generated rule text.

API calls are for proposing/explaining/revising rules, not for each candidate harmonization or each optimizer iteration. The loop does not grant the proposing model unrestricted shell or credential access.

Credentials and spending:
- Project-specific API credential in GitHub Actions secrets, available only to designated trusted jobs.
- No key in conversation, source, test fixtures, reports or logs.
- Credential can be used by jobs without exposing its value to the assistant.
- Initial mocks and deterministic tests need no key.
- Bounded live adapter smoke test after credential setup.
- Approved live experiment configuration, exact model IDs, token/output/retry caps and a run budget.
- Conservative cost reservation before requests; unknown/ambiguous charges remain reserved.
- Serialize initial paid runs; durable cumulative ledger and atomic reservation if concurrent workers are introduced.
- Missing accounting state, unknown pricing, or an unrecognized model stops paid work.
- Spending-cap and billing errors are terminal, not transient retry errors.
- Provider hard limit is a backstop; budget alerts alone are insufficient.
- Provider-side cap stays outside the runtime credential's authority.
- Separate API, cloud compute/storage, and interactive ChatGPT usage budgets.
- Example proposed pilot limits only: $1 smoke test, $5 experiment run, $25 monthly API cap. These numbers are NOT authorization to spend.

OpenAI's current documentation describes project/organization hard limits, with possible slight overshoot due to enforcement delay. Application reservations provide earlier stopping; no claim of a mathematically exact provider bill.
U-M publicly documents monthly quotas; public inspection did not verify their units, hard-stop behavior or enforcement delay because detailed settings documentation requires sign-in.
GitHub Actions has compute/storage costs and an independent stop-usage budget option. Scope budgets so unrelated Telemann work is not inadvertently stopped.

One-time user setup proposed:
- Create/authorize the new repository under their account (the currently exposed GitHub connector has no create-repository operation; browser creation is a possible fallback).
- Choose provider/billing source and authorize explicit budgets/models.
- Add project credential as an Actions secret and set provider cap.
- Grant connector access to the new repository.
Afterward assistant can implement, trigger configured workflows through an available authorized route, inspect logs, and fix failures without repeated key entry. GitHub Actions secrets are only available inside the designated workflow jobs, not automatically in the interactive workspace.

## 10. Implementation milestones

A. Spec and offline core: parser, score import, semantic fixtures, candidate coverage, probability normalization; no API calls.
B. Reproducible one-event benchmark with transparent seed constraints and baselines.
C. Bounded live provider adapter test; save response for later mock/replay testing.
D. Bounded rule proposal/evaluation loop; development-only feedback and cost records.
E. Exact next-two benchmark on a measured tractable subset, then scale or introduce explicitly labeled approximation.
F. Figure interpreter and Telemann integration after general learning is demonstrated.
G. Optional longer horizons and a review UI only if experiment results justify them.

## 11. Open decisions before implementation or paid launch

- Repository name and creation/access route.
- Dataset source, licensing, duplicate-tune grouping and spelling normalization.
- Exact pitch domains; global key provenance and unusual modes.
- Missing-value branch semantics and temporal scoring boundaries.
- Lexer details, interval edge cases, literal escaping, and optional simple interval operation.
- Weight sign constraints, regularization strength and complexity penalty.
- Figure-content semantics and compatibility timing.
- Provider/model, exact prices and quotas, budgets and persistent accounting store.
- Workflow trigger route, permissions, checkpoint retention and artifact location.

Do not present these unresolved details as settled by the user.

## Sources consulted

Accessed 2026-11-15:
- Hayes & Wilson, A Maximum Entropy Model of Phonotactics and Phonotactic Learning: https://colincwilson.github.io/papers/HayesWilsonMaxEntPhonotactics2008.pdf
- Sutton & McCallum, An Introduction to Conditional Random Fields: https://homepages.inf.ed.ac.uk/csutton/publications/crftut-fnt.pdf
- Figured-bass key-signature reference: https://www.continuo.ca/files/Figured%20bass%20chart.pdf
- Historical/relative figure alteration conventions: https://doc.verovio.humdrum.org/humdrum/figured_bass/
- OpenAI spend limits: https://developers.openai.com/api/docs/guides/spend-limits
- OpenAI per-run budget controller: https://developers.openai.com/cookbook/articles/per_run_spending_controller_responses_api
- U-M Toolkit overview: https://www.its.umich.edu/computing/ai/gpt-toolkit-in-depth
- GitHub Actions secrets: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
- GitHub budgets: https://docs.github.com/en/billing/how-tos/set-up-budgets
- Telemann OMR README inspected: https://github.com/EasyArray/telemann-omr/blob/main/README.md

These references support background and current service capabilities, not approval of all architecture recommendations.

