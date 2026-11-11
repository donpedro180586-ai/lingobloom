#!/usr/bin/env python3
"""Generate audio/<hash>.mp3 for every Russian word, letter and example in index.html.

Usage:
    pip install edge-tts
    python scripts/generate_audio.py          # generate missing files
    python scripts/generate_audio.py --list   # only print the texts (no network)

File names use the same FNV-1a hash as h32() in index.html.
"""
import asyncio
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
OUT = ROOT / "audio"
VOICE = "ru-RU-SvetlanaNeural"   # female; alternative: ru-RU-DmitryNeural
RATE = "-10%"                    # a bit slower, easier for learners


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


async def make(text: str, path: pathlib.Path) -> bool:
    import edge_tts

    for attempt in range(4):
        try:
            await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(path))
            if path.exists() and path.stat().st_size > 500:
                return True
        except Exception as e:  # network hiccup, retry
            print(f"  retry {attempt + 1} for {text!r}: {e}")
            await asyncio.sleep(1.5 * (attempt + 1))
    if path.exists():
        path.unlink()
    return False


async def main() -> int:
    texts = collect()
    if "--list" in sys.argv:
        for t in texts:
            print(h32(t), t)
        print(f"{len(texts)} texts")
        return 0

    OUT.mkdir(exist_ok=True)
    failed = []
    for i, t in enumerate(texts, 1):
        f = OUT / f"{h32(t)}.mp3"
        if f.exists() and f.stat().st_size > 500:
            continue
        ok = await make(t, f)
        print(f"[{i}/{len(texts)}] {'ok ' if ok else 'FAIL'} {t}")
        if not ok:
            failed.append(t)
    if failed:
        print("Failed:", failed)
        return 1
    print(f"Done: {len(texts)} files in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
