"""Write rule-cost CSV reports for the BWV 33.06 sample chorale."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from examples.starter_constraints import STARTER_RULES
from harmonizer import (
    analyze_musicxml_rules,
    resolve_bcfb_musicxml_path,
    write_cost_rows_csv,
)

ANCHOR_THRESHOLD = 0.45
SCORE_SCOPE = "hybrid"


def main() -> None:
    musicxml_path = resolve_bcfb_musicxml_path("BWV_33.06")
    analysis = analyze_musicxml_rules(
        musicxml_path,
        STARTER_RULES,
        anchor_threshold=ANCHOR_THRESHOLD,
        score_scope=SCORE_SCOPE,
    )

    rows = analysis.rows
    anchor_rows = [row for row in rows if row["is_anchor"] == "yes"]
    rows_by_strength = sorted(
        rows,
        key=lambda row: (float(row["event_strength"]), -float(row["offset"])),
        reverse=True,
    )

    artifacts_dir = Path(__file__).resolve().parents[1] / "artifacts"
    raw_path = write_cost_rows_csv(artifacts_dir / "BWV_33.06_rule_costs.csv", analysis)
    anchor_path = write_cost_rows_csv(
        artifacts_dir / "BWV_33.06_anchor_rule_costs.csv",
        analysis,
        rows=anchor_rows,
    )
    strength_path = write_cost_rows_csv(
        artifacts_dir / "BWV_33.06_events_by_strength.csv",
        analysis,
        rows=rows_by_strength,
    )

    print(f"Wrote {len(rows)} raw events to {raw_path}")
    print(f"Wrote {len(anchor_rows)} anchor events to {anchor_path}")
    print(f"Selected {len(analysis.anchor_indices)} anchors from {len(analysis.rows)} raw events")
    print(f"Wrote strength-ranked events to {strength_path}")
    print(f"Anchor threshold: {ANCHOR_THRESHOLD}")
    print(f"Score scope: {SCORE_SCOPE}")
    for rule_name, total in sorted(analysis.totals_by_rule().items()):
        print(f"{rule_name}: {total:.1f}")


if __name__ == "__main__":
    main()
