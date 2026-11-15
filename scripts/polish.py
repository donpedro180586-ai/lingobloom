"""Make the voice clips brighter and a little louder (same voice, only EQ + gentle compression + level).

Needs ffmpeg. If ffmpeg is missing or fails, the clip is simply left unchanged.
Used by generate_audio.py for every new clip and by brighten_audio.py for existing ones.
"""
import array
import os
import pathlib
import shutil
import subprocess

TARGET_RMS_DB = -17.0   # loudness of the speech itself (dBFS): clear, but not squashed
PEAK_CEILING_DB = -1.0  # never louder than this
# Natural voice: only a gentle tilt towards clarity, NO compression, so it does not sound "processed".
EQ = (
    "highpass=f=70,"
    "equalizer=f=3500:t=q:w=1:g=1.5,"          # a little presence
    "highshelf=f=9000:g=1.5"                   # a little air
)
EQ_BOOST = EQ  # kept for old imports


def _pcm(path, af=None):
    cmd = ["ffmpeg", "-v", "error", "-i", str(path)]
    if af:
        cmd += ["-af", af]
    cmd += ["-ac", "1", "-ar", "44100", "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True, timeout=60).stdout
    a = array.array("h")
    a.frombytes(raw[: len(raw) // 2 * 2])
    return a


def _levels(a):
    """(rms of the speech parts in dB, peak in dB), 0 dB = full scale."""
    if len(a) < 2048:
        return None
    peak = max(max(a), -min(a)) or 1
    thr = peak * 0.02
    act = [x for x in a if abs(x) > thr]
    rms = (sum(x * x for x in act) / len(act)) ** 0.5
    db = lambda v: 20 * __import__("math").log10(max(v, 1e-9) / 32768)
    return db(rms), db(peak)


def polish_file(path, eq=None) -> bool:
    """Replace the mp3 at `path` with a brighter version. Returns True if changed."""
    if not shutil.which("ffmpeg"):
        return False
    eq = eq or EQ
    path = pathlib.Path(path)
    tmp = path.with_name(path.stem + ".polish.mp3")
    try:
        lv = _levels(_pcm(path, eq))
        if not lv:
            return False
        rms, peak = lv
        gain = min(TARGET_RMS_DB - rms, PEAK_CEILING_DB - peak)
        gain = max(min(gain, 12.0), -12.0)
        af = f"{eq},volume={gain:.2f}dB,alimiter=limit=0.89:level=disabled"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(path), "-af", af, "-ac", "1", "-ar", "44100",
             "-c:a", "libmp3lame", "-b:a", "128k", str(tmp)],
            check=True, timeout=60,
        )
        if tmp.exists() and tmp.stat().st_size > 500:
            os.replace(tmp, path)
            return True
    except Exception as e:  # keep the original clip
        print(f"  polish skipped for {path.name}: {type(e).__name__}", flush=True)
    finally:
        if tmp.exists():
            tmp.unlink()
    return False
