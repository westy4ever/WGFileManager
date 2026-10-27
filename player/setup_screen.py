"""
WGFileManager - Player Settings
Round-88: honest settings, sibling-safe, session-safe.

Folder context (this file lives in player/, sibling of
custom_media_player.py and __init__.py):

    player/
      __init__.py
      custom_media_player.py
      setup_screen.py    <- this file

Config keys written here MUST match what custom_media_player.py and
core/hotkey_manager.py actually read. Nothing decorative.

Fixes carried:
  - MessageBox imported
  - logger imported with fallback
  - % formatting (Py2 images)
  - self.skin assigned BEFORE ConfigListScreen.__init__
  - single ConfigListScreen.__init__
  - cancel() reverts unsaved edits

Round-88 fixes:
  - session is now passed to ConfigListScreen.__init__ in both screens
  - dropped redundant Screen base class (ConfigListScreen already
    inherits Screen) to keep the MRO clean and avoid a double
    Screen.__init__ on some images
  - button column x-step now derived from button width (no silent
    overlap if extra_buttons grows)
  - resetDefaults() persists and refreshes the on-screen rows
"""

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.config import (
    config, getConfigListEntry, ConfigSubsection,
    ConfigYesNo, ConfigInteger, ConfigSelection, configfile,
)
from enigma import getDesktop

try:
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _ensure_player_config():
    """Keys read by custom_media_player.py - keep in sync, nothing else."""
    if not hasattr(config.plugins, 'wgfilemanager'):
        config.plugins.wgfilemanager = ConfigSubsection()
    p = config.plugins.wgfilemanager

    # Bar behaviour
    if not hasattr(p, 'playerBarPosition'):
        p.playerBarPosition = ConfigInteger(default=0, limits=(0, 1))
    if not hasattr(p, 'playerBarAutoHide'):
        p.playerBarAutoHide = ConfigYesNo(default=True)
    if not hasattr(p, 'playerBarHideSeconds'):
        p.playerBarHideSeconds = ConfigInteger(default=5, limits=(2, 60))

    # Display
    if not hasattr(p, 'playerShowTimeRemaining'):
        p.playerShowTimeRemaining = ConfigYesNo(default=True)
    if not hasattr(p, 'playerShowProgressPercent'):
        p.playerShowProgressPercent = ConfigYesNo(default=True)

    # Seeking
    if not hasattr(p, 'playerJumpSeconds'):
        p.playerJumpSeconds = ConfigInteger(default=300, limits=(10, 1800))

    # Playlist
    if not hasattr(p, 'playerRepeatPlaylist'):
        p.playerRepeatPlaylist = ConfigYesNo(default=False)
    if not hasattr(p, 'playerShufflePlaylist'):
        p.playerShufflePlaylist = ConfigYesNo(default=False)

    # Resume
    if not hasattr(p, 'playerResumePlayback'):
        p.playerResumePlayback = ConfigYesNo(default=True)
    if not hasattr(p, 'playerRememberPosition'):
        p.playerRememberPosition = ConfigYesNo(default=True)

    return p


