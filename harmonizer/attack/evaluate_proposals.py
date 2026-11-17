"""Offline proposal round with a committed report and provisional fitted model."""
import json
from pathlib import Path
import re
from .benchmark import run
from .expanded import bootstrap
from .proposals import validate_response
from .select_model import export


def main():
  request = json.loads(Path('experiments/requests/evaluate-proposals.json').read_text())
  identity = request['round']
  if not re.fullmatch(r'round-[0-9]{3}', identity):
    raise ValueError('Invalid round identifier')
  manifest_path = 'experiments/bach-expanded.json'
  base_path = 'rules/discovery-base.harmony'
  response_path = f'experiments/api-responses/{identity}.json'
  proposals_path = f'rules/proposals/{identity}.harmony'
  validated = validate_response(response_path)
  expected = '\n\n'.join(item['dsl'] for item in validated['accepted']) + '\n'
  if not validated['accepted'] or Path(proposals_path).read_text() != expected:
    raise ValueError('Proposal file must match the saved validated response')
  report = run(manifest_path, base_path, proposals_path)
  manifest = json.loads(Path(manifest_path).read_text())
  report['uncertainty'] = bootstrap(report['results'], manifest)
  report_path = Path(f'artifacts/{identity}-evaluation.json')
  report_path.parent.mkdir(exist_ok=True)
  report_path.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
  model = export(report_path, 'experiments/selection-policy.json', base_path,
    response_path, f'rules/learned/{identity}.harmony', f'experiments/models/{identity}.json')
  summary = {**report, 'results': {k:v for k,v in report['results'].items() if k != 'development'},
             'selected':model['selected']}
  Path(f'experiments/results/{identity}-summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
  rows = [f'# {identity}: proposal evaluation', '',
    'Development evidence only; no final test data. Lower NLL is better.', '',
    'The reference includes the original seed rules, melodic-motion baselines and the previously retained shared spacing rule. All weights are refitted on the same 40 training chorales; evaluation uses the same 20 development chorales.', '',
    '| Inventory | Piece NLL | Gain over reference | 95% family-bootstrap interval |',
    '|---|---:|---:|---:|']
  for name, metrics in report['results']['summary'].items():
    uncertainty = report['uncertainty'][name]
    lo, hi = uncertainty['interval95']
    rows.append(f"| {name} | {metrics['mean_piece_nll']:.4f} | {uncertainty['gain_nats']:+.4f} | [{lo:+.4f}, {hi:+.4f}] |")
  rows += ['', f"Provisional selection under the pre-existing policy: **{model['selected']}**.",
    'The current default model is not automatically replaced. Intervals do not account for repeated development-set selection.', '',
    '## Actual model proposals', '']
  for item in validated['accepted']:
    rows += [f"### {item['title']}", '', item.get('rationale',''), '', '```',item['dsl'],'```','']
  rows += ['## Discriminatory training support', '']
  for name, count in report['results']['training_windows_with_varying_feature'].items():
    rows.append(f'- {name}: {count} training windows with differing candidate penalties.')
  rows += ['', f"Complete observed-note coverage: {len(report['coverage'])}/{len(report['coverage'])} decisions.",
    f"Elapsed computation: {report['runtime_seconds']/60:.1f} minutes. This evaluation made no API calls.", '']
  Path(f'docs/{identity}-evaluation.md').write_text('\n'.join(rows))


if __name__ == '__main__':
  main()
