#!/usr/bin/env python3
"""Make the narrator for promo videos: video/narration.json -> video/narration/<name>.mp3 (free Microsoft neural voice)."""
import asyncio, json, os, pathlib, sys
import edge_tts
ROOT = pathlib.Path(__file__).resolve().parent.parent
VOICE = os.environ.get("NARRATOR_VOICE") or "ru-RU-SvetlanaNeural"
RATE = os.environ.get("NARRATOR_RATE") or "+0%"
async def main():
    items = json.loads((ROOT / "video" / "narration.json").read_text(encoding="utf-8"))
    out = ROOT / "video" / "narration"; out.mkdir(exist_ok=True, parents=True)
    for k, text in items.items():
        await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(out / f"{k}.mp3"))
        print("ok", k, flush=True)
asyncio.run(main())
