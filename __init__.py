"""
WG File Manager PRO - Professional File Manager for Enigma2
round-25: single AjPanel-style player (player/custom_media_player.py);
the legacy player and its standalone subtitle engine were removed.
"""

__version__ = "1.1.0"
__author__ = "WG Development Team"
__description__ = "Professional File Manager with Subtitle Support"

try:
    from .ui.main_screen import WGFileManagerMain
    __all__ = ['WGFileManagerMain']
except ImportError as e:
    # Graceful fallback for partial imports
    import logging
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger(__name__).warning(f"Some imports failed during package init: {e}")
    __all__ = []

# Package metadata
PACKAGE_INFO = {
    'name': 'WGFileManager',
    'version': __version__,
    'description': __description__,
    'features': [
        'Dual pane file manager',
        'AjPanel-style media player (playlist, resume, posters)',
        'Subtitles: external files + embedded tracks, live sync adjust',
        'Network access (FTP, SFTP, WebDAV, SMB)',
        'Archive support (ZIP, TAR)',
        'Hotkey configuration',
    ],
    'author': __author__,
    'license': 'GPLv2',
}

def get_package_info():
    """Get package information"""
    return PACKAGE_INFO

def check_player_support():
    """round-25: replaced check_subtitle_support - subtitles live in the player."""
    try:
        from .player.custom_media_player import CustomMediaPlayer
        return True, "Player with subtitle support available"
    except ImportError as e:
        return False, f"Player unavailable: {e}"

# compat alias (old name)
check_subtitle_support = check_player_support
