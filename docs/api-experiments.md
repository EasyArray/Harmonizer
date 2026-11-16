# Bounded model proposals

The user authorized a $10 initial **total** API budget across providers, with no
automatic reset. U-M's reported $25/month quota is a separate backstop. The
local development adapter uses the separately authorized OpenAI key. A separate
one-shot Actions workflow now supports a bounded U-M Astra request. Ordinary
CI and benchmark jobs remain offline.

The provider proposes DSL text only. It receives a small explicit prompt, no
shell, credentials, tools, corpus files, or final test data. Parsed proposals are
evaluated by the same deterministic implementation as handwritten rules.

## Current controls

- Ledger: `experiments/api-ledger.json`, committed on `attack-dsl-prototype`.
  Missing, corrupt, changed-limit, or unsynchronized accounting stops a request.
- One outstanding reservation and unique request IDs. The original local Terra
  adapter caps requests at 25 cents, 64 KB and 6,000 output tokens. The explicitly
  authorized stronger-model cloud adapter caps a request at $2, 40 KB and 12,000
  output tokens, still within the same $10 total project ceiling.
- Reserve a conservative token-cost ceiling before sending. The ledger must be
  checkpointed to GitHub before `send` can proceed. Fetching the latest ledger is
  read-only and never exposes a key.
- A local single-use ticket is consumed before the network call. Losing the
  workspace loses the ticket; the durable reservation remains charged in full.
  No retry or automatic release occurs after timeouts, missing usage or errors.
- Responses are saved for replay. Before another request, checkpoint both the
  response and updated ledger. Uncertain charges retain the reservation.
- Model and prices are allowlisted, with a seven-day review deadline. The first
  round uses `gpt-6.1-terra`, low reasoning, standard service, no tools, no stored
  conversation. Pricing source and review date are in each ledger entry.
- Accounting uses integer micro-dollars. The input rate is conservatively $2.50
  per million tokens (covering the most expensive documented cache-write tier),
  and output $5 per million tokens. Actual uncached standard input is currently
  $1 per million tokens, so the ledger can overcount usage rather than
  undercount it. Prices were checked November 16, 2026 at
  <https://developers.openai.com/api/docs/models/gpt-6.1-terra>.

This is a serialized development workflow, not a distributed transaction system.
Do not run paid jobs from multiple clones/workers. The U-M Actions job uses a
single concurrency group and the same ledger. It commits an unknown/claimed
entry before sending; another run refuses to resend that request ID. User/API
activity outside this project is not covered by this ledger. Provider billing
controls remain independent.

## Assistant-operated sequence

1. Write the exact nonsecret prompt under `experiments/prompts/`.
2. `python -m harmonizer.attack.proposals reserve ROUND PROMPT`.
3. Commit/sync the ledger and prompt through the GitHub connection.
4. `python -m harmonizer.attack.proposals send ROUND PROMPT`.
5. Save and validate the response as data, checkpoint response and ledger, and
   evaluate accepted DSL on training/development only. Never execute returned
   Python or promote unsupported syntax into the language automatically.

The first reservation initialized the ledger with the prior confirmed $0
spending. Subsequent reservations must start with a remote-synchronized ledger.
The user does not need to run these commands or handle the key.

## Round 001

The exact prompt and response are saved in the repository. Three proposals
passed grammar/type validation. Their known limitations are explicit in tests:
spacing counts twice at simultaneous A/T attacks; leading-tone resolution checks
global degree rather than a stepwise upward motion, and penalizes repetition;
the octave rule handles exact positive octaves, not compound/negative octaves.
The [completed development comparison](discovery-round-001.md) provisionally
retained spacing and leading-tone behavior before the key-label audit. The
key-independent policy now excludes leading-tone behavior from the current
model. These remain experimental hypotheses, not independently tested musical
discoveries.

## Stronger-model round 002

The prepared request uses `gpt-6-astra` with high reasoning. U-M published
standard rates checked November 16, 2026 are $10 input / $50 output per million
tokens. The adapter conservatively accounts input at $25 to allow cache-write
premiums; it caps output at 12,000 tokens. The exact prompt currently reserves
less than $1, although the per-request safety ceiling is $2.

The read-only provider probe returned HTTP 999. No paid request was sent and
no round-002 reservation was created. See [execution status](cloud-experiment-status.md).
A successful probe or workflow execution is not evidence of a generated proposal:
the saved response, validation file and ledger entry establish that.

The existing OpenAI key is in the temporarily unavailable development workspace.
Keys are never placed in prompts, source files, logs or reports. GitHub secrets
are consumed only within the dedicated proposal job.
