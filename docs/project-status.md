# Resume here

Updated November 17, 2026. Branch: `attack-dsl-prototype`; draft PR #1.

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

Round 002 completed through OpenAI using Astra/high and the expanded report.
All three proposals passed DSL validation. Conservative total API accounting is
$0.330158 of $10. The response and validation are saved: never resend round-002.
The offline proposal evaluation is launched by the committed evaluation request;
check that workflow once on resume and read docs/round-002-evaluation.md when
available. It publishes its own report and fitted candidate model.
Keep the proposal response and its validation separate from evidence that any
rule improves predictive probabilities.

## Durable operation

Commit source, reports, prompts, responses and accounting to GitHub. Keep secrets
out of git and reports. A managed environment secret or GitHub Actions secret is
a more durable credential location than a workspace-only file, but no credential
has been moved or recreated in this recovery. Such migration is optional and
does not block the working development key.

Official environment documentation describes saved task state and managed
secrets, while still recommending source control for important work:
https://learn.chatgpt.com/docs/environments/cloud-environments
