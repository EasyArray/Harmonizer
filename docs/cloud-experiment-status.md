# Cloud execution status

Update, November 17: the workspace and existing OpenAI development key have
returned. An authenticated model-access check succeeded. The expanded GitHub
experiment completed successfully. Astra/high has since returned three valid
proposals via OpenAI; conservative cumulative API accounting is $0.330158.
Their offline evaluation runs in GitHub. See [current status](project-status.md).

The following records describe the earlier interruption:

- The U-M secret was supplied to a read-only model-list probe on November 16,
  2026. The gateway returned HTTP 999 before any paid request. This does not
  establish whether the credential itself is valid.
- The existing OpenAI development key remains in the unavailable workspace.
  No plaintext key has been requested or copied into a report.
- Round 002 is prepared for gpt-6-astra, high reasoning, up to 12,000 output
  tokens. The request is one-shot and records a conservative reservation on
  GitHub before the paid call. Existing request IDs are never automatically
  resent.
- Project API ceiling remains $10 across providers. The first request accounts
  for $0.005758 conservatively; connection probes do not request generation.
- A failed or interrupted paid request retains its full reservation until
  reconciled. A workflow rerun cannot silently create a second request.
- No further funding or local installation is needed for the offline
  development experiment.

The expanded report compares architecture choices on a larger development set.
It does not claim that a stronger model has supplied new rules until a response
has actually been saved and validated.
