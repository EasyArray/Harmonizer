from harmonizer import (
    analyze_events,
    avoid_voice_crossing,
    prefer_range,
    rulebook,
    VerticalEvent,
)


def test_analyze_events_reports_rule_columns_and_totals():
    rules = rulebook(
        "Cost Smoke Test",
        avoid_voice_crossing(penalty=10),
        prefer_range(alto="C4", cost_per_semitone=2, free_semitones=0),
    )
    events = [
        VerticalEvent.from_literals(
            soprano="C4",
            alto="E4",
            tenor="C3",
            bass="C3",
            index=0,
            event_strength=1.0,
        )
    ]

    analysis = analyze_events(events, rules, score_scope="all")

    assert analysis.rule_columns == ("avoid_voice_crossing", "prefer_range:alto")
    assert analysis.rows[0]["avoid_voice_crossing"] == 10.0
    assert analysis.rows[0]["prefer_range:alto"] == 8.0
    assert analysis.rows[0]["total_cost"] == 18.0
    assert analysis.totals_by_rule() == {
        "avoid_voice_crossing": 10.0,
        "prefer_range:alto": 8.0,
    }
