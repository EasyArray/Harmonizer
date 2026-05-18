"""Small example of writing code-first rules with ``RuleSet``."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harmonizer import Note, RuleSet, VerticalEvent


class ChoraleRules(RuleSet):
    ALTO_CENTER = Note.C4

    def alto_in_range(self, ev: VerticalEvent):
        if ev.alto is None:
            return 0
        return abs(self.ALTO_CENTER - ev.alto) * 10

    def no_parallel_fifths(self, ev1: VerticalEvent, ev2: VerticalEvent):
        cost = 0
        fifths1 = [interval for interval in ev1.intervals() if interval.type == 5]
        fifths2 = [interval for interval in ev2.intervals() if interval.type == 5]
        fifths2_by_pair = {interval.voices(): interval for interval in fifths2}

        for interval1 in fifths1:
            interval2 = fifths2_by_pair.get(interval1.voices())
            if interval2 is None:
                continue
            if interval1.motion_to(interval2).is_parallel:
                cost += 100
        return cost


if __name__ == "__main__":
    events = [
        VerticalEvent.from_literals(soprano="C5", alto="G4", tenor="E4", bass="C3"),
        VerticalEvent.from_literals(soprano="D5", alto="A4", tenor="F4", bass="D3"),
        VerticalEvent.from_literals(soprano="E5", alto="G4", tenor="E4", bass="C3"),
    ]

    rules = ChoraleRules()
    breakdown = rules.evaluate(events)
    print("Total cost:", breakdown.total_cost)
    print("By rule:", breakdown.by_rule())
