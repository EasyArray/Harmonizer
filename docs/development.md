# Development Notes

This project is intentionally small and notebook-friendly. Treat `harmonizer/`
as the reusable library and `notebooks/` as the exploratory front end.

## What Belongs In Git

Commit source files, examples, tests, docs, and notebooks with cleared outputs.
Do not commit downloaded corpus data, rendered HTML, generated MusicXML, CSV
reports, Jupyter runtime folders, or Python cache files.

The important ignored directories are:

- `data/`
- `artifacts/`
- `notebooks/data/`
- `notebooks/artifacts/`
- `.jupyter_local/`
- `.ipynb_checkpoints/`

## Adding A Declarative Rule

1. Add a constructor in `harmonizer/constraints_dsl.py`.
2. Validate inputs there so bad notebook edits fail early with clear errors.
3. Add scoring support in `harmonizer/rule_costs.py`.
4. Add a small test that builds the rule and checks one positive/negative case.
5. Add the rule to `examples/starter_constraints.py` only if it belongs in the
   default musical discussion.

## Adding Code-First Rule Helpers

Use `harmonizer/rules_api.py` for musical primitives that a hand-written Python
rule should naturally see: pitches, intervals, harmony events, and vertical
events. Keep the objects plain and inspectable.

`RuleSet.evaluate(...)` discovers public methods on a subclass:

- one argument means a rule over a single vertical event
- two arguments means a rule over consecutive event pairs
- three or more arguments means a sliding event window

## Notebook Discipline

The notebooks should demonstrate the workflow, not hide important library code.
If a notebook cell starts becoming a reusable algorithm, move it into
`harmonizer/` and leave the notebook as a thin user-facing workflow.

Before publishing or committing notebook edits, clear outputs so local paths and
large rendered HTML blobs do not end up in version control.

## Checks

Run:

```powershell
python -m pytest
```

For corpus-dependent manual checks, run:

```powershell
python .\examples\bwv_33_rule_cost_report.py
```

That second command requires the local `data/` corpus folder.
