#!/usr/bin/env python3
"""Make the narrator for promo videos: video/narration.json -> video/narration/<name>.mp3 (free Microsoft neural voice)."""
import asyncio, json, os, pathlib, sys, urllib.request, urllib.error
import edge_tts
ROOT = pathlib.Path(__file__).resolve().parent.parent
VOICE = os.environ.get("NARRATOR_VOICE") or "ru-RU-SvetlanaNeural"
RATE = os.environ.get("NARRATOR_RATE") or "+0%"
EL_KEY = (os.environ.get("ELEVENLABS_API_KEY") or "").strip()
EL_VOICE = (os.environ.get("ELEVENLABS_VOICE_ID") or "").strip() or "hpp4J3VqNfWAUOO0d1Us"   # Bella
def eleven(text, path):
    body = json.dumps({"text": text, "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.2, "use_speaker_boost": True, "speed": 1.0}}).encode()
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{EL_VOICE}?output_format=mp3_44100_128", data=body, method="POST",
        headers={"xi-api-key": EL_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            pathlib.Path(path).write_bytes(r.read())
        return os.path.getsize(path) > 500
    except urllib.error.HTTPError as e:
        print("  ElevenLabs HTTP", e.code, e.read()[:200], flush=True)
    except Exception as e:
        print("  ElevenLabs", type(e).__name__, e, flush=True)
    return False

async def main():
    items = json.loads((ROOT / "video" / "narration.json").read_text(encoding="utf-8"))
    use_el = bool(EL_KEY) and os.environ.get("NARRATOR_ENGINE") == "eleven"
    out = ROOT / "video" / ("narration_el" if use_el else "narration"); out.mkdir(exist_ok=True, parents=True)
    for k, text in items.items():
        path = str(out / f"{k}.mp3")
        done = False
        if use_el:
            done = eleven(text, path)
            if done:
                print("ok (ElevenLabs)", k, flush=True)
                continue
            print("  ElevenLabs failed for", k, "- using the free voice", flush=True)
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
