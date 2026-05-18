from harmonizer import FiguredBassFigure, Note, RuleSet, VerticalEvent


def test_pitch_literals_accept_common_accidental_spellings():
    assert Note.Bb3.midi == 58
    assert Note.Fs4.spelling == "F#4"
    assert Note.C4 - Note.B3 == 1


def test_harmony_event_expands_simple_figures():
    event = VerticalEvent.from_literals(
        soprano="C5",
        alto="G4",
        tenor="E4",
        bass="E3",
        figures=[FiguredBassFigure(number=6)],
    )

    harmony = event.harmony()

    assert harmony is not None
    assert harmony.figure_text == "6"
    assert harmony.inversion == "first-inversion-triad"
    assert harmony.role_by_interval[1] == "third"
    assert harmony.role_by_interval[6] == "root"


def test_ruleset_evaluates_single_events_and_sliding_windows():
    class TinyRules(RuleSet):
        def missing_alto(self, ev: VerticalEvent):
            return 10 if ev.alto is None else 0

        def parallel_fifths(self, ev1: VerticalEvent, ev2: VerticalEvent):
            cost = 0
            before = {interval.voices(): interval for interval in ev1.intervals()}
            for interval in ev2.intervals():
                previous = before.get(interval.voices())
                if previous is not None and previous.motion_to(interval).is_parallel:
                    cost += 100
            return cost

    events = [
        VerticalEvent.from_literals(soprano="G4", alto=None, tenor="E3", bass="C3"),
        VerticalEvent.from_literals(soprano="A4", alto="F4", tenor="F3", bass="D3"),
    ]

    breakdown = TinyRules().evaluate(events)

    assert breakdown.total_cost == 110
    assert breakdown.by_rule() == {
        "missing_alto": 10.0,
        "parallel_fifths": 100.0,
    }
