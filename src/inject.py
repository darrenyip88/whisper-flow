"""Type cleaned text into the active macOS app.

Default method: put the text on the clipboard, simulate Cmd+V, then restore the
previous clipboard contents (the most reliable cross-app approach). Set
inject.method to "type" in config.yaml to synthesize keystrokes instead --
slower, but leaves the clipboard untouched. Both require Accessibility
permission for the synthetic input events.
"""

import subprocess
import time

from pynput.keyboard import Controller, Key


class Injector:
    def __init__(self, restore_clipboard=True, paste_delay=0.6, method="paste"):
        self.restore_clipboard = restore_clipboard
        self.paste_delay = paste_delay
        self.method = method
        self.keyboard = Controller()

    def _get_clipboard(self):
        try:
            return subprocess.run(
                ["pbpaste"], capture_output=True, text=True, timeout=2
            ).stdout
        except Exception:
            return None

    def _set_clipboard(self, text):
        subprocess.run(["pbcopy"], input=text, text=True, timeout=2)

    def inject(self, text):
        text = (text or "").strip()
        if not text:
            return
        if self.method == "type":
            self.keyboard.type(text)
            return
        prev = self._get_clipboard() if self.restore_clipboard else None
        self._set_clipboard(text)
        time.sleep(0.05)
        # Simulate Cmd+V into whatever app currently has focus.
        with self.keyboard.pressed(Key.cmd):
            self.keyboard.press("v")
            self.keyboard.release("v")
        if self.restore_clipboard and prev is not None:
            # Wait for the target app to consume the paste before restoring;
            # restoring too early makes slow apps paste the OLD clipboard.
            time.sleep(self.paste_delay)
            self._set_clipboard(prev)
