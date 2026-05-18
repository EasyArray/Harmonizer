"""Helpers for writing color-highlighted MusicXML debugging scores."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

from .rule_costs import RuleAnalysis

SATB_PART_IDS = ("P1", "P2", "P3", "P4")


@dataclass(frozen=True)
class HighlightedScore:
    """Output path and tooltip metadata for a highlighted score export."""

    path: Path
    tooltips_by_color: dict[str, str]
    highlighted_event_indices: tuple[int, ...]


def write_cost_highlighted_musicxml(
    source_path: str | Path,
    output_path: str | Path,
    analysis: RuleAnalysis,
    *,
    max_events: int = 16,
    minimum_cost: float = 1.0,
    anchors_only: bool = False,
    part_ids: tuple[str, ...] = SATB_PART_IDS,
) -> HighlightedScore:
    """Color the highest-cost events in a MusicXML score."""

    source = Path(source_path)
    output = Path(output_path)
    selected_rows = list(
        analysis.high_cost_rows(
            limit=max_events,
            minimum_cost=minimum_cost,
            anchors_only=anchors_only,
        )
    )
    color_by_event_index = {
        int(row["index"]): _event_color(rank, max(1, len(selected_rows)))
        for rank, row in enumerate(selected_rows)
    }
    priority_by_event_index = {
        int(row["index"]): rank
        for rank, row in enumerate(selected_rows)
    }
    tooltip_by_color = {
        color.lower(): _tooltip_for_row(row, analysis.rule_columns)
        for row in selected_rows
        for color in [color_by_event_index[int(row["index"])]]
    }

    tree = ET.parse(source)
    root = tree.getroot()
    target_offsets = {
        int(row["index"]): float(row["offset"])
        for row in selected_rows
    }

    _color_sounding_notes(
        root,
        target_offsets=target_offsets,
        color_by_event_index=color_by_event_index,
        priority_by_event_index=priority_by_event_index,
        part_ids=part_ids,
    )

    ET.indent(tree, space="  ")
    output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output, encoding="utf-8", xml_declaration=True)
    return HighlightedScore(
        path=output,
        tooltips_by_color=tooltip_by_color,
        highlighted_event_indices=tuple(sorted(color_by_event_index)),
    )


def _color_sounding_notes(
    root: ET.Element,
    *,
    target_offsets: dict[int, float],
    color_by_event_index: dict[int, str],
    priority_by_event_index: dict[int, int],
    part_ids: tuple[str, ...],
) -> None:
    targets_by_offset = sorted(target_offsets.items(), key=lambda item: item[1])
    for part in root.findall("part"):
        part_id = part.get("id")
        if part_id not in part_ids:
            continue

        divisions = 1
        measure_start = 0.0
        for measure in part.findall("measure"):
            local_cursor = 0
            measure_duration = 0
            attributes = measure.find("attributes")
            if attributes is not None and attributes.find("divisions") is not None:
                divisions = int(attributes.findtext("divisions") or divisions)

            for child in list(measure):
                if child.tag == "backup":
                    local_cursor -= int(child.findtext("duration") or 0)
                    continue
                if child.tag == "forward":
                    local_cursor += int(child.findtext("duration") or 0)
                    measure_duration = max(measure_duration, local_cursor)
                    continue
                if child.tag != "note":
                    continue

                duration = int(child.findtext("duration") or 0)
                is_chord = child.find("chord") is not None
                is_rest = child.find("rest") is not None
                if not is_rest and duration > 0:
                    start = measure_start + (local_cursor / divisions)
                    end = measure_start + ((local_cursor + duration) / divisions)
                    event_index = _highest_cost_event_in_span(start, end, targets_by_offset, priority_by_event_index)
                    if event_index is not None:
                        _set_note_color(child, color_by_event_index[event_index])

                if not is_chord:
                    local_cursor += duration
                    measure_duration = max(measure_duration, local_cursor)

            measure_start += measure_duration / divisions


def _highest_cost_event_in_span(
    start: float,
    end: float,
    targets_by_offset: list[tuple[int, float]],
    priority_by_event_index: dict[int, int],
) -> int | None:
    epsilon = 1e-6
    matching = [
        event_index
        for event_index, offset in targets_by_offset
        if start - epsilon <= offset < end - epsilon
    ]
    if not matching:
        return None
    return min(matching, key=lambda event_index: priority_by_event_index[event_index])


def _set_note_color(note_element: ET.Element, color: str) -> None:
    normalized = color.upper()
    note_element.set("color", normalized)
    notehead = note_element.find("notehead")
    if notehead is not None:
        notehead.set("color", normalized)


def _event_color(rank: int, count: int) -> str:
    if count <= 1:
        ratio = 1.0
    else:
        ratio = rank / (count - 1)
    red = 220
    green = int(38 + 132 * ratio)
    blue = int(38 + 44 * ratio)
    return f"#{red:02x}{green:02x}{blue:02x}"


def _tooltip_for_row(row: dict[str, object], rule_columns: tuple[str, ...]) -> str:
    nonzero_costs = [
        f"{column}: {float(row[column]):.1f}"
        for column in rule_columns
        if float(row[column]) != 0.0
    ]
    header = (
        f"Event {row['index']} | measure {row['measure']} beat {row['beat']} | "
        f"total {float(row['total_cost']):.1f}"
    )
    detail = "\n".join(nonzero_costs) if nonzero_costs else "No nonzero rule costs."
    return f"{header}\n{detail}"
