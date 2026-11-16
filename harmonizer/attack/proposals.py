"""One-shot proposal requests with durable reservations; never executes model code."""
import argparse
from decimal import Decimal, ROUND_CEILING
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import subprocess
import urllib.request
import urllib.error

MODEL = "gpt-6.1-terra"
LEDGER = Path("experiments/api-ledger.json")
# USD/million tokens == micro-USD/token. Upper input rate includes the most
# expensive documented cache-write tier; short, standard-service text only.
INPUT_RATE = Decimal("2.5")
OUTPUT_RATE = Decimal("5")
CEILING = 10_000_000
REQUEST_CEILING = 250_000
MAX_OUTPUT = 6000
MAX_BYTES = 64_000
PRICE_SOURCE = "https://developers.openai.com/api/docs/models/gpt-6.1-terra"
PRICE_CHECKED = "2026-11-16"


def digest(data):
  return sha256(data).hexdigest()


def cost(input_tokens, output_tokens):
  if type(input_tokens) is not int or type(output_tokens) is not int or min(input_tokens, output_tokens) < 0:
    raise ValueError("Invalid token usage")
  return int((input_tokens * INPUT_RATE + output_tokens * OUTPUT_RATE).to_integral_value(rounding=ROUND_CEILING))


def read_ledger(path=LEDGER):
  data = json.loads(path.read_text())  # Missing/corrupt ledger stops, never resets.
  if data.get("version") != 1 or data.get("ceiling_micro_usd") != CEILING:
    raise ValueError("Unrecognized ledger or changed spending ceiling")
  entries = data["entries"]
  if len({e["id"] for e in entries}) != len(entries):
    raise ValueError("Duplicate reservation IDs")
  for e in entries:
    if type(e["accounted_micro_usd"]) is not int or e["accounted_micro_usd"] < 0:
      raise ValueError("Invalid accounting state")
    if e["status"] not in ("reserved", "completed", "incomplete", "unknown"):
      raise ValueError("Unknown reservation status")
  if sum(e["accounted_micro_usd"] for e in entries) > CEILING:
    raise ValueError("Spending ceiling reached or exceeded")
  return data


def save_json(path, data):
  path.parent.mkdir(parents=True, exist_ok=True)
  temporary = path.with_suffix(path.suffix + ".tmp")
  temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
  os.replace(temporary, path)


def require_durable(path=LEDGER):
  # Read-only fetch. Every new request must start from the current remote ledger.
  subprocess.run(["git", "fetch", "origin", "attack-dsl-prototype"], check=True, capture_output=True)
  remote = subprocess.check_output(["git", "show", f"origin/attack-dsl-prototype:{path.as_posix()}"])
  if remote != path.read_bytes():
    raise ValueError("Ledger is not synchronized to GitHub; checkpoint before proceeding")


def reserve(identity, prompt_path, ledger_path=LEDGER, tickets=Path("artifacts/api-tickets")):
  if not identity or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in identity):
    raise ValueError("Request ID must use lowercase letters, digits and hyphens")
  data = read_ledger(ledger_path)
  if any(e["id"] == identity for e in data["entries"]):
    raise ValueError("Request ID already exists; never automatically retry a paid request")
  if any(e["status"] == "reserved" for e in data["entries"]):
    raise ValueError("Resolve the pending reservation before starting another")
  raw = prompt_path.read_bytes()
  if not raw or len(raw) > MAX_BYTES:
    raise ValueError("Prompt is empty or too large")
  reserved = cost(len(raw) + 4096, MAX_OUTPUT)
  if reserved > REQUEST_CEILING or sum(e["accounted_micro_usd"] for e in data["entries"]) + reserved > CEILING:
    raise ValueError("Request would exceed the spending ceiling")
  ticket = secrets.token_hex(32)
  tickets.mkdir(parents=True, exist_ok=True)
  target = tickets / identity
  with target.open("x") as f:
    os.chmod(target, 0o600)
    f.write(ticket)
  entry = {"id": identity, "provider": "openai", "model": MODEL, "status": "reserved",
           "prompt_sha256": digest(raw), "ticket_sha256": digest(ticket.encode()),
           "max_output_tokens": MAX_OUTPUT, "reserved_micro_usd": reserved,
           "accounted_micro_usd": reserved, "pricing_checked": PRICE_CHECKED,
           "pricing_source": PRICE_SOURCE, "input_micro_usd_per_token_ceiling": str(INPUT_RATE),
           "output_micro_usd_per_token_ceiling": str(OUTPUT_RATE)}
  data["entries"].append(entry)
  save_json(ledger_path, data)
  return entry


