# Harmonizer Workbench

Harmonizer Workbench is a notebook-first Python project for experimenting with
18th-century chorale harmonization from soprano melody plus figured bass.

The current prototype focuses on a narrow, inspectable loop:

- load Bach Chorale Figured Bass corpus files
- render original MusicXML in Jupyter/Colab with Verovio
- describe harmony rules in a small declarative DSL
- score Bach realizations against those rules
- export CSV and highlighted-score artifacts for discussion

It is meant to be readable by a musician-programmer as much as by a Python
developer. The code favors plain dataclasses, explicit rule names, and small
helper functions over framework machinery.

## Quick Start

Create an environment and install the project:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

Or, if you only want the notebook dependency surface:

```powershell
pip install -r requirements.txt
```

Start Jupyter Lab locally on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_jupyter_lab.ps1
```

Then open one of the notebooks:

- [notebooks/01_display_bcfb_chorale.ipynb](notebooks/01_display_bcfb_chorale.ipynb)
  downloads/opens a corpus chorale and renders preview scores.
- [notebooks/02_rule_testing_harness.ipynb](notebooks/02_rule_testing_harness.ipynb)
  runs the rule-cost analysis and writes highlighted debugging output.

The notebooks and examples expect the Bach corpus to live under `data/`. That
directory is intentionally ignored by git because it is generated/downloaded
material rather than source code.

## Project Layout

```text
harmonizer/              Reusable Python package
  constraints_dsl.py     Declarative rulebook objects and validators
  rules_api.py           Code-first musical event and rule API
  score_events.py        MusicXML-to-event extraction
  rule_costs.py          Rule scoring and CSV rows
  score_debug.py         Highlighted MusicXML export
  notebook_display.py    Jupyter/Verovio display helpers

examples/                Small runnable scripts
notebooks/               Notebook-first exploration workflow
scripts/                 Local launch helpers
tests/                   Focused tests for public behavior
docs/                    Contributor/development notes
```

Generated material goes in `data/`, `artifacts/`, or local Jupyter folders. The
`.gitignore` keeps those out of GitHub while leaving the source files visible.

## Rule Systems

There are two rule interfaces.

The declarative DSL is designed for notebooks and future UI work:

```python
from harmonizer import A, T, avoid_voice_crossing, cover_chord_tones, prefer_range, rulebook

RULES = rulebook(
    "Starter Chorale Constraints",
    cover_chord_tones(root=500, third=500, fifth=80, seventh=300),
    avoid_voice_crossing(penalty=100),
    prefer_range(alto="C4", tenor="G3", cost_per_semitone=3, free_semitones=10),
)
```

The code-first API is useful when you want to write Python rule bodies directly
against exposed musical events:

```python
from harmonizer import Note, RuleSet, VerticalEvent


class Rules(RuleSet):
    ALTO_CENTER = Note.C4

    def alto_in_range(self, ev: VerticalEvent):
        if ev.alto is None:
            return 0
        return abs(self.ALTO_CENTER - ev.alto) * 10
```

For score-derived events, use:

```python
from harmonizer import load_musicxml_vertical_events, resolve_bcfb_musicxml_path

path = resolve_bcfb_musicxml_path("BWV_33.06")
events = load_musicxml_vertical_events(path)
```

## Examples

Print the starter declarative rulebook as JSON:

```powershell
python .\examples\starter_constraints.py
```

Analyze BWV 33.06 with the starter rules:

```powershell
python .\examples\bwv_33_rule_cost_report.py
```

That example writes CSV files into `artifacts/`:

- `BWV_33.06_rule_costs.csv`
- `BWV_33.06_anchor_rule_costs.csv`
- `BWV_33.06_events_by_strength.csv`

## Tests

Run the focused test suite with:

```powershell
python -m pytest
```

The tests avoid the large corpus download; they check the public rule DSL, pitch
and harmony helpers, and rule-cost analysis on small in-memory examples.

## Data And Artifacts

The project currently uses the Bach Chorale Figured Bass corpus (BCFB v2.0) as
its working source. The corpus itself is not vendored into this repository.
Notebook runs may download it under `data/`.

The notebooks also rely on browser-side Verovio JavaScript for score rendering,
so full visual rendering requires internet access unless that asset is cached by
the browser.

## License

The Harmonizer Workbench source code is released under the MIT License. See
[LICENSE](LICENSE).

Downloaded corpus files and generated artifacts are not part of this source
license. If you use the Bach Chorale Figured Bass corpus, follow the license and
citation guidance distributed with that dataset.

See [docs/development.md](docs/development.md) for the short maintainer guide.
