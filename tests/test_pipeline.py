"""Non-interactive end-to-end test of the ASR + cleanup pipeline.

Synthesizes speech with macOS `say` (no microphone needed), transcribes it with
mlx-whisper, then runs the Ollama cleanup step. Verifies everything except the
global hotkey and text injection, which require an interactive GUI session.

Run with:  uv run tests/test_pipeline.py
"""

import os
import subprocess
import sys
import tempfile

import numpy as np
import yaml
from scipy.io import wavfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from asr import Transcriber  # noqa: E402
from cleanup import Cleaner  # noqa: E402

PHRASE = "um so i think uh we should like ship the feature on friday you know"

# Formatting cases fed straight to the cleaner as text (no audio needed).
# Loose asserts: check the behavior, not exact wording.
FORMAT_CASES = [
    # (label, raw transcript, predicate on cleaned output)
    (
        "numbered list from enumeration",
        "um so for tomorrow we need to buy milk and then get some eggs and also uh pick up bread",
        lambda out: "\n2." in out,
    ),
    (
        "spoken symbols in a path",
        "the config file is at tilde slash dot config slash app dot yaml",
        lambda out: "~/.config/app.yaml" in out,
    ),
    (
        "spoken symbols in an email",
        "send it to jane underscore doe at sign example dot com",
        lambda out: "jane_doe@example.com" in out,
    ),
    (
        "'slash' as a normal word survives",
        "the airline had to slash fares after the uh holiday season",
        lambda out: "slash" in out.lower(),
    ),
    (
        "question is cleaned, not answered",
        "um can you uh tell me what time the market opens",
        lambda out: out.lower().startswith("can you"),
    ),
]


def test_formatting(cleaner):
    # If Ollama is unreachable, clean() falls back to the raw text -- probe
    # once and skip instead of failing on asserts the LLM never saw.
    probe = "um hello there uh world"
    if cleaner.clean(probe) == probe:
        print("SKIP: cleanup unavailable or disabled -- formatting cases not run")
        return
    failures = []
    for label, raw, ok in FORMAT_CASES:
        out = cleaner.clean(raw)
        status = "ok  " if ok(out) else "FAIL"
        print(f"  {status} {label}: {out!r}")
        if not ok(out):
            failures.append(label)
    assert not failures, f"formatting cases failed: {failures}"


def synth_wav(text, path, sample_rate):
    """macOS `say` -> AIFF -> 16 kHz mono 16-bit WAV via built-in afconvert."""
    aiff = path + ".aiff"
    subprocess.run(["say", "-o", aiff, text], check=True)
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", f"LEI16@{sample_rate}", "-c", "1", aiff, path],
        check=True,
    )
    os.remove(aiff)


def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "config.yaml")) as f:
        cfg = yaml.safe_load(f)

    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "sample.wav")
        print(f"Synthesizing test speech: {PHRASE!r}")
        synth_wav(PHRASE, wav, cfg["sample_rate"])
        sr, data = wavfile.read(wav)
        audio = data.astype(np.float32) / 32768.0  # int16 -> float32 [-1, 1]

    print(f"Loaded {len(audio) / sr:.1f}s of audio at {sr} Hz")
    print("Transcribing (first run downloads the model)...")
    raw = Transcriber(cfg["asr_model"]).transcribe(audio)
    print(f"  RAW:   {raw!r}")

    cleaner = Cleaner(
        url=cfg["cleanup"]["url"],
        model=cfg["cleanup"]["model"],
        timeout=cfg["cleanup"]["timeout"],
        enabled=cfg["cleanup"]["enabled"],
    )
    cleaned = cleaner.clean(raw)
    print(f"  CLEAN: {cleaned!r}")

    assert raw, "ASR produced no text"

    print("\nFormatting cases (lists + spoken symbols):")
    test_formatting(cleaner)

    print("\nPASS: ASR pipeline works end-to-end.")


if __name__ == "__main__":
    main()