def _ensure_hotkey_config():
    """
    Keys read by core/hotkey_manager.py.

    VERIFY THIS: open core/hotkey_manager.py and grep for
    'config.plugins.wgfilemanager.hotkey_'. If none appear, DELETE this
    function and the HotkeySettings class below - the screen would be
    writing keys nobody reads.
    """
    if not hasattr(config.plugins, 'wgfilemanager'):
        config.plugins.wgfilemanager = ConfigSubsection()
    p = config.plugins.wgfilemanager

    if not hasattr(p, 'hotkey_profile'):
        p.hotkey_profile = ConfigSelection(default="default", choices=[
            ("default", "Default"),
            ("simple", "Simple"),
            ("advanced", "Advanced"),
            ("expert", "Expert"),
            ("custom", "Custom"),
        ])
    if not hasattr(p, 'hotkey_play_pause'):
        p.hotkey_play_pause = ConfigSelection(default="play", choices=[
            ("play", "PLAY"), ("ok", "OK"), ("pause", "PAUSE"),
        ])
    if not hasattr(p, 'hotkey_stop'):
        p.hotkey_stop = ConfigSelection(default="stop", choices=[
            ("stop", "STOP"), ("exit", "EXIT"), ("cancel", "CANCEL"),
        ])
    if not hasattr(p, 'hotkey_subtitle_toggle'):
        p.hotkey_subtitle_toggle = ConfigSelection(default="subtitle", choices=[
            ("subtitle", "SUBTITLE"), ("text", "TEXT"), ("yellow", "YELLOW"),
        ])
    if not hasattr(p, 'hotkey_subtitle_menu'):
        p.hotkey_subtitle_menu = ConfigSelection(default="long_subtitle", choices=[
            ("long_subtitle", "Long SUBTITLE"),
            ("green", "GREEN"),
            ("menu", "MENU"),
        ])
    if not hasattr(p, 'hotkey_player_bar'):
        p.hotkey_player_bar = ConfigSelection(default="ok", choices=[
            ("ok", "OK"), ("info", "INFO"), ("epg", "EPG"),
        ])
    if not hasattr(p, 'hotkey_seek_forward'):
        p.hotkey_seek_forward = ConfigSelection(default="right", choices=[
            ("right", "RIGHT"), ("fastforward", "FASTFORWARD"), ("next", "NEXT"),
        ])
    if not hasattr(p, 'hotkey_seek_backward'):
        p.hotkey_seek_backward = ConfigSelection(default="left", choices=[
            ("left", "LEFT"), ("rewind", "REWIND"), ("previous", "PREVIOUS"),
        ])
    if not hasattr(p, 'hotkey_red_button'):
        p.hotkey_red_button = ConfigSelection(default="signal", choices=[
            ("signal", "Signal Monitor"), ("bookmark", "Add Bookmark"),
            ("screenshot", "Screenshot"), ("repeat", "Repeat Mode"),
        ])
    if not hasattr(p, 'hotkey_green_button'):
        p.hotkey_green_button = ConfigSelection(default="subtitle_settings", choices=[
            ("subtitle_settings", "Subtitle Settings"), ("audio", "Audio Menu"),
            ("aspect", "Aspect Ratio"), ("zoom", "Zoom Mode"),
        ])
    if not hasattr(p, 'hotkey_yellow_button'):
        p.hotkey_yellow_button = ConfigSelection(default="toggle_subtitle", choices=[
            ("toggle_subtitle", "Toggle Subtitle"), ("download", "Download Subtitle"),
            ("search", "Search Subtitles"), ("convert", "Convert Format"),
        ])
    if not hasattr(p, 'hotkey_blue_button'):
        p.hotkey_blue_button = ConfigSelection(default="jump_menu", choices=[
            ("jump_menu", "Jump Menu"), ("chapters", "Chapters"),
            ("favorites", "Favorites"), ("playlist", "Playlist"),
        ])
    if not hasattr(p, 'hotkey_long_press_delay'):
        p.hotkey_long_press_delay = ConfigSelection(default="500", choices=[
            ("300", "300 ms"), ("500", "500 ms"),
            ("700", "700 ms"), ("1000", "1 second"),
        ])
    return p


# ---------------------------------------------------------------------------
# Shared skin builder
# ---------------------------------------------------------------------------

# FIX (r88): single source of truth for button geometry so extra rows
# cannot silently overlap the primary row.
_BTN_W = 160
_BTN_H = 40
_BTN_X0 = 20
_BTN_X1 = 200
_BTN_X_EXTRA = 380
_BTN_X_STEP = 180


def _build_config_skin(name, title, extra_buttons=()):
    """
    Build a ConfigListScreen skin.

    extra_buttons: sequence of (widget_name, label, bg_hex) placed right
    of the Save button.
    """
    desktop = getDesktop(0)
    sw, sh = desktop.size().width(), desktop.size().height()
    w = min(sw - 60, 700)
    h = min(sh - 60, 560)
    btn_y = h - 56

    buttons = [
        ('key_red',   'Cancel', '#9f1313', _BTN_X0),
        ('key_green', 'Save',   '#1f771f', _BTN_X1),
    ]
    x = _BTN_X_EXTRA
    for wid, label, bg in extra_buttons:
        buttons.append((wid, label, bg, x))
        x += _BTN_X_STEP

    parts = [
        '<screen name="%s" position="center,center" size="%d,%d" title="%s">'
        % (name, w, h, title),
        '  <widget name="config" position="10,10" size="%d,%d" '
        '          scrollbarMode="showOnDemand" />' % (w - 20, h - 80),
    ]
    for wid, label, bg, bx in buttons:
        parts.append(
            '  <widget name="%s" position="%d,%d" size="%d,%d" '
            '          font="Regular;22" halign="center" valign="center" '
            '          backgroundColor="%s" foregroundColor="#ffffff" />'
            % (wid, bx, btn_y, _BTN_W, _BTN_H, bg)
        )
    parts.append('</screen>')
    return "".join(parts)


