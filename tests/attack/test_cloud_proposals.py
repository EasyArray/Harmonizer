from copy import deepcopy
from datetime import date
import pytest
from harmonizer.attack import cloud_proposals as cloud


@pytest.fixture
def ledger(monkeypatch):
  monkeypatch.setattr(cloud, "PRICE_CHECKED", date.today().isoformat())
  return {"entries": [], "ceiling_micro_usd": 10_000_000}


def test_cloud_reservation_counts_full_cost_and_refuses_replay(ledger):
  entry = cloud.reservation(ledger, "round-002", b"prompt")
  assert entry["status"] == "unknown"
  assert entry["accounted_micro_usd"] == entry["reserved_micro_usd"]
  ledger["entries"].append(entry)
  with pytest.raises(ValueError, match="never resend"):
    cloud.reservation(ledger, "round-002", b"prompt")
  with pytest.raises(ValueError, match="reconciliation"):
    cloud.reservation(ledger, "another", b"prompt")


def test_cloud_total_budget_and_usage(ledger):
  ledger["entries"] = [{"id": "old", "status": "completed", "accounted_micro_usd": 9_900_000}]
  with pytest.raises(ValueError, match="ceiling"):
    cloud.reservation(ledger, "round-002", b"prompt")
  ledger["entries"] = []
  entry = cloud.reservation(ledger, "round-002", b"prompt")
  original = deepcopy(entry)
  cloud.settle(entry, {"status": "completed"})
  assert entry == original
  cloud.settle(entry, {"status": "completed", "usage": {"input_tokens": 100, "output_tokens": 200}})
  assert entry["accounted_micro_usd"] == 12_500
  assert entry["status"] == "completed"


def test_failed_remote_checkpoint_prevents_paid_request(tmp_path, monkeypatch, ledger):
  monkeypatch.chdir(tmp_path)
  request_path = tmp_path / "request.json"
  request_path.write_text('{"id":"round-002","model":"gpt-6-astra","prompt":"experiments/prompts/round-002.txt"}')
  prompt = tmp_path / "experiments/prompts/round-002.txt"
  prompt.parent.mkdir(parents=True)
  prompt.write_text("Propose rules")
  monkeypatch.setattr(cloud, "REQUEST", request_path)
  monkeypatch.setattr(cloud, "read_ledger", lambda: ledger)
  monkeypatch.setenv("UM_TOOLKIT_API_KEY", "fake-test-key")
  calls = []
  def fake_request(endpoint, key, payload=None):
    calls.append(endpoint)
    assert endpoint == "/models"
    return {"data": [{"id": cloud.MODEL}]}
  def fail_checkpoint(*args):
    raise RuntimeError("remote unavailable")
  monkeypatch.setattr(cloud, "request", fake_request)
  monkeypatch.setattr(cloud, "checkpoint", fail_checkpoint)
  with pytest.raises(RuntimeError, match="remote unavailable"):
    cloud.main()
  assert calls == ["/models"]
