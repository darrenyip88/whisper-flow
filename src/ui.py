"""Menu bar indicator (rumps).

Shows live state in the macOS menu bar so you always know Whisper Flow is
running: a Wispr Flow-style waveform glyph when idle (template image, so it
adapts to light/dark menu bars), red while recording, dimmed while
transcribing. The dropdown shows status, the last dictation, and Quit.
"""

import os
import tempfile

import rumps
from AppKit import NSBezierPath, NSBitmapImageRep, NSColor, NSImage, NSMakeRect

# Icon geometry (px, drawn 2x for retina; rumps scales it to 20pt).
_SIZE = 40
_BAR_W = 4.5
_GAP = 3.5
_HEIGHTS = (0.35, 0.7, 1.0, 0.55, 0.3)  # waveform silhouette
_MAX_H = 28.0


def _draw_waveform(path, color, alpha):
    img = NSImage.alloc().initWithSize_((_SIZE, _SIZE))
    img.lockFocus()
    color.colorWithAlphaComponent_(alpha).set()
    total_w = len(_HEIGHTS) * _BAR_W + (len(_HEIGHTS) - 1) * _GAP
    x = (_SIZE - total_w) / 2
    for frac in _HEIGHTS:
        h = max(_MAX_H * frac, _BAR_W)  # never thinner than it is wide
        rect = NSMakeRect(x, (_SIZE - h) / 2, _BAR_W, h)
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            rect, _BAR_W / 2, _BAR_W / 2
        ).fill()
        x += _BAR_W + _GAP
    img.unlockFocus()
    rep = NSBitmapImageRep.imageRepWithData_(img.TIFFRepresentation())
    rep.representationUsingType_properties_(4, None).writeToFile_atomically_(  # 4 = PNG
        path, True
    )


def _make_icons():
    d = tempfile.mkdtemp(prefix="whisperflow-icons-")
    icons = {}
    # (color, alpha, template) per phase; template=True lets macOS tint the
    # glyph for light/dark menu bars, so idle/processing use plain black.
    specs = {
        "idle": (NSColor.blackColor(), 1.0, True),
        "recording": (NSColor.systemRedColor(), 1.0, False),
        "processing": (NSColor.blackColor(), 0.35, True),
    }
    for phase, (color, alpha, template) in specs.items():
        path = os.path.join(d, f"{phase}.png")
        _draw_waveform(path, color, alpha)
        icons[phase] = (path, template)
    return icons


ICONS = _make_icons()


def quit_app():
    rumps.quit_application()


class StatusBarApp(rumps.App):
    def __init__(self, flow, hotkey_label):
        path, template = ICONS["idle"]
        super().__init__("Whisper Flow", icon=path, template=template)
        self._icon_path = path
        self.flow = flow
        self.hotkey_label = hotkey_label
        self.status_item = rumps.MenuItem("Starting…")
        self.last_item = rumps.MenuItem("Last: —")
        self.menu = [self.status_item, self.last_item]
        self.bubble = None
        if flow.cfg.get("indicator", {}).get("bubble", True):
            try:
                from bubble import Bubble

                self.bubble = Bubble()
            except Exception as e:  # never let the bubble kill dictation
                print(f"[ui] on-screen bubble disabled: {e}")
        # Poll shared state from the main thread (AppKit UI updates must not
        # come from the listener/pipeline threads).
        self._timer = rumps.Timer(self._refresh, 0.15)
        self._timer.start()
        # Faster timer just for the live waveform (no-op unless recording).
        self._wave_timer = rumps.Timer(self._wave_tick, 0.05)
        self._wave_timer.start()

    def _wave_tick(self, _):
        if self.bubble and self.flow.phase == "recording":
            self.bubble.push_level(self.flow.recorder.level)

    def _refresh(self, _):
        flow = self.flow
        path, template = ICONS.get(flow.phase, ICONS["idle"])
        if self._icon_path != path:
            self._icon_path = path
            self.template = template
            self.icon = path
        if self.bubble:
            self.bubble.set_phase(flow.phase)

        if flow.phase == "recording":
            status = "Recording… release to transcribe"
        elif flow.phase == "processing":
            status = "Transcribing…"
        elif flow.warning:
            status = f"⚠️ {flow.warning}"
        else:
            status = f"Idle — hold {self.hotkey_label} to dictate"
        if self.status_item.title != status:
            self.status_item.title = status

        last = flow.last_text or "—"
        if len(last) > 47:
            last = last[:47] + "…"
        last = f"Last: {last}"
        if self.last_item.title != last:
            self.last_item.title = last
