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


def test_one_shot_send_and_unknown_transport_stays_reserved(tmp_path, monkeypatch):
  import harmonizer.attack.proposals as api
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr(api, "require_durable", lambda: None)
  Path("experiments").mkdir()
  path=ledger(tmp_path)
  path.rename("experiments/api-ledger.json")
  Path(".env.local").write_text("OPENAI_API_KEY=fake-test-credential\n")
  prompt=Path("prompt.txt");prompt.write_text("three rules")
  api.reserve("once",prompt)
  class Reply:
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self):return json.dumps({"status":"completed","usage":{"input_tokens":10,"output_tokens":10}}).encode()
  monkeypatch.setattr(api.urllib.request,"urlopen",lambda *a,**kw:Reply())
  assert api.send("once",prompt)["status"]=="completed"
  with pytest.raises(ValueError,match="unspent"):
    api.send("once",prompt)
  reserved=api.reserve("uncertain",prompt)["reserved_micro_usd"]
  def timeout(*a,**kw):raise TimeoutError("not printed")
  monkeypatch.setattr(api.urllib.request,"urlopen",timeout)
  result=api.send("uncertain",prompt)
  assert result["status"]=="unknown" and result["accounted_micro_usd"]==reserved
  with pytest.raises(ValueError,match="unspent"):
    api.send("uncertain",prompt)


def test_saved_model_response_replays_without_a_paid_request():
  from harmonizer.attack.proposals import validate_response
  result=validate_response(Path("experiments/api-responses/round-001.json"))
  assert len(result["accepted"])==3 and not result["rejected"]


def test_astra_uses_its_own_price_limits_and_reasoning(tmp_path, monkeypatch):
  import harmonizer.attack.proposals as api
  monkeypatch.chdir(tmp_path)
  monkeypatch.setattr(api, "require_durable", lambda: None)
  Path("experiments").mkdir()
  ledger(tmp_path).rename("experiments/api-ledger.json")
  Path(".env.local").write_text("OPENAI_API_KEY=fake-test-credential\n")
  prompt = Path("prompt.txt")
  prompt.write_text("Three readable rules")
  entry = api.reserve("astra", prompt, model="gpt-6-astra")
  assert entry["max_output_tokens"] == 12000
  assert entry["reserved_micro_usd"] > 600000
  assert entry["reserved_micro_usd"] < 2000000
  calls = []
  class Reply:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self):
      return json.dumps({"status":"completed","usage":{"input_tokens":1000,"output_tokens":1000}}).encode()
  def fake_request(request, **kwargs):
    payload = json.loads(request.data)
    calls.append(payload)
    assert payload["model"] == "gpt-6-astra"
    assert payload["reasoning"]["effort"] == "high"
    assert payload["max_output_tokens"] == 12000
    return Reply()
  monkeypatch.setattr(api.urllib.request,"urlopen",fake_request)
  result = api.send("astra",prompt)
  assert result["accounted_micro_usd"] == 75000
  assert len(calls) == 1
  with pytest.raises(ValueError,match="unspent"):
    api.send("astra",prompt)


def test_unpriced_model_cannot_reserve(tmp_path):
  with pytest.raises(ValueError,match="allowlisted"):
    reserve("unpriced",tmp_path/"unused",model="not-priced")
