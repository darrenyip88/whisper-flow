#!/usr/bin/env bash
# Whisper Flow launcher.
#   ./run.sh                  start dictation (menu bar waveform: monochrome idle, red recording, dim transcribing)
#   ./run.sh check            run diagnostics (permissions, mic, models, Ollama)
#   ./run.sh install-login    auto-start Whisper Flow at every login
#   ./run.sh restart-login    restart the login agent (do this after granting permissions)
#   ./run.sh uninstall-login  remove the auto-start
set -e
cd "$(dirname "$0")"

PROJECT_DIR="$(pwd)"
# Unbuffered stdout so errors actually reach /tmp/whisperflow.out.log when
# launched by launchd (block buffering was swallowing them).
export PYTHONUNBUFFERED=1
UV="$HOME/.local/bin/uv"
OLLAMA_BIN="/Applications/Ollama.app/Contents/Resources/ollama"
[ -x "$OLLAMA_BIN" ] || OLLAMA_BIN="$(command -v ollama || true)"

LABEL="com.whisperflow.agent"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

install_login() {
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$PROJECT_DIR/run.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>ProcessType</key>
    <string>Interactive</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin</string>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/whisperflow.out.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/whisperflow.err.log</string>
</dict>
</plist>
EOF
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load -w "$PLIST"
  echo "Installed login item: $PLIST"
  echo "Whisper Flow will now start automatically at login (waveform icon in the menu bar)."
  echo
  echo "IMPORTANT: the login-launched process is a DIFFERENT app than your"
  echo "terminal, so grant it permissions the first time it runs ->"
  echo "System Settings -> Privacy & Security -> enable the 'Python'/'uv' entry"
  echo "under Accessibility, Input Monitoring, and Microphone. Run ./run.sh check"
  echo "if the icon shows a warning."
}

uninstall_login() {
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  # Stop any currently running instance started by launchd.
  launchctl remove "$LABEL" 2>/dev/null || true
  echo "Removed login item. Whisper Flow will no longer start at login."
}

restart_login() {
  if [ ! -f "$PLIST" ]; then
    echo "No login item installed. Run: ./run.sh install-login"
    exit 1
  fi
  launchctl kickstart -k "gui/$(id -u)/$LABEL" 2>/dev/null \
    || { launchctl unload "$PLIST" 2>/dev/null || true; launchctl load -w "$PLIST"; }
  echo "Restarted the login agent (picks up newly granted permissions)."
}

case "${1:-}" in
  install-login)   install_login;   exit 0 ;;
  uninstall-login) uninstall_login; exit 0 ;;
  restart-login)   restart_login;   exit 0 ;;
esac

# Start the Ollama server if it isn't already listening (LLM cleanup step;
# dictation still works without it, using the raw transcript).
if [ -n "$OLLAMA_BIN" ] && ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "Starting Ollama server..."
  "$OLLAMA_BIN" serve >/tmp/ollama_flow.log 2>&1 &
  for _ in $(seq 1 20); do
    curl -s http://localhost:11434/api/tags >/dev/null 2>&1 && break
    sleep 1
  done
fi

if [ "${1:-}" = "check" ]; then
  exec "$UV" run src/doctor.py
fi

exec "$UV" run src/flow.py
