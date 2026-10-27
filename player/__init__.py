"""
WGFileManager Player Module
round-88: player + settings.

The AjPanel-style CustomMediaPlayer (custom_media_player.py) is the one
player. PlayerSettings and HotkeySettings (setup_screen.py) are the
settings screens; every config key they write is read by the player or
by core/hotkey_manager.py.

Exports (round-88):
    CustomMediaPlayer, playFile, playPlaylist, playDirectory
    PlayerSettings, HotkeySettings
    show_player_settings, show_hotkey_settings
    add_player_settings_to_menu, reset_player_settings
"""

from .custom_media_player import (
    CustomMediaPlayer,
    playFile,
    playPlaylist,
    playDirectory,
)

# FIX (r88): HotkeySettings and show_hotkey_settings were referenced by
# add_player_settings_to_menu() but never exported. Both are now
# surfaced here so callers can open the screen directly.
from .setup_screen import (
    PlayerSettings,
    HotkeySettings,
    show_player_settings,
    show_hotkey_settings,
    add_player_settings_to_menu,
    reset_player_settings,
)

__all__ = [
    # Player
    'CustomMediaPlayer',
    'playFile',
    'playPlaylist',
    'playDirectory',
    # Settings
    'PlayerSettings',
    'HotkeySettings',
    'show_player_settings',
    'show_hotkey_settings',
    'add_player_settings_to_menu',
    'reset_player_settings',
]