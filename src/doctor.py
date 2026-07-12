"""Whisper Flow diagnostics: deps, models, services, and macOS permissions.

Run with:  ./run.sh check    (or: uv run src/doctor.py)

Note: permission results apply to the app this is run from (Terminal, iTerm,
etc.) -- macOS grants Microphone / Accessibility / Input Monitoring per-app.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check_accessibility(prompt=False):
    """True/False, or None if the check itself is unavailable."""
    try:
        if prompt:
            from ApplicationServices import (
                AXIsProcessTrustedWithOptions,
                kAXTrustedCheckOptionPrompt,
            )

            return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True}))
        from ApplicationServices import AXIsProcessTrusted

        return bool(AXIsProcessTrusted())
    except Exception:
        return None


def check_input_monitoring(request=False):
    """True/False, or None if the check itself is unavailable."""
    try:
        from Quartz import CGPreflightListenEventAccess, CGRequestListenEventAccess

        ok = bool(CGPreflightListenEventAccess())
        if not ok and request:
            # One-time system prompt; also registers the app in System Settings.
            CGRequestListenEventAccess()
            ok = bool(CGPreflightListenEventAccess())
        return ok
    except Exception:
        return None


def main():
    import time

    import numpy as np
    import requests
    import yaml

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "config.yaml")) as f:
        cfg = yaml.safe_load(f)

    failed = False

    def report(label, good, detail=""):
        nonlocal failed
        mark = {True: "PASS", False: "FAIL", None: "WARN"}[good]
        print(f"[{mark}] {label}" + (f" -- {detail}" if detail else ""))
        if good is False:
            failed = True

    print("Whisper Flow doctor (results apply to the terminal app this runs from)\n")

    # 1. Python deps
    try:
        import mlx_whisper  # noqa: F401
        import pynput  # noqa: F401
        import sounddevice  # noqa: F401

        report("Python deps (mlx-whisper, pynput, sounddevice)", True)
    except Exception as e:
        report("Python deps", False, str(e))

    # 2. Whisper model cache
    repo = cfg["asr_model"].replace("/", "--")
    cache = os.path.expanduser(f"~/.cache/huggingface/hub/models--{repo}")
    if os.path.isdir(cache):
        report(f"Whisper model cached ({cfg['asr_model']})", True)
    else:
        report("Whisper model", None, "not cached yet -- downloads on first use")

    # 3. Microphone capture (also exercises the Recorder fallback path)
    try:
        from audio import Recorder

        rec = Recorder(sample_rate=cfg["sample_rate"])
        rec.start()
        time.sleep(0.4)
        audio = rec.stop()
        if len(audio) == 0:
            report("Microphone capture", False, "no frames captured")
        else:
            rms = float(np.sqrt((audio.astype(np.float64) ** 2).mean()))
            if rms == 0.0:
                report(
                    "Microphone capture",
                    None,
                    "captured pure silence -- Microphone permission may be denied "
                    "for this terminal, or the mic is muted",
                )
            else:
                report("Microphone capture", True, f"{len(audio) / cfg['sample_rate']:.1f}s, signal present")
    except Exception as e:
        report("Microphone capture", False, f"{e} -- grant Microphone permission to this terminal")

    # 4. Ollama server + cleanup model (non-fatal: raw transcription still works)
    base = cfg["cleanup"]["url"].rstrip("/").removesuffix("/api/generate")
    tags_url = f"{base}/api/tags"
    try:
        r = requests.get(tags_url, timeout=2)
        models = [m.get("name", "") for m in r.json().get("models", [])]
        want = cfg["cleanup"]["model"]
        if any(m == want or m.startswith(want) for m in models):
            report("Ollama server + cleanup model", True, want)
        else:
            report("Ollama server", None, f"running, but '{want}' missing -- run: ollama pull {want}")
    except Exception:
        report("Ollama server", None, "not running -- cleanup skipped, raw transcription still works (./run.sh starts it)")

    # 5. macOS permissions
    ax = check_accessibility()
    report(
        "Accessibility permission (needed to paste text)",
        ax,
        "" if ax else "System Settings -> Privacy & Security -> Accessibility -> enable your terminal",
    )
    im = check_input_monitoring()
    report(
        "Input Monitoring permission (needed for the global hotkey)",
        im,
        "" if im else "System Settings -> Privacy & Security -> Input Monitoring -> enable your terminal",
    )

    print()
    if failed:
        print("Fix the FAIL items above. After granting a permission, FULLY QUIT and")
        print("reopen your terminal app -- macOS only applies these on app restart.")
    else:
        print("All critical checks passed. Run ./run.sh and hold the hotkey to dictate.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
