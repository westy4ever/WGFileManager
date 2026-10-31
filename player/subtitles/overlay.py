# -*- coding: utf-8 -*-
"""Full-screen transparent overlay the STUDIO singleton renders into.

The original Studio bound to the player screen (full-screen in its
home plugin). This player's window is the 1400x220 bar, so subtitles
get their own dialog at zPosition 500 — below the bar's 1000, so the
bar slides OVER subtitles. Widget names MUST match studio.py exactly:
subBg1/subBg2, subLine1/subLine2, subShadow0_0 .. subShadow1_7.

Label backgrounds: text/shadow labels carry #FF000000 — under
Enigma2's INVERTED alpha that is a fully-transparent colour, i.e. an
invisible background without using the transparent="1" label mode.
"""
from enigma import eTimer, getDesktop

from Screens.Screen import Screen
from Components.Label import Label

from .studio import STUDIO

_LABELS_BG = ("subBg1", "subBg2")
_LABELS_TXT = ("subLine1", "subLine2")
_LABELS_SHADOW = tuple("subShadow%d_%d" % (li, di)
                       for li in range(2) for di in range(8))


class SubtitleStudioOverlay(Screen):
    skinName = ["SubtitleStudioOverlay"]

    def __init__(self, session):
        self.session = session
        try:
            s = getDesktop(0).size()
            w, h = s.width(), s.height()
        except Exception:
            w, h = 1920, 1080
        widgets = []
        for n in _LABELS_BG:      # studio paints these at runtime
            widgets.append('  <widget name="%s" position="0,0" size="2,2" '
                           'font="Regular;38" backgroundColor="#80000000" '
                           'transparent="0" zPosition="1" />' % n)
        for n in _LABELS_SHADOW:  # outline copies
            widgets.append('  <widget name="%s" position="0,0" size="2,2" '
                           'font="Regular;38" backgroundColor="#FF000000" '
                           'transparent="0" zPosition="2" />' % n)
        for n in _LABELS_TXT:     # text on top
            widgets.append('  <widget name="%s" position="0,0" size="2,2" '
                           'font="Regular;38" backgroundColor="#FF000000" '
                           'transparent="0" zPosition="3" />' % n)
        self.skin = ('<screen name="SubtitleStudioOverlay" position="0,0" '
                     'size="%d,%d" flags="wfNoBorder" '
                     'backgroundColor="transparent" zPosition="500">\n'
                     '%s\n</screen>' % (w, h, "\n".join(widgets)))
        Screen.__init__(self, session)
        for n in _LABELS_BG + _LABELS_SHADOW + _LABELS_TXT:
            self[n] = Label("")
        # FIX (merge): empty ActionMap so the overlay never blocks the
        # player's key dispatch. Without this, the overlay dialog sits
        # on top of the dialog stack and can swallow color-button /
        # arrow key events on some Enigma2 images (confirmed on Vu+ /
        # OpenATV). An empty ActionMap with no actions lets all keys
        # pass through to the player screen below.
        from Components.ActionMap import ActionMap as _AM
        self["actions"] = _AM([], {}, -1)
        self._timer = eTimer()
        try:
            self._timer.timeout.connect(self._tick)
        except Exception:
            self._timer.callback.append(self._tick)
        self._timer.start(100, False)
        self.onClose.append(self._on_close)

    def _tick(self):
        try:
            service = self.session.nav.getCurrentService()
            if not service:
                return
            seek = service.seek()
            if not seek:
                return
            r = seek.getPlayPosition()
            if r[0]:
                return
            STUDIO.update(r[1] / 90.0)
        except Exception:
            pass

    def _on_close(self):
        try:
            self._timer.stop()
        except Exception:
            pass
