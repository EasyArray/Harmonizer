"""Starter declarative rulebook used by the notebooks and examples."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harmonizer import (
    A,
    ALL_VOICE_PAIRS,
    B,
    S,
    T,
    avoid_parallel_perfects,
    avoid_similar_motion_into_perfects,
    avoid_voice_crossing,
    cover_chord_tones,
    prefer_doublings,
    prefer_independent_motion,
    prefer_melodic_intervals,
    prefer_range,
    prepare_leaps,
    recover_leaps,
    rulebook,
)


STARTER_RULES = rulebook(
    "Starter Chorale Constraints",
    cover_chord_tones(
        root=500,
        third=500,
        fifth=80,
        seventh=300,
        ninth=150,
        explicit=500,
        other=150,
        unfigured_scale=0.25,
        chromatic_same_letter_ok=True,
        notes=(
            "Role-aware coverage: roots/thirds matter most, fifths are cheap to omit, "
            "and unfigured default 5/3 events are downweighted because they often behave "
            "like passing bass motion in this corpus."
        ),
    ),
    avoid_voice_crossing(
        penalty=100,
        allow_equal=True,
        notes="Equality is allowed. Only strict crossing is penalized.",
    ),
    prefer_range(
        alto="C4",
        tenor="G3",
        cost_per_semitone=3,
        free_semitones=10,
        notes=(
            "Soft tessitura nudge: ordinary Bach alto/tenor placements should not "
            "dominate the debug costs."
        ),
    ),
    prefer_doublings(
        root=0,
        fifth=20,
        third=50,
        seventh=70,
    ),
    prefer_melodic_intervals(
        voices=[A, T],
        unison=0,
        step=0,
        third=5,
        fourth=10,
        fifth=20,
        sixth=35,
        seventh=50,
        octave_or_larger=70,
    ),
    recover_leaps(
        voices=[A, T],
        leap_gt="third",
        require="step_opposite",
        penalty=10,
    ),
    prepare_leaps(
        voices=[A, T],
        leap_gt="third",
        require="step_opposite",
        penalty=10,
        enabled=False,
        notes="Included in the ruleset shape, but disabled by default because it is still underspecified.",
    ),
    avoid_parallel_perfects(
        pairs=ALL_VOICE_PAIRS,
        fifth=100,
        octave=100,
        unison=100,
    ),
    avoid_similar_motion_into_perfects(
        pairs=[(S, B)],
        fifth=50,
        octave=50,
        unison=50,
        require_upper_leap=True,
        notes=(
            "Direct perfects are tracked by default only in the outer voices, and only "
            "when the upper voice leaps."
        ),
    ),
    prefer_independent_motion(
        pairs=ALL_VOICE_PAIRS,
        contrary=0,
        oblique=0,
        similar=5,
        ignore_if_perfect_rule_applies=True,
    ),
    description=(
        "A declarative, notebook-friendly starter constraint set for alto/tenor "
        "realization over soprano plus figured bass."
    ),
)


if __name__ == "__main__":
    print(STARTER_RULES.to_json())
