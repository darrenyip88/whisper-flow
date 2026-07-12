"""Whisper Flow -- a local Wispr Flow clone.

Pipeline: hold hotkey -> record mic -> local Whisper (mlx) -> Ollama LLM cleanup
-> auto-type into the active app.

Run with:  ./run.sh                       menu bar indicator (recommended)
           ./run.sh check                 diagnostics (permissions, mic, models)
           uv run src/flow.py --no-ui     console only
           uv run src/flow.py --debug     print every key event (hotkey debug)
"""

import argparse
import os
import signal
import subprocess
import threading
import time

import numpy as np
import yaml

import doctor
from asr import Transcriber
from audio import Recorder
from cleanup import Cleaner
from hotkey import HotkeyListener
from inject import Injector

KEY_LABELS = {
    "alt_r": "right ⌥ Option",
    "alt_l": "left ⌥ Option",
    "alt": "⌥ Option",
    "cmd_r": "right ⌘ Cmd",
    "cmd_l": "left ⌘ Cmd",
    "ctrl_r": "right ⌃ Ctrl",
    "shift_r": "right ⇧ Shift",
    "f13": "F13",
}
SOUND_FILES = {"start": "Tink", "done": "Pop", "error": "Basso"}


def load_config():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "config.yaml")) as f:
        return yaml.safe_load(f)


class Flow:
    """Pipeline controller; also the shared state the menu bar UI reads."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.phase = "idle"  # idle | recording | processing
        self.last_text = ""
        self.warning = ""
        self._phase_lock = threading.Lock()
        self.sounds_on = cfg.get("indicator", {}).get("sounds", True)
        self.recorder = Recorder(sample_rate=cfg["sample_rate"])
        self.transcriber = Transcriber(cfg["asr_model"], language=cfg.get("language"))
        self.cleaner = Cleaner(
            url=cfg["cleanup"]["url"],
            model=cfg["cleanup"]["model"],
            timeout=cfg["cleanup"]["timeout"],
            enabled=cfg["cleanup"]["enabled"],
        )
        self.injector = Injector(
            restore_clipboard=cfg["inject"]["restore_clipboard"],
            paste_delay=cfg["inject"]["paste_delay"],
            method=cfg["inject"].get("method", "paste"),
        )

    def sound(self, key):
        if not self.sounds_on:
            return
        path = f"/System/Library/Sounds/{SOUND_FILES[key]}.aiff"
        subprocess.Popen(
            ["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    def prewarm(self):
        """Load Whisper + the Ollama cleanup model so first dictation is fast."""

        def _load_asr():
            try:
                self.transcriber.transcribe(np.zeros(1600, dtype=np.float32))
                print("[flow] whisper model loaded")
            except Exception as e:
                print(f"[flow] prewarm failed: {e}")

        threading.Thread(target=_load_asr, daemon=True).start()
        threading.Thread(target=self.cleaner.prewarm, daemon=True).start()

    def on_start(self):
        try:
            self.recorder.start()
        except Exception as e:
            self.warning = f"mic error: {e}"
            self.sound("error")
            print(f"[flow] could not start recording: {e}")
            print("       (is Microphone permission granted to this terminal?)")
            return
        with self._phase_lock:
            self.phase = "recording"
        self.sound("start")
        print("recording... (release key to transcribe)")

    def on_stop(self):
        audio = self.recorder.stop()
        with self._phase_lock:
            if self.phase == "recording":
                self.phase = "processing"
        # Heavy work off the listener thread so the hotkey stays responsive.
        threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def _process(self, audio):
        try:
            if len(audio) < self.cfg["sample_rate"] * 0.2:
                print("(too short -- hold the key while speaking)")
                return
            dur = len(audio) / self.cfg["sample_rate"]
            print(f"transcribing {dur:.1f}s ...")
            t0 = time.perf_counter()
            raw = self.transcriber.transcribe(audio)
            t_asr = time.perf_counter() - t0
            if not raw:
                print("(empty transcript)")
                return
            print(f"  raw   ({t_asr:.2f}s): {raw}")
            t0 = time.perf_counter()
            cleaned = self.cleaner.clean(raw)
            t_llm = time.perf_counter() - t0
            print(f"  clean ({t_llm:.2f}s): {cleaned}")
            self.injector.inject(cleaned)
            self.last_text = cleaned
            self.warning = ""
            self.sound("done")
            print("typed into active app")
        except Exception as e:
            self.warning = f"error: {e}"
            self.sound("error")
            print(f"[flow] pipeline error: {e}")
        finally:
            with self._phase_lock:
                if self.phase == "processing":
                    self.phase = "idle"


def main():
    ap = argparse.ArgumentParser(description="Whisper Flow -- local dictation")
    ap.add_argument("--no-ui", action="store_true", help="run without the menu bar indicator")
    ap.add_argument("--debug", action="store_true", help="print every key event")
    args = ap.parse_args()

    cfg = load_config()
    flow = Flow(cfg)

    # Surface macOS permission problems immediately (prompts once if missing).
    ax = doctor.check_accessibility(prompt=True)
    im = doctor.check_input_monitoring(request=True)
    problems = []
    if im is False:
        problems.append("Input Monitoring -- the hotkey will NOT be detected")
    if ax is False:
        problems.append("Accessibility -- text will NOT paste into apps")
    if problems:
        flow.warning = "missing permissions -- run ./run.sh check"
        print("\n*** MISSING macOS PERMISSIONS for this terminal app ***")
        for p in problems:
            print(f"  - {p}")
        print("  Fix: System Settings -> Privacy & Security -> enable your terminal")
        print("  under Input Monitoring / Accessibility / Microphone, then FULLY")
        print("  QUIT and reopen the terminal. Details: ./run.sh check\n")

    if cfg.get("prewarm", True):
        flow.prewarm()

    label = KEY_LABELS.get(cfg["hotkey"], cfg["hotkey"])
    listener = HotkeyListener(cfg["hotkey"], flow.on_start, flow.on_stop, debug=args.debug)
    print(f"Whisper Flow ready. Hold [{label}] to dictate. ", flush=True)

    use_ui = not args.no_ui and cfg.get("indicator", {}).get("menubar", True)
    if not use_ui:
        print("(console mode -- Ctrl+C to quit)")
        listener.run()
        return

    listener.start()
    import ui  # imported lazily so --no-ui works even without rumps

    signal.signal(signal.SIGINT, lambda *_: ui.quit_app())
    print("Menu bar indicator active: 🎙 idle / 🔴 recording / ⏳ transcribing")
    ui.StatusBarApp(flow, label).run()


if __name__ == "__main__":
    main()
