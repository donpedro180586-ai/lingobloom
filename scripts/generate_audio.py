#!/usr/bin/env python3
"""Generate audio/<hash>.mp3 for every Russian word, letter and example in index.html.

Usage:
    pip install edge-tts
    python scripts/generate_audio.py          # generate what is missing / outdated
    python scripts/generate_audio.py --list   # only print the texts (no network)

Voice and speed come from TTS_VOICE / TTS_RATE (the "Run workflow" form on GitHub).
If they change, every file is re-created. Progress is stored in audio/_meta.json, so a
run that fails half way can simply be started again and it continues where it stopped.

File names use the same FNV-1a hash as h32() in index.html.
"""
import asyncio
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
OUT = ROOT / "audio"
META = OUT / "_meta.json"

DEFAULT_VOICE = "ru-RU-SvetlanaNeural"   # female; male: ru-RU-DmitryNeural
DEFAULT_RATE = "-10%"                    # slower = easier for learners
FORCE = "--force" in sys.argv or os.environ.get("FORCE", "").lower() == "true"


def h32(s: str) -> str:
    h = 0x811C9DC5
    for ch in s:
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return format(h, "08x")


def collect() -> list[str]:
    src = INDEX.read_text(encoding="utf-8")
    texts = []

    alpha = re.search(r"const ALPHA=\[(.*?)\n\];", src, re.S).group(1)
    for letter, _snd, word, _en in re.findall(
        r'\["([^"]+)","([^"]+)","([^"]+)","([^"]+)"\]', alpha
    ):
        texts.append(letter.split(" ")[0])  # the letter itself
        texts.append(word)                  # example word

    topics = re.search(r"const TOPICS=\{(.*?)\n\};", src, re.S).group(1)
    for ru, _tr, _en in re.findall(r'\["([^"]+)","([^"]*)","([^"]*)"\]', topics):
        texts.append(ru)

    ex = re.search(r"const EX=\{(.*?)\n\};", src, re.S).group(1)
    for ru_phrase, _en in re.findall(r'\["([^"]+)","([^"]+)"\]', ex):
        texts.append(ru_phrase)

    texts.append("Привет, как дела?")  # used by the sound test

    seen, out = set(), []
    for t in texts:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def load_meta() -> dict | None:
    if META.exists():
        try:
            return json.loads(META.read_text(encoding="utf-8"))
        except Exception:
            pass
    existing = [p.stem for p in OUT.glob("*.mp3")] if OUT.exists() else []
    if existing:  # made by the very first run, with the default settings
        return {"voice": DEFAULT_VOICE, "rate": DEFAULT_RATE, "done": existing}
    return None


def save_meta(meta: dict) -> None:
    OUT.mkdir(exist_ok=True)
    META.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


async def make(text: str, path: pathlib.Path, voice: str, rate: str) -> bool:
    import edge_tts

    tmp = path.with_suffix(".tmp")
    for attempt in range(1, 6):
        try:
            await asyncio.wait_for(
                edge_tts.Communicate(text, voice, rate=rate).save(str(tmp)), timeout=40
            )
            if tmp.exists() and tmp.stat().st_size > 500:
                os.replace(tmp, path)  # only now the old file is replaced
                return True
        except Exception as e:  # network hiccup / throttling: wait and retry
            print(f"  retry {attempt} for {text!r}: {type(e).__name__}: {e}", flush=True)
        await asyncio.sleep(2 * attempt)
    if tmp.exists():
        tmp.unlink()
    return False


async def main() -> int:
    texts = collect()
    if "--list" in sys.argv:
        for t in texts:
            print(h32(t), t)
        print(f"{len(texts)} texts")
        return 0

    OUT.mkdir(exist_ok=True)
    meta = load_meta()
    voice = os.environ.get("TTS_VOICE") or (meta or {}).get("voice") or DEFAULT_VOICE
    rate = os.environ.get("TTS_RATE") or (meta or {}).get("rate") or DEFAULT_RATE
    if FORCE or not meta or meta.get("voice") != voice or meta.get("rate") != rate:
        meta = {"voice": voice, "rate": rate, "done": []}
        print(f"Re-creating all files: voice={voice} rate={rate}", flush=True)
    done = set(meta["done"])

    failed = []
    for i, t in enumerate(texts, 1):
        h = h32(t)
        f = OUT / f"{h}.mp3"
        if h in done and f.exists() and f.stat().st_size > 500:
            continue
        ok = await make(t, f, voice, rate)
        print(f"[{i}/{len(texts)}] {'ok  ' if ok else 'FAIL'} {t}", flush=True)
        if ok:
            done.add(h)
            await asyncio.sleep(0.3)
        else:
            failed.append(t)
        if i % 10 == 0:
            save_meta({"voice": voice, "rate": rate, "done": sorted(done)})

    save_meta({"voice": voice, "rate": rate, "done": sorted(done)})
    if failed:
        print(f"{len(failed)} failed (run the workflow again to retry them):", failed)
        return 1
    print(f"Done: {len(texts)} files, voice={voice} rate={rate}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
