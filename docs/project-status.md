# Resume here

Updated November 20, 2026. Branch: `attack-dsl-prototype`; draft PR #1.

## Recovery check

The original workspace and its existing OpenAI development key file survived.
The local checkout was behind GitHub and has been updated. A read-only OpenAI
request authenticated successfully and confirmed access to `gpt-6-astra`.
No replacement key or additional funding was needed. System Python lacks
pytest; the existing `.venv/bin/python` works. The recovery check passed 64
tests; adding semantic checks for the actual Astra proposals brought this to
71 passing tests.

The previous turn mishandled an environment outage by repeatedly polling cloud
work and expanding scope while waiting. A failed git push is a separate issue:
shell git can fetch, but writes require the connected GitHub tool. These are
distinct from a deleted workspace, revoked API key, or exhausted API balance.

## Completed

- Generic, single-voice and voice-union note triggers, including
  `At alto or tenor attack n:`. One binding per attacking note; a union shares
  one fitted weight, whereas separate rules permit separate weights.
- Exact probabilistic evaluation on 40 training and 20 development chorales,
  360 decisions and 666,297 candidates, with complete observed-note coverage.
- [Expanded report](expanded-development.md), including architectural controls,
  key sensitivity, spelling diagnostics and whole-family bootstrap intervals.
- Expanded workflow run **43966324296** completed successfully and published
  its results. Do not rerun it to recover its output.
- Key-independent provisional model at `experiments/models/current.json` and
  `rules/learned/current.harmony`. This is the preserved first-round fit.

## Interpretation

Shared spacing improved the observed completion's geometric probability by
about 3.1%, helping 19/20 development pieces. Separate voice weights and counting
once per event did not improve this particular comparison. Equal L2 coefficients
do not make these parameterizations fully comparable: feature scaling and
parameter count affect the effective regularization. Keep the simple shared
rule provisionally; do not declare the event-count convention settled.

Encoded and S/B-estimated keys disagree in 12/60 pieces. Neither is verified
ground truth. Degree-dependent rules remain provisional. Spelling alternatives
still divide probability; the report now shows the sounding-pitch total too.

## Next action

Round 002 finished and published its [evaluation](round-002-evaluation.md).
The [five-family foundations experiment](foundations.md) has also finished. Its
rulebook, reproducible offline runner and per-piece results are on this branch.
Both runs preserve the 40/20 split. Conservative total API accounting remains
$0.330158 of $10. No experiments are pending.

The next scientific question is why outer consonance helps joint attacks but
reduces the probability of Bach’s pitch on single attacks. Compare a shared
weight against separate weights by attack type on the same decisions, and
inspect passing notes and suspensions before interpreting the difference.
Reserve fresh chorale families for a confirmatory test after model selection.

## Durable operation

Commit source, reports, prompts, responses and accounting to GitHub. Keep secrets
out of git and reports. A managed environment secret or GitHub Actions secret is
a more durable credential location than a workspace-only file, but no credential
has been moved or recreated in this recovery. Such migration is optional and
does not block the working development key.

Official environment documentation describes saved task state and managed
secrets, while still recommending source control for important work:
https://learn.chatgpt.com/docs/environments/cloud-environments
