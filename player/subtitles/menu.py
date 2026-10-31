# -*- coding: utf-8 -*-
"""
WGFileManager — subtitle menu.

The SUBTITLE / TEXT / yellow key opens this. Replaces the old
SubtitleSelectionScreen. Uses a ChoiceBox: the action set covers
search / browse / sync / studio / on-off, and a MenuList would need a
second level of navigation for each group.
"""

import os

from Screens.ChoiceBox import ChoiceBox

from .engine import (
    get_subtitle_state, adjust_sync, reset_sync, disable_subtitle,
    apply_subtitle, remember_subtitle, find_best_local_subtitle,
    SYNC_STEP_MS, _cfg, _cfg_set, _cfg_bool,
)


def _skip_label():
    try:
        secs = max(10, min(600, int(_cfg("skip_intro_secs", "90") or 90)))
    except Exception:
        secs = 90
    return "Skip intro +%ds" % secs


class SubtitleMenuScreen(object):
    """Opens a ChoiceBox and routes the result back into the engine."""

    def __init__(self, session, player=None):
        self.session = session
        self.player = player
        self._open()

    def _open(self):
        studio_on = str(_cfg("substudio_mode", "false")).lower() == "true"
        autosub_on = _cfg_bool("autosub", True)
        state = get_subtitle_state()
        has_sub = bool(state.get("path"))

        items = [
            (_skip_label(), "skipintro"),
            ("Auto subtitles - %s" % ("ON" if autosub_on else "OFF"),
             "autosub_toggle"),
            ("Subtitle Studio - %s" % ("ON" if studio_on else "OFF"),
             "studio_toggle"),
        ]
        if studio_on:
            items.append(("Studio settings", "studio_open"))
        items.append(("Audio tracks", "audio"))
        items.append(("Browse local subtitles", "browse"))
        items.append(("Search online (SubSource)", "subsource"))
        items.append(("Search online (OpenSubtitles)", "opensubtitles"))
        if has_sub:
            items.append(("Sync +%d ms" % SYNC_STEP_MS, "sync+"))
            items.append(("Sync -%d ms" % SYNC_STEP_MS, "sync-"))
            items.append(("Reset sync", "sync0"))
            items.append(("Disable subtitles", "off"))

        self.session.openWithCallback(self._chosen, ChoiceBox,
                                      "Subtitles", items)

    def _chosen(self, result):
        if not result:
            return
        choice = result[1]
        try:
            if choice == "skipintro":
                self._skip()
            elif choice == "autosub_toggle":
                _cfg_set("autosub",
                         "false" if _cfg_bool("autosub", True) else "true")
            elif choice == "studio_toggle":
                self._toggle_studio()
            elif choice == "studio_open":
                self._open_studio_settings()
            elif choice == "audio":
                self._open_audio()
            elif choice == "browse":
                self._browse()
            elif choice in ("subsource", "opensubtitles"):
                self._online(choice)
            elif choice == "sync+":
                adjust_sync(self.session, SYNC_STEP_MS)
            elif choice == "sync-":
                adjust_sync(self.session, -SYNC_STEP_MS)
            elif choice == "sync0":
                reset_sync(self.session)
            elif choice == "off":
                disable_subtitle(self.session)
        except Exception as e:
            try:
                with open("/tmp/wgfilemanager.log", "a") as f:
                    f.write("[subtitles.menu] action %s failed: %s\n"
                            % (choice, e))
            except Exception:
                pass

    def _skip(self):
        if self.player and hasattr(self.player, "_skip_intro"):
            self.player._skip_intro()
        elif self.player and hasattr(self.player, "seek"):
            try:
                secs = max(10, min(600,
                                   int(_cfg("skip_intro_secs", "90") or 90)))
            except Exception:
                secs = 90
            self.player.seek(secs)

    def _toggle_studio(self):
        was_on = str(_cfg("substudio_mode", "false")).lower() == "true"
        _cfg_set("substudio_mode", "false" if was_on else "true")
        state = get_subtitle_state()
        path = state.get("_orig_path") or state.get("path") or ""
        from .studio import STUDIO
        if not was_on:
            if path and os.path.exists(path):
                STUDIO.attach(path)
        else:
            STUDIO.detach()
            if path and os.path.exists(path):
                apply_subtitle(self.session, path)

    def _open_studio_settings(self):
        if self.player and hasattr(self.player, "_open_studio_overlay"):
            self.player._open_studio_overlay()

    def _open_audio(self):
        try:
            from Screens.AudioSelection import AudioSelection
            self.session.open(AudioSelection, self.player)
        except Exception:
            pass

    def _browse(self):
        from .screens import NovaSubtitleBrowser
        self.session.openWithCallback(
            self._picked_local, NovaSubtitleBrowser,
            "", self.player.title if self.player else "")

    def _picked_local(self, path):
        if not path or not os.path.exists(path):
            return
        if self.player and getattr(self.player, "_item_url", ""):
            remember_subtitle(self.player._item_url, path, 0)
        apply_subtitle(self.session, path)

    def _online(self, provider):
        from .screens import NovaOnlineSubsScreen
        self.session.openWithCallback(
            self._picked_online, NovaOnlineSubsScreen,
            self.player.title if self.player else "",
            getattr(self.player, "_item_url", "") if self.player else "",
            provider,
            _cfg(provider + "_api_key", ""))

    def _picked_online(self, path):
        if not path or not os.path.exists(path):
            return
        if self.player and getattr(self.player, "_item_url", ""):
            remember_subtitle(self.player._item_url, path, 0)
        apply_subtitle(self.session, path)
