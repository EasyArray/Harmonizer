"""Build a larger development manifest; preserve all previously exposed splits."""
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import music21
from music21 import converter, corpus, key, stream
from .benchmark import validate_manifest
from .import_score import from_music21
from .score import Key, Pitch


def spelling(pitch):
  return pitch.name.replace("-", "b") + str(pitch.octave if pitch.octave is not None else 4)


def assign_groups(pieces, previous):
  """Join title, melody and identical-source groups before assigning splits."""
  parents = list(range(len(pieces)))
  def root(i):
    while parents[i] != i:
      parents[i] = parents[parents[i]]
      i = parents[i]
    return i
  for field in ("title_group", "melody_group", "sha256"):
    seen = {}
    for i, p in enumerate(pieces):
      if p[field] in seen:
        parents[root(i)] = root(seen[p[field]])
      else:
        seen[p[field]] = i
  groups = defaultdict(list)
  for i, p in enumerate(pieces):
    groups[root(i)].append(p)
  old = {p["source"]: p["split"] for p in previous}
  for members in groups.values():
    prior = {old[p["source"]] for p in members if p["source"] in old}
    if len(prior) > 1:
      raise ValueError("New grouping bridges previously exposed splits; quarantine and review")
    split = next(iter(prior)) if prior else (
      "development" if min(p["riemenschneider"] for p in members) % 3 == 0 else "train")
    identity = sha256("|".join(sorted(p["source"] for p in members)).encode()).hexdigest()[:16]
    for p in members:
      p.update(split=split, family_group=identity)
  return pieces


def build(limit=64, previous_path="experiments/bach-development.json"):
  previous = json.loads(Path(previous_path).read_text())
  catalog = corpus.chorales.ChoraleListRKBWV().byRiemenschneider
  pieces, excluded, audit, seen = [], [], [], set()
  for number in range(1, limit + 1):
    info = catalog[number]
    source = f"bach/bwv{info['bwv']}.mxl"
    try:
      path = Path(corpus.getWork(source))
      digest = sha256(path.read_bytes()).hexdigest()
      if digest in seen:
        excluded.append({"source": source, "reason": "Duplicate source content"})
        continue
      raw = converter.parse(path)
      if len(raw.parts) != 4:
        raise ValueError("Exactly four SATB parts required")
      encoded = next(iter(raw.parts[0].recurse().getElementsByClass(key.Key)), None)
      if encoded is None:
        raise ValueError("No explicitly encoded major/minor key")
      declared = Key(Pitch.parse(spelling(encoded.tonic)), encoded.mode, "encoded; not verified tonic")
      score = from_music21(raw, declared)
      soprano = [n.pitch.semitones for n in score.notes if n.voice.name == "S"]
      melody = sha256(json.dumps([p - soprano[0] for p in soprano]).encode()).hexdigest()
      title = info["title"]
      piece = {"source": source, "riemenschneider": number, "title": title,
        "title_group": re.sub("[^a-z]", "", title.lower()), "melody_group": melody,
        "tonic": str(declared.tonic), "mode": declared.mode, "sha256": digest}
      outer = stream.Score()
      outer.insert(0, raw.parts[0])
      outer.insert(0, raw.parts[3])
      estimate = outer.analyze("key")
      alternative = {"tonic": spelling(estimate.tonic), "mode": estimate.mode}
      disagreement = (estimate.tonic.pitchClass, estimate.mode) != (encoded.tonic.pitchClass, encoded.mode)
      piece["outer_key_estimate"] = alternative
      audit.append({"source": source, "encoded": {"tonic": piece["tonic"], "mode": piece["mode"]},
                    "outer_estimate": alternative, "disagreement": disagreement,
                    "final_bass": str([n for n in score.notes if n.voice.name == "B"][-1].pitch)})
      pieces.append(piece)
      seen.add(digest)
    except (ValueError, TypeError, IndexError) as error:
      excluded.append({"source": source, "reason": str(error)})
  missing = {p["source"] for p in previous["pieces"]} - {p["source"] for p in pieces}
  if missing:
    raise ValueError(f"Previously included pieces unexpectedly missing: {sorted(missing)}")
  assign_groups(pieces, previous["pieces"])
  manifest = {"version": 2, "music21_version": music21.__version__,
    "selection": f"First {limit} Riemenschneider entries; same first/middle/last single and joint attack selection as round 001.",
    "grouping": "Connected components of normalized titles, transposition-invariant full soprano sequences, and content hashes. Old train/development assignments preserved. New families assigned development iff smallest Riemenschneider number is divisible by three. Related variants may remain undetected.",
    "pieces": pieces, "excluded": excluded,
    "test_policy": "Expanded development only. No final test partition selected or opened.",
    "key_audit": audit}
  validate_manifest(manifest)
  return manifest
