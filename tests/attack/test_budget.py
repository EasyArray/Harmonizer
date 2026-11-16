import json
from pathlib import Path
import pytest
from harmonizer.attack.proposals import CEILING, MAX_BYTES, cost, read_ledger, reserve, settle


def ledger(tmp_path, entries=None):
  path = tmp_path / "ledger.json"
  path.write_text(json.dumps({"version": 1, "ceiling_micro_usd": CEILING, "entries": entries or []}))
  return path


def test_reservation_duplicate_pending_and_unknown_charge(tmp_path):
  path = ledger(tmp_path)
  prompt = tmp_path / "prompt.txt"
  prompt.write_text("Propose three rules.")
  entry = reserve("test-1", prompt, path, tmp_path / "tickets")
  assert entry["accounted_micro_usd"] == cost(len(prompt.read_bytes())+4096, 6000)
  with pytest.raises(ValueError, match="already exists"):
    reserve("test-1", prompt, path, tmp_path / "tickets")
  with pytest.raises(ValueError, match="pending"):
    reserve("test-2", prompt, path, tmp_path / "tickets")
  before = entry["accounted_micro_usd"]
  settle({}, entry, {})
  assert entry["status"] == "unknown" and entry["accounted_micro_usd"] == before


def test_total_ceiling_missing_ledger_and_prompt_limit(tmp_path):
  prompt = tmp_path / "prompt.txt"
  prompt.write_text("hello")
  path = ledger(tmp_path, [{"id": "old", "status": "completed", "accounted_micro_usd": CEILING-1}])
  with pytest.raises(ValueError, match="ceiling"):
    reserve("new", prompt, path, tmp_path / "tickets")
  with pytest.raises(FileNotFoundError):
    read_ledger(tmp_path / "absent.json")
  path = ledger(tmp_path)
  prompt.write_text("x"*(MAX_BYTES+1))
  with pytest.raises(ValueError, match="large"):
    reserve("new", prompt, path, tmp_path / "tickets")


def test_conservative_cost_and_reconciliation():
  assert cost(1000,1000) == 7500
  entry = {"reserved_micro_usd": 10000, "accounted_micro_usd": 10000}
  settle({}, entry, {"status":"completed", "usage":{"input_tokens":1000,"output_tokens":1000}})
  assert entry["status"] == "completed" and entry["accounted_micro_usd"] == 7500
  with pytest.raises(ValueError):
    cost(-1, 10)
  with pytest.raises(ValueError, match="exceeded"):
    settle({}, entry, {"status":"completed", "usage":{"input_tokens":10000,"output_tokens":10000}})


def test_corrupt_or_changed_limits_fail_closed(tmp_path):
  path = ledger(tmp_path)
  data=json.loads(path.read_text())
  data["ceiling_micro_usd"] *= 2
  path.write_text(json.dumps(data))
  with pytest.raises(ValueError, match="changed"):
    read_ledger(path)
