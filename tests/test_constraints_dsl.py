import json

import pytest

from harmonizer import (
    A,
    T,
    avoid_voice_crossing,
    cover_chord_tones,
    prefer_range,
    rulebook,
)


def test_rulebook_serializes_validated_plain_data():
    rules = rulebook(
        "Small Test Rules",
        cover_chord_tones(root=500, third=500, fifth=80, seventh=300),
        prefer_range(
            alto="c4",
            tenor="G3",
            cost_per_semitone=3,
            free_semitones=10,
        ),
        metadata={"voices": (A, T)},
    )

    payload = json.loads(rules.to_json())

    assert payload["name"] == "Small Test Rules"
    assert payload["rules"][0]["kind"] == "cover_chord_tones"
    assert payload["rules"][1]["params"]["centers"] == {
        "alto": "C4",
        "tenor": "G3",
    }
    assert payload["metadata"]["voices"] == ["alto", "tenor"]


def test_invalid_rule_parameters_fail_early():
    with pytest.raises(ValueError, match="nonnegative"):
        avoid_voice_crossing(penalty=-1)

    with pytest.raises(ValueError, match="pitch literal"):
        prefer_range(alto="middle C", cost_per_semitone=3)
