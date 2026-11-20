from harmonizer.attack.dataset import assign_groups
import pytest


def piece(source, number, title=None, melody=None):
  return {"source": source, "riemenschneider": number, "title_group": title or source,
          "melody_group": melody or source, "sha256": source}


def test_new_family_cannot_pull_previous_training_into_development():
  pieces = [piece("old", 1, title="shared"), piece("new", 18, title="shared"), piece("other", 21)]
  assign_groups(pieces, [{"source": "old", "split": "train"}])
  assert [p["split"] for p in pieces] == ["train", "train", "development"]
  assert pieces[0]["family_group"] == pieces[1]["family_group"]


def test_transitive_leakage_is_blocked():
  pieces = [piece("old-train", 1, title="x"), piece("bridge", 2, title="x", melody="y"),
            piece("old-dev", 3, melody="y")]
  with pytest.raises(ValueError, match="bridges"):
    assign_groups(pieces, [{"source": "old-train", "split": "train"},
                          {"source": "old-dev", "split": "development"}])
