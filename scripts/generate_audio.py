#!/usr/bin/env python3
"""Generate audio/<hash>.mp3 for every English word, letter name and example in index.html.

Usage:
    pip install edge-tts gTTS
    python scripts/generate_audio.py          # generate what is missing / outdated
    python scripts/generate_audio.py --list   # only print the texts (no network)

Engines, in order of preference:
  1. ElevenLabs  - used when the ELEVENLABS_API_KEY secret/env var is set (voice Bella by default)
  2. edge-tts    - Microsoft neural voices (TTS_VOICE / TTS_RATE)
  3. gTTS        - Google, last resort

If the engine, voice or speed changes, every file is re-created. Progress is stored in
audio/_meta.json, so a run that fails half way can simply be started again.

File names use the same FNV-1a hash as h32() in index.html.
"""
import asyncio
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
OUT = ROOT / "audio"
META = OUT / "_meta.json"

DEFAULT_VOICE = "en-US-AriaNeural"   # also: en-US-GuyNeural, en-GB-SoniaNeural, en-GB-RyanNeural
DEFAULT_RATE = "-10%"                # slower = easier for learners
FORCE = "--force" in sys.argv or os.environ.get("FORCE", "").lower() == "true"

EL_KEY = (os.environ.get("ELEVENLABS_API_KEY") or "").strip()
EL_VOICE = (os.environ.get("ELEVENLABS_VOICE_ID") or "").strip() or "hpp4J3VqNfWAUOO0d1Us"  # Bella
EL_MODEL = (os.environ.get("ELEVENLABS_MODEL") or "").strip() or "eleven_flash_v2_5"   # half the credits of multilingual_v2
EL_BASE = (os.environ.get("ELEVENLABS_BASE_URL") or "").strip() or "https://api.elevenlabs.io"
EL_STABILITY, EL_SIMILARITY, EL_SPEED = 0.5, 0.8, 0.95   # same settings as the Worker (/tts)


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


def _store(tmp: pathlib.Path, path: pathlib.Path) -> bool:
    if tmp.exists() and tmp.stat().st_size > 500:
        os.replace(tmp, path)   # only now the old file is replaced
        return True
    if tmp.exists():
        tmp.unlink()
    return False


def make_eleven(text, path) -> bool:
    url = f"{EL_BASE}/v1/text-to-speech/{EL_VOICE}?output_format=mp3_44100_128"
    body = json.dumps({
        "text": text,
        "model_id": EL_MODEL,
        "voice_settings": {"stability": EL_STABILITY, "similarity_boost": EL_SIMILARITY, "speed": EL_SPEED},
    }).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"xi-api-key": EL_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    tmp = path.with_suffix(".tmp")
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                tmp.write_bytes(r.read())
            if _store(tmp, path):
                return True
        except urllib.error.HTTPError as e:
            detail = e.read()[:200].decode("utf-8", "replace")
            print(f"  ElevenLabs HTTP {e.code} for {text!r}: {detail}", flush=True)
            if e.code in (401, 402, 403, 422):   # key / plan / quota problem: retrying will not help
                return False
        except Exception as e:
            print(f"  ElevenLabs error for {text!r}: {type(e).__name__}: {e}", flush=True)
        time.sleep(2 * attempt)
    return False


async def make_edge(text, path, voice, rate) -> bool:
    tmp = path.with_suffix(".tmp")
    for attempt in range(1, 3):
        try:
            import edge_tts

            await asyncio.wait_for(
                edge_tts.Communicate(text, voice, rate=rate).save(str(tmp)), timeout=30
            )
            if _store(tmp, path):
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
        return _store(tmp, path)
    except Exception as e:
        print(f"  gTTS failed for {text!r}: {type(e).__name__}: {e}", flush=True)
    return False


class Engines:
    def __init__(self):
        self.eleven = bool(EL_KEY)
        self.gtts = False
        self.eleven_fails = 0
        self.edge_fails = 0


async def synth(t, f, voice, rate, E: Engines) -> bool:
    if E.eleven:
        ok = await asyncio.to_thread(make_eleven, t, f)
        E.eleven_fails = 0 if ok else E.eleven_fails + 1
        if E.eleven_fails >= 3:
            E.eleven = False
            print("ElevenLabs is not working (check the key, plan limit or voice id) "
                  "-> falling back to the free voices", flush=True)
        await asyncio.sleep(0.2)
        return ok
    if not E.gtts:
        ok = await make_edge(t, f, voice, rate)
        E.edge_fails = 0 if ok else E.edge_fails + 1
        if E.edge_fails >= 3:
            E.gtts = True
            print("Microsoft voice is not reachable, switching to Google TTS", flush=True)
        if ok:
            return True
        if not E.gtts:
            return False
    ok = await asyncio.to_thread(make_gtts, t, f)
    await asyncio.sleep(0.4)
    return ok


async def main() -> int:
    texts = collect()
    if "--list" in sys.argv:
        for t in texts:
            print(h32(t), t)
        print(f"{len(texts)} texts")
        return 0

    OUT.mkdir(exist_ok=True)
    meta = load_meta()
    mv = (meta or {}).get("voice") or ""
    voice = os.environ.get("TTS_VOICE") or (mv if mv and not mv.startswith("elevenlabs:") else "") or DEFAULT_VOICE
    rate = os.environ.get("TTS_RATE") or (meta or {}).get("rate") or DEFAULT_RATE
    label = f"elevenlabs:{EL_VOICE}:{EL_MODEL}" if EL_KEY else voice
    if FORCE or not meta or meta.get("voice") != label or meta.get("rate") != rate:
        meta = {"voice": label, "rate": rate, "done": []}
        print(f"Re-creating all files: engine={label} rate={rate}", flush=True)
    done = set(meta["done"])

    E = Engines()
    failed = []
    for i, t in enumerate(texts, 1):
        h = h32(t)
        f = OUT / f"{h}.mp3"
        if h in done and f.exists() and f.stat().st_size > 500:
            continue
        ok = await synth(t, f, voice, rate, E)
        print(f"[{i}/{len(texts)}] {'ok  ' if ok else 'FAIL'} {t}", flush=True)
        if ok:
            done.add(h)
        else:
            failed.append(t)
        if i % 10 == 0:
            save_meta({"voice": label, "rate": rate, "done": sorted(done)})

    if failed:  # one more try, now with whichever engine is active
        print(f"Retrying {len(failed)} item(s)", flush=True)
        for t in list(failed):
            if await synth(t, OUT / f"{h32(t)}.mp3", voice, rate, E):
                done.add(h32(t))
                failed.remove(t)
                print(f"  ok   {t}", flush=True)

    keep = {h32(t) for t in texts}
    for p in OUT.glob("*.mp3"):  # remove files that are no longer used
        if p.stem not in keep:
            p.unlink()

    fell_back = bool(EL_KEY) and not E.eleven
    if fell_back:  # some files come from a free voice: a later run with a working key re-creates them
        label = voice
    save_meta({"voice": label, "rate": rate, "done": sorted(done & keep)})
    if fell_back:
        print("WARNING: ElevenLabs did not work, free voices were used instead.", flush=True)
        return 1
    if failed:
        print(f"{len(failed)} failed (run the workflow again to retry them):", failed)
        return 1
    print(f"Done: {len(texts)} files, engine={label} rate={rate}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
