"""One-shot U-M requests from Actions, checkpointed remotely before spending."""
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
from .proposals import CEILING, LEDGER, read_ledger, save_json, validate_response

BASE = "https://api.toolkit.umgpt.umich.edu/v1"
MODEL = "gpt-6-astra"
PRICE_CHECKED = "2026-11-16"
# Standard published rate: $10/$50 per million. Input ceiling includes a
# conservative 2.5x allowance for cache writes. No tools, images or retries.
INPUT_RATE = 25
OUTPUT_RATE = 50
MAX_OUTPUT = 12000
MAX_BYTES = 40000
REQUEST_LIMIT = 2_000_000
REQUEST = Path("experiments/requests/round-002.json")
STATUS = Path("experiments/um-provider-status.json")


class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self, req, fp, code, msg, headers, newurl):
    raise ValueError("API redirects are not allowed")


def request(endpoint, key, payload=None):
  raw = None if payload is None else json.dumps(payload).encode()
  req = urllib.request.Request(BASE + endpoint, data=raw,
    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
  with urllib.request.build_opener(NoRedirect).open(req, timeout=240) as response:
    return json.load(response)


def checkpoint(paths, message):
  """Retry only git transport, never a model request."""
  subprocess.run(["git", "add", "--", *map(str, paths)], check=True, capture_output=True)
  subprocess.run(["git", "commit", "-m", message], check=True, capture_output=True)
  for attempt in range(3):
    result = subprocess.run(["git", "push", "origin", "HEAD:attack-dsl-prototype"], capture_output=True)
    if result.returncode == 0:
      return
    subprocess.run(["git", "pull", "--rebase", "origin", "attack-dsl-prototype"],
                   check=True, capture_output=True)
  raise RuntimeError("Checkpoint not published; stop without another API request")


def reservation(data, identity, raw):
  if any(e["id"] == identity for e in data["entries"]):
    raise ValueError("Request already recorded; never resend automatically")
  if any(e["status"] in ("reserved", "unknown") for e in data["entries"]):
    raise ValueError("Unresolved request requires reconciliation")
  if not raw or len(raw) > MAX_BYTES:
    raise ValueError("Invalid prompt size")
  if not 0 <= (date.today() - date.fromisoformat(PRICE_CHECKED)).days <= 7:
    raise ValueError("Refresh provider pricing before spending")
  amount = (len(raw) + 4096) * INPUT_RATE + MAX_OUTPUT * OUTPUT_RATE
  if amount > REQUEST_LIMIT or sum(e["accounted_micro_usd"] for e in data["entries"]) + amount > CEILING:
    raise ValueError("Spending ceiling would be exceeded")
  return {"id": identity, "provider": "um-toolkit", "model": MODEL,
    "status": "unknown", "phase": "claimed-before-network",
    "prompt_sha256": sha256(raw).hexdigest(), "max_output_tokens": MAX_OUTPUT,
    "reserved_micro_usd": amount, "accounted_micro_usd": amount,
    "pricing_checked": PRICE_CHECKED, "pricing_source": "https://its.umich.edu/computing/ai/pricing",
    "input_micro_usd_per_token_ceiling": INPUT_RATE,
    "output_micro_usd_per_token_ceiling": OUTPUT_RATE,
    "workflow_run": os.environ.get("GITHUB_RUN_ID"), "reasoning_effort": "high"}


def settle(entry, response):
  usage = response.get("usage") or {}
  a, b = usage.get("input_tokens"), usage.get("output_tokens")
  if type(a) is not int or type(b) is not int or min(a, b) < 0:
    return
  amount = a * INPUT_RATE + b * OUTPUT_RATE
  if amount > entry["reserved_micro_usd"]:
    entry["error_type"] = "UsageExceedsReservation"
    entry["accounted_micro_usd"] = amount
    return
  entry.update(usage=usage, accounted_micro_usd=amount,
    status="completed" if response.get("status") == "completed" else "incomplete",
    phase="response-saved")


def main():
  key = os.environ.get("UM_TOOLKIT_API_KEY", "").strip()
  if not key:
    save_json(STATUS, {"status": "secret-unavailable", "paid_requests": 0})
    checkpoint([STATUS], "Record U-M credential availability")
    return
  try:
    models = request("/models", key)
    available = MODEL in {row["id"] for row in models["data"]}
    status = {"status": "model-listed" if available else "model-not-listed",
              "model": MODEL, "checked": date.today().isoformat(), "paid_requests_in_probe": 0}
  except Exception as error:
    status = {"status": "probe-failed", "error_type": type(error).__name__,
              "http_status": error.code if isinstance(error, urllib.error.HTTPError) else None,
              "paid_requests_in_probe": 0}
    available = False
  save_json(STATUS, status)
  if not available or not REQUEST.exists():
    checkpoint([STATUS], "Record U-M model availability without a paid request")
    return
  spec = json.loads(REQUEST.read_text())
  if spec != {"id": "round-002", "model": MODEL, "prompt": "experiments/prompts/round-002.txt"}:
    raise ValueError("Unexpected paid request specification")
  data = read_ledger()
  if any(e["id"] == spec["id"] for e in data["entries"]):
    print("Request already recorded: no network resubmission.")
    return
  raw = Path(spec["prompt"]).read_bytes()
  entry = reservation(data, spec["id"], raw)
  data["entries"].append(entry)
  save_json(LEDGER, data)
  # Interruption after this checkpoint leaves a fully charged unknown entry.
  # Only this process proceeds; a fresh process sees the recorded request ID.
  checkpoint([LEDGER, STATUS], "Reserve round-002 budget before one U-M Astra request")
  paths = [LEDGER]
  try:
    result = request("/responses", key, {"model": MODEL, "input": raw.decode(),
      "max_output_tokens": MAX_OUTPUT, "reasoning": {"effort": "high"}, "store": False})
    response_path = Path("experiments/api-responses/round-002.json")
    save_json(response_path, result)
    paths.append(response_path)
    entry.update(response_path=str(response_path), response_sha256=sha256(response_path.read_bytes()).hexdigest())
    settle(entry, result)
    if result.get("status") == "completed":
      validated = validate_response(response_path)
      validation_path = Path("experiments/round-002-validation.json")
      save_json(validation_path, validated)
      paths.append(validation_path)
      if validated["accepted"]:
        rules_path = Path("rules/proposals/round-002.harmony")
        rules_path.write_text("\n\n".join(item["dsl"] for item in validated["accepted"]) + "\n")
        paths.append(rules_path)
  except Exception as error:
    entry["error_type"] = type(error).__name__
    if isinstance(error, urllib.error.HTTPError):
      entry["http_status"] = error.code
    # Parser failures preserve a saved response and its settled usage charge.
  finally:
    save_json(LEDGER, data)
    checkpoint(paths, "Save round-002 response, validation and API accounting")
  print(json.dumps({"id": entry["id"], "status": entry["status"],
                    "accounted_micro_usd": entry["accounted_micro_usd"]}))


if __name__ == "__main__":
  main()
