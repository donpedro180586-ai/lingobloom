#!/usr/bin/env python3
"""Generate audio/<hash>.mp3 for every English word, letter name and example in index.html.

Usage:
    pip install edge-tts gTTS
    python scripts/generate_audio.py          # generate what is missing / outdated
    python scripts/generate_audio.py --list   # only print the texts (no network)

Voice and speed come from TTS_VOICE / TTS_RATE (the "Run workflow" form on GitHub).
If they change, every file is re-created. Progress is stored in audio/_meta.json, so a
run that fails half way can simply be started again and continues where it stopped.
If the Microsoft voice (edge-tts) is not reachable, Google TTS (gTTS) is used instead.

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

DEFAULT_VOICE = "en-US-AriaNeural"   # also: en-US-GuyNeural, en-GB-SoniaNeural, en-GB-RyanNeural
DEFAULT_RATE = "-10%"                # slower = easier for learners
FORCE = "--force" in sys.argv or os.environ.get("FORCE", "").lower() == "true"


def h32(s: str) -> str:
    h = 0x811C9DC5
    for ch in s:
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return format(h, "08x")


def collect() -> list[str]:
    src = INDEX.read_text(encoding="utf-8")
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', src, re.S)
    data = json.loads(m.group(1))
    texts = []
    for a in data["alpha"]:          # [letter, name_ru, say, word, word_ru]
        texts += [a[2], a[3]]
    for t in data["topics"].values():
        for w in t["words"]:         # [en, transcription, ru]
            texts.append(w[0])
    for sentence, _ru in data["examples"].values():
        texts.append(sentence)
    texts.append("Hello, how are you?")  # used by the sound test
    seen, out = set(), []
    for t in texts:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def load_meta():
    if META.exists():
        try:
            return json.loads(META.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def save_meta(meta: dict) -> None:
    OUT.mkdir(exist_ok=True)
    META.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


async def make_edge(text, path, voice, rate) -> bool:
    tmp = path.with_suffix(".tmp")
    for attempt in range(1, 3):
        try:
            import edge_tts

            await asyncio.wait_for(
                edge_tts.Communicate(text, voice, rate=rate).save(str(tmp)), timeout=30
            )
            if tmp.exists() and tmp.stat().st_size > 500:
                os.replace(tmp, path)
                return True
        except Exception as e:
            print(f"  edge retry {attempt} for {text!r}: {type(e).__name__}: {e}", flush=True)
        await asyncio.sleep(2 * attempt)
    if tmp.exists():
        tmp.unlink()
    return False


def make_gtts(text, path) -> bool:
    try:
        from gtts import gTTS

        tmp = path.with_suffix(".tmp")
        gTTS(text, lang="en", tld="com").save(str(tmp))
        if tmp.exists() and tmp.stat().st_size > 500:
            os.replace(tmp, path)
            return True
    except Exception as e:
        print(f"  gTTS failed for {text!r}: {type(e).__name__}: {e}", flush=True)
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

    use_gtts, edge_fails, failed = False, 0, []
    for i, t in enumerate(texts, 1):
        h = h32(t)
        f = OUT / f"{h}.mp3"
        if h in done and f.exists() and f.stat().st_size > 500:
            continue
        ok = False
        if not use_gtts:
            ok = await make_edge(t, f, voice, rate)
            edge_fails = 0 if ok else edge_fails + 1
            if edge_fails >= 3:
                use_gtts = True
                print("Microsoft voice is not reachable, switching to Google TTS", flush=True)
        if not ok and use_gtts:
            ok = await asyncio.to_thread(make_gtts, t, f)
            await asyncio.sleep(0.4)
        print(f"[{i}/{len(texts)}] {'ok  ' if ok else 'FAIL'} {t}", flush=True)
        if ok:
            done.add(h)
        else:
            failed.append(t)
        if i % 10 == 0:
            save_meta({"voice": voice, "rate": rate, "done": sorted(done)})

    if failed and use_gtts:  # words that failed before the switch to Google TTS
        print(f"Retrying {len(failed)} word(s) with Google TTS", flush=True)
        for t in list(failed):
            if await asyncio.to_thread(make_gtts, t, OUT / f"{h32(t)}.mp3"):
                done.add(h32(t))
                failed.remove(t)
                print(f"  ok   {t}", flush=True)

    keep = {h32(t) for t in texts}
    for p in OUT.glob("*.mp3"):  # remove files that are no longer used
        if p.stem not in keep:
            p.unlink()

    save_meta({"voice": voice, "rate": rate, "done": sorted(done & keep)})
    if failed:
        print(f"{len(failed)} failed (run the workflow again to retry them):", failed)
        return 1
    print(f"Done: {len(texts)} files, voice={voice} rate={rate}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
