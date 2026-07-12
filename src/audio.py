"""Microphone capture for push-to-talk dictation.

Records mono float32 audio into an in-memory buffer while a key is held and
returns it as a 16 kHz numpy array ready for mlx-whisper (no ffmpeg needed).
If the input device refuses to open at 16 kHz, captures at the device's native
rate and resamples on stop.
"""

import math
import threading
from math import gcd

import numpy as np
import sounddevice as sd


class Recorder:
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self._capture_rate = sample_rate
        self._frames = []
        self._stream = None
        self._lock = threading.Lock()
        self.level = 0.0  # live mic level 0..1, consumed by the waveform UI

    def _callback(self, indata, frames, time_info, status):
        if status:
            # Overflows are non-fatal for short dictation; note and continue.
            print(f"[audio] {status}")
        # Live level for the on-screen waveform: RMS mapped from dB to 0..1
        # (~-55 dB silence floor -> 0, loud speech -> 1).
        rms = float(np.sqrt((indata ** 2).mean()))
        db = 20.0 * math.log10(rms + 1e-9)
        self.level = max(0.0, min(1.0, (db + 55.0) / 40.0))
        with self._lock:
            self._frames.append(indata.copy())

    def _open(self, rate):
        stream = sd.InputStream(
            samplerate=rate, channels=1, dtype="float32", callback=self._callback
        )
        stream.start()
        return stream

    def start(self):
        if self._stream is not None:
            return  # already recording (duplicate press event)
        self.level = 0.0
        with self._lock:
            self._frames = []
        try:
            self._stream = self._open(self.sample_rate)
            self._capture_rate = self.sample_rate
        except Exception:
            # PortAudio snapshots the device list at init; if audio devices
            # changed since (headphones plugged/unplugged, default mic switch)
            # every open fails with -10851 until the list is refreshed.
            sd._terminate()
            sd._initialize()
            try:
                self._stream = self._open(self.sample_rate)
                self._capture_rate = self.sample_rate
            except Exception:
                # Some input devices refuse 16 kHz; capture at native rate.
                native = int(sd.query_devices(kind="input")["default_samplerate"])
                self._stream = self._open(native)
                self._capture_rate = native

    def stop(self):
        """Stop capture and return the audio as 16 kHz mono float32."""
        if self._stream is None:
            return np.zeros(0, dtype=np.float32)
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
            self.level = 0.0
        with self._lock:
            if not self._frames:
                return np.zeros(0, dtype=np.float32)
            audio = np.concatenate(self._frames, axis=0).flatten().astype(np.float32)
        if self._capture_rate != self.sample_rate and len(audio):
            from scipy.signal import resample_poly

            g = gcd(self.sample_rate, self._capture_rate)
            audio = resample_poly(
                audio, self.sample_rate // g, self._capture_rate // g
            ).astype(np.float32)
        return audio
