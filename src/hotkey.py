"""Global push-to-talk hotkey listener (pynput).

Fires on_start when the configured key is first pressed and on_stop when it is
released. Key auto-repeat is ignored so a single hold produces exactly one
record/transcribe cycle. Requires Accessibility + Input Monitoring permission.
"""

from pynput import keyboard

KEY_MAP = {
    "alt_r": keyboard.Key.alt_r,
    "alt_l": keyboard.Key.alt_l,
    "alt": keyboard.Key.alt,
    "cmd_r": keyboard.Key.cmd_r,
    "cmd_l": keyboard.Key.cmd_l,
    "ctrl_r": keyboard.Key.ctrl_r,
    "shift_r": keyboard.Key.shift_r,
    "f13": keyboard.Key.f13,
}


class HotkeyListener:
    def __init__(self, key_name, on_start, on_stop, debug=False):
        self.target = KEY_MAP.get(key_name, keyboard.Key.alt_r)
        self.on_start = on_start
        self.on_stop = on_stop
        self.debug = debug
        self._active = False
        self._listener = None

    def _on_press(self, key):
        if self.debug:
            print(f"[hotkey] press:   {key}")
        if key == self.target and not self._active:
            self._active = True
            self.on_start()

    def _on_release(self, key):
        if self.debug:
            print(f"[hotkey] release: {key}")
        if key == self.target and self._active:
            self._active = False
            self.on_stop()

    def start(self):
        """Start listening without blocking (for use alongside the UI loop)."""
        self._listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release
        )
        self._listener.start()
        return self._listener

    def run(self):
        """Blocking listen (console mode)."""
        self.start().join()
