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
        path = str(out / f"{k}.mp3")
        done = False
        for rate in (RATE, "-4%", "-8%"):
            for attempt in (1, 2):
                try:
                    await edge_tts.Communicate(text, VOICE, rate=rate).save(path)
                    done = os.path.getsize(path) > 500
                except Exception as e:
                    print("  edge-tts", type(e).__name__, rate, flush=True)
                    await asyncio.sleep(2)
                if done:
                    break
            if done:
                break
        if not done:   # fallback: Google voice (plainer, but always available)
            from gtts import gTTS
            gTTS(text, lang="ru").save(path)
            print("  gTTS fallback", k, flush=True)
        print("ok", k, flush=True)
asyncio.run(main())
