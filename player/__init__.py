"""
WGFileManager Player Module

The Nova player (player/nova/) -- NovaPlay's player, local edition -- is
the one video player; its settings are in its own MENU panel. (The old
player's settings screens, setup_screen.py, were removed with that player.)

Exports:
    play_file, play_playlist, play_directory  (and the old names
    playFile, playPlaylist, playDirectory, kept for callers)
"""

from .nova import play_file, play_playlist, play_directory

# old names, kept so existing callers keep working
playFile = play_file
playPlaylist = play_playlist
playDirectory = play_directory

__all__ = [
    'play_file',
    'play_playlist',
    'play_directory',
    'playFile',
    'playPlaylist',
    'playDirectory',
]
