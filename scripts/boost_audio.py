#!/usr/bin/env python3
"""Second brightening pass for clips that were already polished once (audio/_boosted.json remembers which)."""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from polish import polish_file, EQ_BOOST  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent.parent / "audio"
LOG = OUT / "_boosted.json"
done = set(json.loads(LOG.read_text())) if LOG.exists() else set()
n = 0
for i, f in enumerate(sorted(OUT.glob("*.mp3")), 1):
    if f.stem in done:
        continue
    if polish_file(f, eq=EQ_BOOST):
        done.add(f.stem); n += 1
    if i % 100 == 0:
        print(i, flush=True)
LOG.write_text(json.dumps(sorted(done)))
print("boosted", n, "of", len(done))