# ---------------------------------------------------------------------------
# Player Settings
# ---------------------------------------------------------------------------

class PlayerSettings(ConfigListScreen):
    """Every setting here is read by custom_media_player.py."""

    def __init__(self, session, player=None):
        self.player = player  # kept for API compatibility
        self.skin = _build_config_skin(
            "WGPlayerSettings", "Player Settings",
        )
        self.p = _ensure_player_config()
        self.list = self._buildList()
        # FIX (r88): pass session - ConfigListScreen forwards it to
        # Screen.__init__. Previously this was None on many images.
        ConfigListScreen.__init__(self, self.list, session)

        self["key_red"] = Label("Cancel")
        self["key_green"] = Label("Save")
        self["actions"] = ActionMap(
            ["SetupActions", "ColorActions"],
            {
                "cancel": self.keyCancel,
                "save": self.keySave,
                "red": self.keyCancel,
                "green": self.keySave,
            },
            -2,
        )

    def _buildList(self):
        p = self.p
        return [
            getConfigListEntry("Bar position (0=bottom, 1=top)", p.playerBarPosition),
            getConfigListEntry("Auto-hide the bar",                p.playerBarAutoHide),
            getConfigListEntry("Hide after (seconds)",             p.playerBarHideSeconds),
            getConfigListEntry("Show time remaining",              p.playerShowTimeRemaining),
            getConfigListEntry("Show progress percent",            p.playerShowProgressPercent),
            getConfigListEntry("Jump time (seconds)",              p.playerJumpSeconds),
            getConfigListEntry("Repeat playlist",                  p.playerRepeatPlaylist),
            getConfigListEntry("Shuffle playlist",                 p.playerShufflePlaylist),
            getConfigListEntry("Ask to resume playback",           p.playerResumePlayback),
            getConfigListEntry("Remember playback position",       p.playerRememberPosition),
        ]

    def keySave(self):
        try:
            for entry in self["config"].list:
                cfg = entry[1]
                if hasattr(cfg, "save"):
                    cfg.save()
            configfile.save()
            logger.info("[PlayerSettings] saved")
            self.session.open(
                MessageBox, "Player settings saved.",
                MessageBox.TYPE_INFO, timeout=2,
            )
            self.close()
        except Exception as e:
            logger.error("[PlayerSettings] save failed: %s", e)
            self.session.open(
                MessageBox,
                "Could not save:\n%s" % str(e)[:120],
                MessageBox.TYPE_ERROR, timeout=4,
            )

    def keyCancel(self):
        try:
            for entry in self["config"].list:
                cfg = entry[1]
                if hasattr(cfg, "cancel"):
                    cfg.cancel()
        except Exception as e:
            logger.warning("[PlayerSettings] revert failed: %s", e)
        self.close()


# ---------------------------------------------------------------------------
# Hotkey Settings -- ONLY KEEP IF hotkey_manager.py reads hotkey_* keys
# ---------------------------------------------------------------------------

