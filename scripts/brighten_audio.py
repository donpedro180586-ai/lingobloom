#!/usr/bin/env python3
"""One-time (or repeatable) brightening of every clip already in audio/.

    python scripts/brighten_audio.py          # processes audio/*.mp3 that are not done yet
    python scripts/brighten_audio.py --force  # process again (do NOT do this twice in a row: it would boost twice)

Done clips are remembered in audio/_polished.json.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from polish import polish_file  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent.parent / "audio"
LOG = OUT / "_polished.json"


def main() -> int:
    done = set()
    if LOG.exists() and "--force" not in sys.argv:
        done = set(json.loads(LOG.read_text()))
    files = sorted(OUT.glob("*.mp3"))
    n = 0
    for i, f in enumerate(files, 1):
        if f.stem in done:
            continue
        if polish_file(f):
            done.add(f.stem)
            n += 1
        if i % 50 == 0:
            LOG.write_text(json.dumps(sorted(done)))
            print(f"{i}/{len(files)}", flush=True)
    LOG.write_text(json.dumps(sorted(done)))
    print(f"Brightened {n} clips, {len(done)} of {len(files)} are done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
