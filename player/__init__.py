"""
WGFileManager Player Module

The Nova player (player/nova/) -- NovaPlay's player, local edition -- is
the one video player. PlayerSettings and HotkeySettings (setup_screen.py)
are the settings screens.

Exports:
    play_file, play_playlist, play_directory  (and the old names
    playFile, playPlaylist, playDirectory, kept for callers)
    PlayerSettings, HotkeySettings
    show_player_settings, show_hotkey_settings
    add_player_settings_to_menu, reset_player_settings
"""

from .nova import play_file, play_playlist, play_directory

# old names, kept so existing callers keep working
playFile = play_file
playPlaylist = play_playlist
playDirectory = play_directory

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
    'play_file',
    'play_playlist',
    'play_directory',
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