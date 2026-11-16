# Bounded model proposals

The user authorized a $10 initial **total** API budget across providers, with no
automatic reset. U-M's reported $25/month quota is a separate backstop. The
current development adapter uses the separately authorized OpenAI key; U-M
cloud execution is not yet wired. No CI job runs paid requests.

The provider proposes DSL text only. It receives a small explicit prompt, no
shell, credentials, tools, corpus files, or final test data. Parsed proposals are
evaluated by the same deterministic implementation as handwritten rules.

## Current controls

- Ledger: `experiments/api-ledger.json`, committed on `attack-dsl-prototype`.
  Missing, corrupt, changed-limit, or unsynchronized accounting stops a request.
- One outstanding reservation, unique request IDs, maximum 25 cents per request,
  maximum 64 KB of prompt and 6,000 output tokens (including reasoning).
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
Do not run paid jobs from multiple clones/workers. Before enabling U-M or cloud
paid jobs, route them through the same durable reservation process. User/API
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
These remain experimental hypotheses until the development comparison is read.
