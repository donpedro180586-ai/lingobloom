# Learn English

Static site (GitHub Pages) for Russian speakers who learn English: alphabet, 11 lessons,
games, music and sound effects. The interface is in Russian, the learned content is English.

Word audio lives in `audio/` and is generated automatically by the "Generate word audio"
GitHub Action (see `.github/workflows/audio.yml`). It runs when `index.html` changes, and
manually from the Actions tab, where you can also choose the voice and speed.

Local generation: `pip install edge-tts gTTS && python scripts/generate_audio.py`

## ElevenLabs voice (optional)

Add the repository secret `ELEVENLABS_API_KEY` (Settings -> Secrets and variables -> Actions).
The generator then records every word with the ElevenLabs voice Roger (stability 0.5, similarity 0.75)
instead of the free voices. Optional env vars: `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL`.
