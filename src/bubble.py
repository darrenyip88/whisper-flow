"""On-screen status bubble (Wispr Flow style).

A small click-through pill floating near the bottom-center of the active
screen. While recording it shows a pulsing red dot plus a LIVE waveform of
your voice (20 scrolling bars fed by the mic level at 20 fps); while
transcribing it shows an orange dot with a label. Pure AppKit via pyobjc;
must be created and updated on the main thread (the menu bar app's timers
do both).
"""

from collections import deque

from AppKit import (
    NSBackingStoreBuffered,
    NSColor,
    NSFont,
    NSFontWeightMedium,
    NSMakeRect,
    NSPanel,
    NSScreen,
    NSStatusWindowLevel,
    NSTextField,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Quartz import CABasicAnimation, CALayer, CATransaction

HEIGHT = 32
DOT = 10
PAD_X = 14
GAP = 8
BOTTOM_OFFSET = 20  # px above the visible screen bottom (sits above the Dock)

# Live waveform: scrolling bars, newest level on the right.
BARS = 20
BAR_W = 3
BAR_GAP = 2
WAVE_W = BARS * BAR_W + (BARS - 1) * BAR_GAP
WAVE_MIN_H = 2
WAVE_MAX_H = 20


class Bubble:
    def __init__(self):
        self._phase = None
        self._levels = deque([0.0] * BARS, maxlen=BARS)
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 180, HEIGHT),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        p = self.panel
        p.setLevel_(NSStatusWindowLevel)  # float above normal windows
        p.setOpaque_(False)
        p.setBackgroundColor_(NSColor.clearColor())
        p.setHasShadow_(True)
        p.setIgnoresMouseEvents_(True)  # click-through
        p.setCollectionBehavior_(  # visible on every Space / over fullscreen apps
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )

        content = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 180, HEIGHT))
        content.setWantsLayer_(True)
        content.layer().setBackgroundColor_(
            NSColor.blackColor().colorWithAlphaComponent_(0.8).CGColor()
        )
        content.layer().setCornerRadius_(HEIGHT / 2)
        p.setContentView_(content)
        self.content = content

        self.dot = NSView.alloc().initWithFrame_(
            NSMakeRect(PAD_X, (HEIGHT - DOT) / 2, DOT, DOT)
        )
        self.dot.setWantsLayer_(True)
        self.dot.layer().setCornerRadius_(DOT / 2)
        content.addSubview_(self.dot)

        # Waveform container (shown while recording).
        self.wave = NSView.alloc().initWithFrame_(
            NSMakeRect(PAD_X + DOT + GAP, 0, WAVE_W, HEIGHT)
        )
        self.wave.setWantsLayer_(True)
        self._bars = []
        for i in range(BARS):
            bar = CALayer.layer()
            bar.setBackgroundColor_(
                NSColor.whiteColor().colorWithAlphaComponent_(0.9).CGColor()
            )
            bar.setCornerRadius_(BAR_W / 2)
            bar.setFrame_(
                ((i * (BAR_W + BAR_GAP), (HEIGHT - WAVE_MIN_H) / 2), (BAR_W, WAVE_MIN_H))
            )
            self.wave.layer().addSublayer_(bar)
            self._bars.append(bar)
        content.addSubview_(self.wave)

        # Label (shown while transcribing).
        self.label = NSTextField.labelWithString_("Transcribing…")
        self.label.setTextColor_(NSColor.whiteColor())
        self.label.setFont_(NSFont.systemFontOfSize_weight_(13, NSFontWeightMedium))
        content.addSubview_(self.label)

    def _pulse(self, on):
        layer = self.dot.layer()
        layer.removeAnimationForKey_("pulse")
        if on:
            anim = CABasicAnimation.animationWithKeyPath_("opacity")
            anim.setFromValue_(1.0)
            anim.setToValue_(0.25)
            anim.setDuration_(0.55)
            anim.setAutoreverses_(True)
            anim.setRepeatCount_(1e9)
            layer.addAnimation_forKey_(anim, "pulse")

    def _show(self, width):
        """Size the pill and place it bottom-center of the focused screen."""
        self.content.setFrame_(NSMakeRect(0, 0, width, HEIGHT))
        screen = NSScreen.mainScreen()
        if screen is not None:
            vf = screen.visibleFrame()
            x = vf.origin.x + (vf.size.width - width) / 2
            y = vf.origin.y + BOTTOM_OFFSET
            self.panel.setFrame_display_(NSMakeRect(x, y, width, HEIGHT), True)
        self.panel.orderFrontRegardless()  # show without stealing focus

    def push_level(self, level):
        """Feed one live mic level (0..1); scrolls the waveform (20 fps)."""
        if self._phase != "recording":
            return
        self._levels.append(max(0.0, min(1.0, float(level))))
        CATransaction.begin()
        CATransaction.setDisableActions_(True)  # crisp bar updates, no lag
        for bar, lv in zip(self._bars, self._levels):
            h = WAVE_MIN_H + lv * (WAVE_MAX_H - WAVE_MIN_H)
            x = bar.frame().origin.x
            bar.setFrame_(((x, (HEIGHT - h) / 2), (BAR_W, h)))
        CATransaction.commit()

    def set_phase(self, phase):
        """Show/hide the pill for the given pipeline phase (main thread only)."""
        if phase == self._phase:
            return
        self._phase = phase

        if phase == "recording":
            self._levels.extend([0.0] * BARS)  # reset the scroll
            self.dot.layer().setBackgroundColor_(NSColor.systemRedColor().CGColor())
            self._pulse(True)
            self.label.setHidden_(True)
            self.wave.setHidden_(False)
            self._show(PAD_X + DOT + GAP + WAVE_W + PAD_X)
        elif phase == "processing":
            self.dot.layer().setBackgroundColor_(NSColor.systemOrangeColor().CGColor())
            self._pulse(False)
            self.wave.setHidden_(True)
            self.label.setHidden_(False)
            self.label.sizeToFit()
            size = self.label.frame().size
            self.label.setFrameOrigin_(
                (PAD_X + DOT + GAP, (HEIGHT - size.height) / 2)
            )
            self._show(PAD_X + DOT + GAP + size.width + PAD_X)
        else:
            self.panel.orderOut_(None)
            self._pulse(False)
