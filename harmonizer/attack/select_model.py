"""Select and export a provisional development model using a frozen policy."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from .dsl import parse
from .pilot import MELODIC
from .proposals import validate_response


def choose(results, policy):
  reference=policy["reference_model"]
  scores={name:row["mean_piece_nll"] for name,row in results["summary"].items()}
  eligible=[]
  for name,value in scores.items():
    if not name.startswith("base+"):
      continue
    if name.startswith("base+pair:") and not policy.get("allow_pair_models",False):
      continue
    wins=sum(piece[name]<piece[reference] for piece in results["by_piece"].values())
    if scores[reference]-value >= policy["minimum_improvement_nats"] and wins/len(results["by_piece"])>=policy["minimum_piece_win_fraction"]:
      eligible.append(name)
  if not eligible:
    return reference
  best=min(scores[name] for name in eligible)
  near=[name for name in eligible if scores[name]<=best+policy["simplicity_tolerance_nats"]]
  return min(near,key=lambda name:(len(results.get("added_rules",{}).get(name,[])) or (3 if name=="base+all-proposals" else 1),scores[name],name))


def export(report_path, policy_path, seed_path, response_path, rules_output, model_output):
  report=json.loads(Path(report_path).read_text())
  policy=json.loads(Path(policy_path).read_text())
  selected=choose(report["results"],policy)
  accepted=validate_response(response_path)["accepted"]
  additions=[]
  if selected=="base+all-proposals":
    additions=accepted
  elif selected.startswith("base+proposal:"):
    additions=[item for item in accepted if item["title"]==selected.removeprefix("base+proposal:")]
    if len(additions)!=1:
      raise ValueError("Selected proposal not present in saved response")
  elif selected.startswith("base+pair:"):
    titles=report["results"]["added_rules"][selected]
    additions=[item for item in accepted if item["title"] in titles]
    if len(additions)!=2:
      raise ValueError("Selected pair is not present in saved response")
  source=Path(seed_path).read_text()+"\n"+MELODIC+"\n"+"\n\n".join(item["dsl"] for item in additions)+"\n"
  rules=parse(source)
  fitted=report["results"]["weights"][selected]
  if set(fitted)!={r.title for r in rules}:
    raise ValueError("Selected inventory does not match fitted weights")
  rules_output=Path(rules_output);rules_output.parent.mkdir(parents=True,exist_ok=True);rules_output.write_text(source)
  model={"status":"provisional; selected on development, not a final test result","selected":selected,
         "rules_sha256":sha256(source.encode()).hexdigest(),"rule_weights":{r.id:fitted[r.title] for r in rules},
         "titles":{r.id:r.title for r in rules},"domains":report["domains"],
         "manifest_sha256":report["manifest_sha256"],"training_code_sha256":report["code_sha256"],
         "selection_policy":policy,"selection_policy_sha256":sha256(Path(policy_path).read_bytes()).hexdigest(),
         "development_summary":report["results"]["summary"][selected]}
  model_output=Path(model_output);model_output.parent.mkdir(parents=True,exist_ok=True)
  model_output.write_text(json.dumps(model,indent=2)+"\n")
  return model


def main():
  p=argparse.ArgumentParser(description=__doc__)
  p.add_argument("--report",default="artifacts/bach-development.json")
  p.add_argument("--policy",default="experiments/selection-policy.json")
  p.add_argument("--seed",default="rules/seed.harmony")
  p.add_argument("--response",default="experiments/api-responses/round-001.json")
  p.add_argument("--rules-output",default="rules/learned/round-001.harmony")
  p.add_argument("--model-output",default="experiments/models/round-001.json")
  args=p.parse_args()
  model=export(args.report,args.policy,args.seed,args.response,args.rules_output,args.model_output)
  print(json.dumps({"selected":model["selected"],"development":model["development_summary"]},indent=2))


if __name__=="__main__":
  main()