def settle(data, entry, response):
  usage = response.get("usage") or {}
  try:
    accounted = cost(usage["input_tokens"], usage["output_tokens"])
  except (KeyError, ValueError):
    entry["status"] = "unknown"
    return
  entry["usage"] = usage
  entry["status"] = "completed" if response.get("status") == "completed" else "incomplete"
  entry["accounted_micro_usd"] = accounted
  if accounted > entry["reserved_micro_usd"]:
    entry["status"] = "unknown"
    raise ValueError("Actual accounted cost exceeded reservation; stop and reconcile")


def send(identity, prompt_path):
  require_durable()
  data = read_ledger()
  entry = next(e for e in data["entries"] if e["id"] == identity)
  if entry["status"] != "reserved" or entry["model"] != MODEL:
    raise ValueError("Request is not an unspent reservation for the allowed model")
  raw = prompt_path.read_bytes()
  if digest(raw) != entry["prompt_sha256"]:
    raise ValueError("Prompt changed after reservation")
  env = dict(line.split("=", 1) for line in Path(".env.local").read_text().splitlines() if "=" in line)
  key = env["OPENAI_API_KEY"].strip()
  response_path = Path("experiments/api-responses") / f"{identity}.json"
  if response_path.exists():
    raise ValueError("Saved response exists: replay it instead of paying again")
  ticket_path = Path("artifacts/api-tickets") / identity
  # Atomic rename claims the one-use local ticket; a second process fails.
  claimed = ticket_path.with_suffix(".claimed")
  os.rename(ticket_path, claimed)
  ticket = claimed.read_text()
  claimed.unlink()
  if digest(ticket.encode()) != entry["ticket_sha256"]:
    raise ValueError("Invalid one-use ticket")
  # A lost workspace loses its ticket. The remote reservation continues to
  # count in full and cannot be resent automatically.
  request_body = {"model": MODEL, "input": raw.decode(), "max_output_tokens": MAX_OUTPUT,
                  "reasoning": {"effort": "low"}, "service_tier": "default", "store": False}
  request = urllib.request.Request("https://api.openai.com/v1/responses",
    data=json.dumps(request_body).encode(),
    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
  try:
    with urllib.request.urlopen(request, timeout=90) as response:
      result = json.load(response)
    save_json(response_path, result)
    entry["response_path"] = str(response_path)
    entry["response_sha256"] = digest(response_path.read_bytes())
    settle(data, entry, result)
  except Exception as error:
    # Never log request headers, response error bodies or plaintext credentials.
    entry["status"] = "unknown"
    entry["accounted_micro_usd"] = max(entry["accounted_micro_usd"], entry["reserved_micro_usd"])
    entry["error_type"] = type(error).__name__
    if isinstance(error, urllib.error.HTTPError):
      entry["http_status"] = error.code
  finally:
    save_json(LEDGER, data)
  return {"id": identity, "status": entry["status"], "accounted_micro_usd": entry["accounted_micro_usd"]}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("action", choices=("reserve", "send"))
  parser.add_argument("identity")
  parser.add_argument("prompt", type=Path)
  args = parser.parse_args()
  if args.action == "reserve":
    require_durable()
    result = reserve(args.identity, args.prompt)
  else:
    result = send(args.identity, args.prompt)
  print(json.dumps(result, indent=2))


if __name__ == "__main__":
  main()