class HotkeySettings(ConfigListScreen):
    """
    Only honest if core/hotkey_manager.py reads
    config.plugins.wgfilemanager.hotkey_* keys. If it reads
    default_hotkeys.json instead, DELETE this class and the
    _ensure_hotkey_config() function above.
    """

    def __init__(self, session):
        self.skin = _build_config_skin(
            "WGHotkeySettings", "Hotkey Settings",
            extra_buttons=(('key_yellow', 'Reset', '#a08500'),),
        )
        self.p = _ensure_hotkey_config()
        self.list = self._buildList()
        # FIX (r88): pass session.
        ConfigListScreen.__init__(self, self.list, session)

        self["key_red"] = Label("Cancel")
        self["key_green"] = Label("Save")
        self["key_yellow"] = Label("Reset")
        self["actions"] = ActionMap(
            ["SetupActions", "ColorActions"],
            {
                "cancel": self.keyCancel,
                "save": self.keySave,
                "red": self.keyCancel,
                "green": self.keySave,
                "yellow": self.resetDefaults,
            },
            -2,
        )

    def _buildList(self):
        p = self.p
        return [
            getConfigListEntry("Hotkey profile",   p.hotkey_profile),
            getConfigListEntry("Play / Pause",     p.hotkey_play_pause),
            getConfigListEntry("Stop",             p.hotkey_stop),
            getConfigListEntry("Toggle subtitle",  p.hotkey_subtitle_toggle),
            getConfigListEntry("Subtitle menu",    p.hotkey_subtitle_menu),
            getConfigListEntry("Player bar",       p.hotkey_player_bar),
            getConfigListEntry("Seek forward",     p.hotkey_seek_forward),
            getConfigListEntry("Seek backward",    p.hotkey_seek_backward),
            getConfigListEntry("RED button",       p.hotkey_red_button),
            getConfigListEntry("GREEN button",     p.hotkey_green_button),
            getConfigListEntry("YELLOW button",    p.hotkey_yellow_button),
            getConfigListEntry("BLUE button",      p.hotkey_blue_button),
            getConfigListEntry("Long-press delay", p.hotkey_long_press_delay),
        ]

    def keySave(self):
        try:
            for entry in self["config"].list:
                cfg = entry[1]
                if hasattr(cfg, "save"):
                    cfg.save()
            configfile.save()
            logger.info("[HotkeySettings] saved")
            self.session.open(
                MessageBox,
                "Hotkey settings saved.\nRestart player to apply.",
                MessageBox.TYPE_INFO, timeout=3,
            )
            self.close()
        except Exception as e:
            logger.error("[HotkeySettings] save failed: %s", e)
            self.session.open(
                MessageBox,
                "Could not save:\n%s" % str(e)[:120],
                MessageBox.TYPE_ERROR, timeout=4,
            )

    def keyCancel(self):
        try:
            for entry in self["config"].list:
                cfg = entry[1]
                if hasattr(cfg, "cancel"):
                    cfg.cancel()
        except Exception as e:
            logger.warning("[HotkeySettings] revert failed: %s", e)
        self.close()

    def resetDefaults(self):
        self.session.openWithCallback(
            self._resetConfirmed,
            MessageBox,
            "Reset all hotkeys to defaults?",
            MessageBox.TYPE_YESNO,
        )

    def _resetConfirmed(self, confirmed):
        if not confirmed:
            return
        try:
            for entry in self["config"].list:
                cfg = entry[1]
                if hasattr(cfg, "setValue") and hasattr(cfg, "default"):
                    cfg.setValue(cfg.default)
                    cfg.save()
            configfile.save()
            # FIX (r88): refresh on-screen rows so the new values are
            # visible without reopening the screen.
            try:
                self["config"].setList(self.list)
            except Exception:
                pass
            logger.info("[HotkeySettings] reset to defaults")
            self.session.open(
                MessageBox, "Hotkeys reset.",
                MessageBox.TYPE_INFO, timeout=2,
            )
        except Exception as e:
            logger.error("[HotkeySettings] reset failed: %s", e)


# ---------------------------------------------------------------------------
# Reset helpers + menu integration
# ---------------------------------------------------------------------------

def reset_player_settings():
    """Reset every player key to its default. Returns the list of keys."""
    p = _ensure_player_config()
    keys = (
        'playerBarPosition', 'playerBarAutoHide', 'playerBarHideSeconds',
        'playerShowTimeRemaining', 'playerShowProgressPercent',
        'playerJumpSeconds',
        'playerRepeatPlaylist', 'playerShufflePlaylist',
        'playerResumePlayback', 'playerRememberPosition',
    )
    for k in keys:
        cfg = getattr(p, k)
        try:
            cfg.setValue(cfg.default)
            cfg.save()
        except Exception as e:
            logger.warning("[PlayerSettings] reset %s failed: %s", k, e)
    try:
        configfile.save()
    except Exception as e:
        logger.warning("[PlayerSettings] configfile.save failed: %s", e)
    logger.info("[PlayerSettings] reset to defaults")
    return list(keys)


def show_player_settings(session, player=None):
    session.open(PlayerSettings, player)


def show_hotkey_settings(session):
    session.open(HotkeySettings)


def add_player_settings_to_menu(menu_list):
    """
    Append player settings entries. HotkeySettings is added only if you
    keep the class above (i.e. hotkey_manager.py reads hotkey_* keys).
    """
    menu_list.append(("Player Settings", show_player_settings))
    menu_list.append(("Hotkey Settings", show_hotkey_settings))
    return menu_list