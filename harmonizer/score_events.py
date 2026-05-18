"""Extract SATB vertical events and figured-bass context from MusicXML."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

from music21 import converter, key, meter, note, stream

from .rules_api import (
    A,
    B,
    S,
    T,
    FiguredBassFigure,
    PitchValue,
    VerticalEvent,
    VoiceName,
)

VOICE_PARTS: tuple[tuple[VoiceName, int], ...] = (
    (S, 0),
    (A, 1),
    (T, 2),
    (B, 3),
)


@dataclass(frozen=True)
class _VoiceSpan:
    start: float
    end: float
    pitch: PitchValue | None


@dataclass(frozen=True)
class _MeasureInfo:
    label: str
    start: float
    end: float
    beat_quarter_length: float
    time_signature: meter.TimeSignature | None


DEFAULT_ANCHOR_THRESHOLD = 0.45


def resolve_bcfb_musicxml_path(
    bwv: str = "BWV_33.06",
    *,
    workspace_root: str | Path | None = None,
) -> Path:
    """Resolve a BCFB chorale id such as ``BWV_33.06`` to a local MusicXML file."""

    root = Path(workspace_root) if workspace_root is not None else Path(__file__).resolve().parents[1]
    musicxml_root = root / "data" / "bcfb_v2" / "juyaolongpaul-Bach_chorale_FB-0873cc7" / "FB_source" / "musicXML_master"
    candidates = [
        musicxml_root / f"{bwv}_FB.musicxml",
        musicxml_root / f"{bwv.replace('.', '_')}_FB.musicxml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Could not find any of: {', '.join(str(candidate) for candidate in candidates)}.")


def load_musicxml_vertical_events(path: str | Path) -> tuple[VerticalEvent, ...]:
    """Load a MusicXML score as a stream of SATB vertical events."""

    musicxml_path = Path(path)
    score = converter.parse(musicxml_path)
    if len(score.parts) < 4:
        raise ValueError("Expected at least four parts for soprano, alto, tenor, and bass.")

    xml_root = ET.parse(musicxml_path).getroot()
    measure_infos = _measure_infos(score.parts[0], xml_root)
    key_signature_map = _key_signature_map(score.parts[0])
    figure_events = _figure_events(score, xml_root)
    voice_spans = {
        voice: _voice_spans(score.parts[part_index])
        for voice, part_index in VOICE_PARTS
    }
    voice_start_maps = {
        voice: {span.start: span.pitch for span in spans}
        for voice, spans in voice_spans.items()
    }
    bass_onsets = set(voice_start_maps[B].keys())

    onset_candidates = set(figure_events.keys())
    for spans in voice_spans.values():
        for span in spans:
            onset_candidates.add(span.start)
    onsets = sorted(onset_candidates)

    if not onsets:
        return ()

    current_pitches: dict[VoiceName, PitchValue | None] = {voice: None for voice, _ in VOICE_PARTS}
    current_figures: tuple[FiguredBassFigure, ...] = ()
    current_fifths = 0
    key_pointer = 0
    measure_pointer = 0
    key_offsets = [offset for offset, _ in key_signature_map]

    events: list[VerticalEvent] = []
    for index, onset in enumerate(onsets):
        previous_pitches = dict(current_pitches)

        while key_pointer + 1 < len(key_signature_map) and key_offsets[key_pointer + 1] <= onset:
            key_pointer += 1
        current_fifths = key_signature_map[key_pointer][1]

        changed_voices: list[VoiceName] = []
        for voice in (S, A, T, B):
            pitch_map = voice_start_maps[voice]
            if onset in pitch_map:
                current_pitches[voice] = pitch_map[onset]
                changed_voices.append(voice)

        figure_changed = onset in figure_events
        if onset in bass_onsets and not figure_changed:
            current_figures = ()
        if figure_changed:
            current_figures = figure_events[onset]

        while measure_pointer + 1 < len(measure_infos) and measure_infos[measure_pointer + 1].start <= onset:
            measure_pointer += 1
        measure = measure_infos[measure_pointer]
        relative_offset = onset - measure.start
        beat = 1.0 + (relative_offset / measure.beat_quarter_length)
        beat_strength = _beat_strength(measure, relative_offset)
        event_strength, strength_components = _event_strength(
            beat_strength=beat_strength,
            changed_voices=tuple(changed_voices),
            figure_changed=figure_changed,
        )

        events.append(
            VerticalEvent(
                soprano=current_pitches[S],
                alto=current_pitches[A],
                tenor=current_pitches[T],
                bass=current_pitches[B],
                index=index,
                offset=onset,
                measure=measure.label,
                beat=beat,
                beat_strength=beat_strength,
                event_strength=event_strength,
                figures=current_figures,
                figure_changed=figure_changed,
                key_signature_fifths=current_fifths,
                changed_voices=tuple(changed_voices),
                previous_pitches=previous_pitches,
                metadata={
                    "source_path": str(musicxml_path),
                    "strength_components": strength_components,
                },
            )
        )

    return tuple(events)


def select_anchor_events(
    events: tuple[VerticalEvent, ...] | list[VerticalEvent],
    threshold: float = DEFAULT_ANCHOR_THRESHOLD,
) -> tuple[VerticalEvent, ...]:
    """Return events whose heuristic strength reaches the anchor threshold."""

    return tuple(event for event in events if event.is_anchor(threshold))


def sort_events_by_strength(
    events: tuple[VerticalEvent, ...] | list[VerticalEvent],
    *,
    descending: bool = True,
) -> tuple[VerticalEvent, ...]:
    """Sort events by heuristic structural strength for debugging."""

    return tuple(sorted(events, key=lambda event: (event.event_strength, event.offset or 0.0), reverse=descending))


def _voice_spans(part: stream.Part) -> tuple[_VoiceSpan, ...]:
    spans: list[_VoiceSpan] = []
    for element in part.flatten().notesAndRests:
        duration = float(element.quarterLength)
        if duration <= 0:
            continue
        start = float(element.offset)
        end = start + duration
        pitch = _pitch_from_music21_note(element)
        spans.append(_VoiceSpan(start=start, end=end, pitch=pitch))
    return tuple(spans)


def _pitch_from_music21_note(element: note.GeneralNote) -> PitchValue | None:
    if element.isRest:
        return None
    if hasattr(element, "pitch"):
        music21_pitch = element.pitch
    else:
        music21_pitch = element.pitches[0]
    alter = 0 if music21_pitch.accidental is None else int(music21_pitch.accidental.alter)
    accidental = {
        -2: "bb",
        -1: "b",
        0: "",
        1: "#",
        2: "##",
    }.get(alter)
    if accidental is None:
        raise ValueError(f"Unsupported note accidental alter {alter} in {music21_pitch!r}.")
    return PitchValue.from_components(
        letter=music21_pitch.step,
        accidental=accidental,
        octave=music21_pitch.octave,
    )


def _measure_infos(part: stream.Part, xml_root: ET.Element) -> tuple[_MeasureInfo, ...]:
    raw_labels = [measure.get("number") or str(index) for index, measure in enumerate(xml_root.find("part").findall("measure"))]
    measures = list(part.getElementsByClass("Measure"))
    if len(raw_labels) != len(measures):
        raise ValueError("MusicXML measure labels did not line up with parsed score measures.")

    infos: list[_MeasureInfo] = []
    beat_quarter_length = 1.0
    current_time_signature: meter.TimeSignature | None = None
    for index, (measure, label) in enumerate(zip(measures, raw_labels)):
        if measure.timeSignature is not None:
            beat_quarter_length = float(measure.timeSignature.beatDuration.quarterLength)
            current_time_signature = measure.timeSignature
        start = float(measure.offset)
        end = float(measures[index + 1].offset) if index + 1 < len(measures) else float(part.highestTime)
        infos.append(
            _MeasureInfo(
                label=label,
                start=start,
                end=end,
                beat_quarter_length=beat_quarter_length,
                time_signature=current_time_signature,
            )
        )
    return tuple(infos)


def _key_signature_map(part: stream.Part) -> tuple[tuple[float, int], ...]:
    key_signatures = list(part.flatten().getElementsByClass(key.KeySignature))
    if not key_signatures:
        return ((0.0, 0),)

    mapping = [(float(signature.offset), int(signature.sharps)) for signature in key_signatures]
    if mapping[0][0] != 0.0:
        mapping.insert(0, (0.0, mapping[0][1]))
    return tuple(mapping)


def _figure_events(score: stream.Score, xml_root: ET.Element) -> dict[float, tuple[FiguredBassFigure, ...]]:
    if len(score.parts) < 5:
        return {}

    continuo_measures = list(score.parts[4].getElementsByClass("Measure"))
    raw_continuo = xml_root.findall("part")[-1].findall("measure")
    if len(continuo_measures) != len(raw_continuo):
        raise ValueError("Continuo measure count mismatch while reading figured bass.")

    events: dict[float, tuple[FiguredBassFigure, ...]] = {}
    divisions = 1
    for measure, raw_measure in zip(continuo_measures, raw_continuo):
        attributes = raw_measure.find("attributes")
        if attributes is not None and attributes.find("divisions") is not None:
            divisions = int(attributes.findtext("divisions"))

        note_cursor = 0
        pending_figures: list[tuple[tuple[FiguredBassFigure, ...], int | None]] = []
        measure_start = float(measure.offset)

        for child in raw_measure:
            if child.tag == "attributes":
                continue
            if child.tag == "figured-bass":
                parsed_figures = _parse_figured_bass(child)
                duration_text = child.findtext("duration")
                duration = int(duration_text) if duration_text else None
                pending_figures.append((parsed_figures, duration))
                continue
            if child.tag == "forward":
                note_cursor += int(child.findtext("duration") or 0)
                continue
            if child.tag == "backup":
                note_cursor -= int(child.findtext("duration") or 0)
                continue
            if child.tag != "note":
                continue

            duration = int(child.findtext("duration") or 0)
            note_start = note_cursor
            if pending_figures:
                local_cursor = 0
                for figures, figure_duration in pending_figures:
                    onset = measure_start + ((note_start + local_cursor) / divisions)
                    events[onset] = figures
                    if figure_duration is not None:
                        local_cursor += figure_duration
                pending_figures.clear()
            note_cursor += duration

    return events


def _parse_figured_bass(figured_bass: ET.Element) -> tuple[FiguredBassFigure, ...]:
    figures: list[FiguredBassFigure] = []
    for figure in figured_bass.findall("figure"):
        parsed = FiguredBassFigure.from_musicxml(
            number=figure.findtext("figure-number"),
            prefix=figure.findtext("prefix"),
            suffix=figure.findtext("suffix"),
        )
        if parsed.is_blank:
            continue
        figures.append(parsed)
    return tuple(figures)


def _beat_strength(measure: _MeasureInfo, relative_offset: float) -> float:
    if measure.time_signature is None:
        return 0.0
    return float(measure.time_signature.getAccentWeight(relative_offset, forcePositionMatch=False))


def _event_strength(
    *,
    beat_strength: float,
    changed_voices: tuple[VoiceName, ...],
    figure_changed: bool,
) -> tuple[float, dict[str, float]]:
    components = {
        "beat": 0.30 * beat_strength,
        "figure": 0.45 if figure_changed else 0.0,
        "soprano": 0.35 if S in changed_voices else 0.0,
        "bass": 0.30 if B in changed_voices else 0.0,
        "alto": 0.05 if A in changed_voices else 0.0,
        "tenor": 0.05 if T in changed_voices else 0.0,
    }
    return min(1.0, sum(components.values())), components
