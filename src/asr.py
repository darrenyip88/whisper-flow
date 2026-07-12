"""Local speech-to-text using mlx-whisper (Apple Silicon GPU accelerated)."""

import threading

import mlx_whisper


class Transcriber:
    def __init__(self, model_repo, language=None):
        self.model_repo = model_repo
        # Pinning the language (e.g. "en") skips per-clip language detection,
        # which saves a decode pass; None = auto-detect.
        self.language = language
        # Serialize calls: mlx model load/inference is not re-entrant, and the
        # prewarm thread may race the first real dictation.
        self._lock = threading.Lock()

    def transcribe(self, audio):
        """Transcribe a 16 kHz mono float32 numpy array to text."""
        if audio is None or len(audio) == 0:
            return ""
        with self._lock:
            result = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=self.model_repo,
                language=self.language,
            )
        return (result.get("text") or "").strip()
