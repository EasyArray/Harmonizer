# Working on Harmonizer

- Use lightweight Python, two-space indentation, and `match` where useful.
- Start by reading `docs/project-status.md` and checking the remote branch and
  recorded workflow IDs. GitHub is the durable source of project state.
- Check workspace and credential availability once. Unavailable is not deleted.
  Inspect credentials only through presence checks; never print their contents
  or create a replacement merely because a workspace cannot be reached.
- Use `.venv/bin/python` for this checkout. System Python may lack dependencies.
- Use the GitHub connector for writes when shell git has read-only access.
  Preserve local changes when synchronizing with remote commits.
- Do not keep a turn alive solely to poll a long experiment. Check once, do
  independent authorized work, then check once more. If still running, save a
  checkpoint with the job link and exact next action. Do not start unrelated
  features merely to fill the wait, or rerun an experiment already in progress.
- Checkpoint substantive work to GitHub before a long job or ending a turn.
  Record completed work, pending jobs, blockers and the next concrete step in
  `docs/project-status.md`; chat progress messages are not the project ledger.
- API spending is capped at $10 total across providers. Respect the committed
  ledger and unique request IDs. Never resend a reserved, completed or uncertain
  request automatically. Replay saved responses instead of paying again.
- Ordinary tests and musical evaluation are offline. Never expose final-test
  data to a proposal model. Distinguish generated proposals, syntax validation,
  development results, and independently validated musical conclusions.
