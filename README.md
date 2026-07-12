# Whisper Flow

A local, offline dictation tool for macOS. Hold a key, talk, release — your words get typed into whatever app is in front. Think [Wispr Flow](https://wisprflow.ai), but everything runs on your Mac. No cloud, no account, no per-word billing.

## Why it exists

I wanted push-to-talk dictation that stays on-device. Cloud dictation means your voice leaves the machine and you pay per minute. This uses Apple Silicon's MLX to run Whisper locally and a small local LLM to clean up the transcript. The whole pipeline runs offline once the models are downloaded.

## How it works

```
hold hotkey → record mic → local Whisper (MLX) → LLM cleanup (Ollama) → paste into active app
```

1. **Hotkey** (`src/hotkey.py`) — hold a key (default: left ⌥ Option) to record, release to stop.
2. **Record** (`src/audio.py`) — captures mic audio at 16 kHz.
3. **Transcribe** (`src/asr.py`) — [`mlx-whisper`](https://github.com/ml-explore/mlx-examples) turns audio into text on the GPU. Default model is `whisper-large-v3-turbo`.
4. **Cleanup** (`src/cleanup.py`) — a local Ollama model (default `qwen2.5:3b`) strips filler ("um", "uh", "like"), fixes punctuation, turns spoken enumerations into numbered lists, and converts dictated symbols ("tilde slash dot zshrc" → `~/.zshrc`). If Ollama is unreachable, it falls back to the raw transcript so dictation never fails.
5. **Inject** (`src/inject.py`) — pastes the result into the active app via clipboard + Cmd+V (restores your old clipboard after).

There's a menu bar indicator (🎙 idle / 🔴 recording / ⏳ transcribing) and an optional floating pill at the bottom of the screen while recording (`src/ui.py`, `src/bubble.py`).

## Requirements

- macOS on Apple Silicon (MLX needs it)
- [`uv`](https://github.com/astral-sh/uv) for running (`~/.local/bin/uv`)
- [Ollama](https://ollama.com) for the cleanup step (optional — dictation works without it)
- Python deps in `requirements.txt` (`mlx-whisper`, `sounddevice`, `pynput`, `rumps`, etc.)

## Setup

```bash
# 1. install the cleanup model (optional but recommended)
ollama pull qwen2.5:3b

# 2. check permissions, mic, models, and Ollama
./run.sh check

# 3. start dictation
./run.sh
```

First run downloads the Whisper model from HuggingFace (a few hundred MB).

macOS will ask for **Accessibility**, **Input Monitoring**, and **Microphone** permissions — grant them to the `Python`/`uv` entry under System Settings → Privacy & Security. `./run.sh check` tells you what's missing.

### Auto-start at login

```bash
./run.sh install-login     # start automatically at every login
./run.sh restart-login     # restart after granting permissions
./run.sh uninstall-login   # remove it
```

The login-launched process is a *different* app than your terminal, so it needs its own permission grants the first time it runs.

## Config

Everything lives in `config.yaml` — hotkey, Whisper model, cleanup on/off, paste vs. type injection, indicators. Notable knobs:

| Setting | What it does |
|---|---|
| `hotkey` | Push-to-talk key (`alt_l`, `cmd_r`, `f13`, …) |
| `asr_model` | Whisper model — trade speed for accuracy |
| `cleanup.model` | Ollama model. `qwen2.5:3b` tested more faithful than `llama3.2:3b`, which flipped questions into statements |
| `inject.method` | `paste` (fast, uses clipboard) or `type` (leaves clipboard alone) |
| `prewarm` | Load Whisper at startup so the first dictation is instant |

## Testing

```bash
uv run tests/test_pipeline.py
```

Synthesizes speech with macOS `say` (no mic needed), runs it through Whisper + cleanup, and checks the output. Covers everything except the global hotkey and text injection, which need an interactive GUI session.

## Layout

```
config.yaml          all settings
run.sh               launcher + login-item management + diagnostics
src/flow.py          pipeline controller / entry point
src/hotkey.py        push-to-talk listener
src/audio.py         mic capture
src/asr.py           MLX Whisper transcription
src/cleanup.py       Ollama LLM cleanup
src/inject.py        text injection into active app
src/ui.py            menu bar indicator
src/bubble.py        floating recording pill
src/doctor.py        `./run.sh check` diagnostics
tests/               pipeline test
```

## License

MIT — see [LICENSE](LICENSE).

