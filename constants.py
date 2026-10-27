"""
Constants for WGFileManager
Location: core/constants.py
"""

import os
from enigma import getDesktop

# ============================================================================
# FILE SYSTEM CONSTANTS
# ============================================================================
class FS:
    """File System Constants"""
    # Root paths
    ROOT = "/"
    MEDIA = "/media/"
    HDD = "/media/hdd/"
    USB = "/media/usb/"
    NETWORK = "/media/network/"
    ETC = "/etc/enigma2/"
    
    # Configuration files
    SETTINGS_FILE = "/etc/enigma2/wgfilemanager.json"
    HOTKEYS_FILE = "/etc/enigma2/wgfilemanager_hotkeys.json"
    BOOKMARKS_FILE = "/etc/enigma2/wgfilemanager_bookmarks.json"
    SUBS_CONFIG_FILE = "/etc/enigma2/wgfilemanager_subtitles.json"
    DB_FILE = "/etc/enigma2/wgfilemanager.db"
    
    # Plugin paths
    PLUGIN_ROOT = "/usr/lib/enigma2/python/Plugins/Extensions/WGFileManager/"
    SKINS_DIR = "/usr/share/enigma2/WGFileManager/"
    ICONS_DIR = "/usr/share/enigma2/WGFileManager/icons/"
    BUTTONS_DIR = "/usr/share/enigma2/WGFileManager/buttons/"
    
    # Subtitle directories
    SUBTITLE_DIRS = [
        "/media/hdd/movie/",
        "/media/usb/subtitles/",
        "/etc/enigma2/subtitles/",
        "/tmp/"
    ]
    
    # Supported subtitle extensions
    SUBTITLE_EXTS = ['.srt', '.sub', '.ssa', '.ass', '.vtt', '.txt', '.smi']
    
    # Temporary directory
    TEMP_DIR = "/tmp/wgfilemanager/"
    
    # Log files
    LOG_DIR = "/var/log/"
    MAIN_LOG = "/var/log/wgfilemanager.log"
    DEBUG_LOG = "/var/log/wgfilemanager_debug.log"
    SUBS_LOG = "/var/log/wgfilemanager_subs.log"

# ============================================================================
# SCREEN DIMENSIONS & UI CONSTANTS
# ============================================================================
class UI:
    """User Interface Constants"""
    
    @staticmethod
    def get_screen_size():
        """Get current screen size"""
        desktop = getDesktop(0)
        return desktop.size().width(), desktop.size().height()
    
    # Common screen dimensions
    SCREEN_WIDTH, SCREEN_HEIGHT = get_screen_size()
    
    # Colors (RGBA format)
    COLORS = {
        # Basic colors
        'TRANSPARENT': (0, 0, 0, 0),
        'BLACK': (0, 0, 0, 255),
        'WHITE': (255, 255, 255, 255),
        'RED': (255, 0, 0, 255),
        'GREEN': (0, 255, 0, 255),
        'BLUE': (0, 0, 255, 255),
        'YELLOW': (255, 255, 0, 255),
        'CYAN': (0, 255, 255, 255),
        'MAGENTA': (255, 0, 255, 255),
        
        # UI theme colors
        'BACKGROUND': (26, 26, 26, 255),      # #1a1a1a
        'BACKGROUND_DARK': (17, 17, 17, 255),  # #111111
        'BACKGROUND_LIGHT': (34, 34, 34, 255), # #222222
        'FOREGROUND': (255, 255, 255, 255),    # #ffffff
        'ACCENT': (0, 85, 170, 255),          # #0055aa
        'ACCENT_LIGHT': (0, 119, 221, 255),   # #0077dd
        'WARNING': (255, 153, 0, 255),        # #ff9900
        'ERROR': (220, 53, 69, 255),          # #dc3545
        'SUCCESS': (40, 167, 69, 255),        # #28a745
        'INFO': (23, 162, 184, 255),          # #17a2b8
        
        # Subtitle-specific colors
        'SUBTITLE_BG': (0, 0, 0, 128),        # Semi-transparent black
        'SUBTITLE_TEXT': (255, 255, 255, 255), # White subtitles
        'SUBTITLE_YELLOW': (255, 255, 0, 255), # Yellow subtitles
        'SUBTITLE_CYAN': (0, 255, 255, 255),   # Cyan subtitles
        'SUBTITLE_GREEN': (0, 255, 0, 255),    # Green subtitles
        'SUBTITLE_BORDER': (255, 0, 0, 255),   # Red border for debug
    }
    
    # Font sizes
    FONTS = {
        'TINY': 14,
        'SMALL': 16,
        'NORMAL': 20,
        'MEDIUM': 24,
        'LARGE': 28,
        'XLARGE': 32,
        'HUGE': 40,
        'TITLE': 48,
        
        # Subtitle font sizes
        'SUBS_SMALL': 18,
        'SUBS_MEDIUM': 22,
        'SUBS_LARGE': 26,
        'SUBS_XLARGE': 30,
    }
    
    # Animation timings (ms)
    ANIMATIONS = {
        'FAST': 100,
        'NORMAL': 300,
        'SLOW': 500,
        'SUBTITLE_FADE': 200,
        'TOOLTIP_DELAY': 500,
    }
    
    # Icon names
    ICONS = {
        # File type icons
        'FOLDER': "icon_folder.png",
        'VIDEO': "icon_video.png",
        'AUDIO': "icon_audio.png",
        'IMAGE': "icon_image.png",
        'TEXT': "icon_text.png",
        'SUBTITLE': "icon_subtitle.png",
        'ARCHIVE': "icon_archive.png",
        'EXECUTABLE': "icon_executable.png",
        'CONFIG': "icon_config.png",
        'UNKNOWN': "icon_unknown.png",
        
        # Action icons
        'PLAY': "icon_play.png",
        'STOP': "icon_stop.png",
        'PAUSE': "icon_pause.png",
        'DELETE': "icon_delete.png",
        'COPY': "icon_copy.png",
        'MOVE': "icon_move.png",
        'RENAME': "icon_rename.png",
        'INFO': "icon_info.png",
        'SETTINGS': "icon_settings.png",
        'SEARCH': "icon_search.png",
        'BOOKMARK': "icon_bookmark.png",
        'DOWNLOAD': "icon_download.png",
        'UPLOAD': "icon_upload.png",
        'REFRESH': "icon_refresh.png",
        'HELP': "icon_help.png",
        
        # Subtitle icons
        'SUBS_ON': "icon_subs_on.png",
        'SUBS_OFF': "icon_subs_off.png",
        'SUBS_MENU': "icon_subs_menu.png",
        'SUBS_DOWNLOAD': "icon_subs_download.png",
        'SUBS_DELAY': "icon_subs_delay.png",
        'SUBS_STYLE': "icon_subs_style.png",
        'SUBS_CONVERT': "icon_subs_convert.png",
        'SUBS_SEARCH': "icon_subs_search.png",
    }

# ============================================================================
# HOTKEY CONSTANTS
# ============================================================================
class HOTKEYS:
    """Hotkey Constants"""
    
    # Available keys for mapping
    AVAILABLE_KEYS = [
        # Standard remote keys
        "subtitle", "text", "audio", "info", "epg", "radio", "tv", "video",
        "menu", "help", "red", "green", "yellow", "blue",
        
        # Number keys
        "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
        
        # Navigation keys
        "up", "down", "left", "right", "ok", "exit",
        
        # Playback keys
        "play", "pause", "stop", "record", "rewind", "fastforward",
        "previous", "next", "channelup", "channeldown",
        
        # Special function keys
        "power", "eject", "setup", "sat", "dvd",
        
        # Long press variants (add 'long_' prefix)
        "long_subtitle", "long_text", "long_audio", "long_info",
        "long_red", "long_green", "long_yellow", "long_blue",
    ]
    
    # Default key mappings
    DEFAULT_MAPPINGS = {
        # Subtitle controls
        "toggle_subtitle": "subtitle",
        "open_subtitle_menu": "text",
        "open_subtitle_settings": "long_subtitle",
        "subtitle_delay_up": "8",
        "subtitle_delay_down": "2",
        "subtitle_reset_delay": "5",
        
        # Delay quick adjustment
        "subtitle_delay_minus5": "1",
        "subtitle_delay_minus1": "2",
        "subtitle_delay_minus01": "3",
        "subtitle_delay_plus01": "7",
        "subtitle_delay_plus1": "8",
        "subtitle_delay_plus5": "9",
        
        # Style controls
        "cycle_font_size": "long_info",
        "cycle_font_color": "long_epg",
        "toggle_background": "long_tv",
        "change_position": "long_radio",
        
        # Playback controls
        "play_pause": "play",
        "stop": "stop",
        "rewind": "rewind",
        "fastforward": "fastforward",
        "previous": "previous",
        "next": "next",
        
        # Navigation
        "context_menu": "menu",
        "info": "info",
        "exit": "exit",
        
        # Audio controls
        "toggle_audio": "audio",
        "cycle_audio_track": "long_audio",
        
        # Bookmark controls
        "mark_in": "red",
        "mark_out": "green",
        "jump_to_mark": "yellow",
        "clear_marks": "blue",
        
        # Jump controls
        "jump_forward_30": "right",
        "jump_back_30": "left",
        "jump_forward_300": "channelup",
        "jump_back_300": "channeldown",
    }
    
    # Action descriptions (for UI display)
    ACTION_DESCRIPTIONS = {
        # Subtitle actions
        "toggle_subtitle": "Toggle subtitles on/off",
        "open_subtitle_menu": "Open subtitle selection menu",
        "open_subtitle_settings": "Open subtitle settings",
        "subtitle_delay_up": "Increase subtitle delay",
        "subtitle_delay_down": "Decrease subtitle delay",
        "subtitle_reset_delay": "Reset subtitle delay to zero",
        "subtitle_delay_minus5": "Decrease delay by 5 seconds",
        "subtitle_delay_minus1": "Decrease delay by 1 second",
        "subtitle_delay_minus01": "Decrease delay by 0.1 second",
        "subtitle_delay_plus01": "Increase delay by 0.1 second",
        "subtitle_delay_plus1": "Increase delay by 1 second",
        "subtitle_delay_plus5": "Increase delay by 5 seconds",
        "cycle_font_size": "Cycle through font sizes",
        "cycle_font_color": "Cycle through font colors",
        "toggle_background": "Toggle subtitle background",
        "change_position": "Change subtitle position",
        "cycle_subtitle_track": "Cycle through subtitle tracks",
        "download_subtitle": "Download subtitle for current video",
        "convert_subtitle": "Convert subtitle format",
        "sync_subtitle": "Sync subtitle timing",
        
        # Playback actions
        "play_pause": "Play/Pause playback",
        "stop": "Stop playback",
        "rewind": "Rewind",
        "fastforward": "Fast forward",
        "previous": "Previous item",
        "next": "Next item",
        "increase_speed": "Increase playback speed",
        "decrease_speed": "Decrease playback speed",
        "reset_speed": "Reset playback speed to normal",
        
        # Navigation actions
        "context_menu": "Open context menu",
        "info": "Show file information",
        "exit": "Exit/Go back",
        "home": "Go to home directory",
        "parent": "Go to parent directory",
        "refresh": "Refresh file list",
        
        # Audio actions
        "toggle_audio": "Toggle audio on/off",
        "cycle_audio_track": "Cycle through audio tracks",
        "audio_delay_up": "Increase audio delay",
        "audio_delay_down": "Decrease audio delay",
        "audio_reset_delay": "Reset audio delay to zero",
        
        # Bookmark actions
        "mark_in": "Mark IN point",
        "mark_out": "Mark OUT point",
        "jump_to_mark": "Jump to marked position",
        "clear_marks": "Clear all marks",
        "set_bookmark": "Set bookmark at current position",
        "jump_to_bookmark": "Jump to bookmark",
        "manage_bookmarks": "Manage bookmarks",
        
        # Jump actions
        "jump_forward_30": "Jump forward 30 seconds",
        "jump_back_30": "Jump back 30 seconds",
        "jump_forward_300": "Jump forward 5 minutes",
        "jump_back_300": "Jump back 5 minutes",
        "jump_to_percentage": "Jump to percentage",
        "open_jump_menu": "Open jump menu",
        "open_chapter_menu": "Open chapter menu",
        
        # File operations
        "copy": "Copy selected file",
        "move": "Move selected file",
        "delete": "Delete selected file",
        "rename": "Rename selected file",
        "create_folder": "Create new folder",
        "search": "Search files",
        
        # View actions
        "toggle_view": "Toggle between list and grid view",
        "sort_by_name": "Sort by name",
        "sort_by_date": "Sort by date",
        "sort_by_size": "Sort by size",
        "sort_by_type": "Sort by type",
        "toggle_hidden": "Show/hide hidden files",
        
        # System actions
        "screenshot": "Take screenshot",
        "record": "Start/stop recording",
        "toggle_osd": "Show/hide OSD",
        "system_info": "Show system information",
        "reload_skin": "Reload skin",
        "restart_gui": "Restart GUI",
    }
    
    # Key display names (for UI)
    KEY_DISPLAY_NAMES = {
        "subtitle": "SUBTITLE",
        "text": "TEXT",
        "audio": "AUDIO",
        "info": "INFO",
        "epg": "EPG",
        "radio": "RADIO",
        "tv": "TV",
        "video": "VIDEO",
        "menu": "MENU",
        "help": "HELP",
        "red": "RED",
        "green": "GREEN",
        "yellow": "YELLOW",
        "blue": "BLUE",
        "play": "PLAY",
        "pause": "PAUSE",
        "stop": "STOP",
        "record": "RECORD",
        "rewind": "REWIND",
        "fastforward": "FAST FORWARD",
        "previous": "PREVIOUS",
        "next": "NEXT",
        "channelup": "CHANNEL UP",
        "channeldown": "CHANNEL DOWN",
        "up": "UP",
        "down": "DOWN",
        "left": "LEFT",
        "right": "RIGHT",
        "ok": "OK",
        "exit": "EXIT",
        "power": "POWER",
        "eject": "EJECT",
        "setup": "SETUP",
        "sat": "SAT",
        "dvd": "DVD",
    }
    
    # Long press delay (ms)
    LONG_PRESS_DELAY = 500
    
    # Repeat delay for held keys (ms)
    REPEAT_DELAY = 300
    REPEAT_INTERVAL = 100

# ============================================================================
# SUBTITLE CONSTANTS
# ============================================================================
class SUBTITLES:
    """Subtitle Constants"""
    
    # Supported encodings
    ENCODINGS = [
        'utf-8',
        'iso-8859-1',
        'iso-8859-2',
        'iso-8859-3',
        'iso-8859-4',
        'iso-8859-5',
        'iso-8859-6',
        'iso-8859-7',
        'iso-8859-8',
        'iso-8859-9',
        'iso-8859-10',
        'iso-8859-13',
        'iso-8859-14',
        'iso-8859-15',
        'iso-8859-16',
        'windows-1250',
        'windows-1251',
        'windows-1252',
        'windows-1253',
        'windows-1254',
        'windows-1255',
        'windows-1256',
        'windows-1257',
        'windows-1258',
        'cp437',
        'cp850',
        'cp852',
        'cp866',
        'cp1250',
        'cp1251',
        'cp1252',
        'mac_cyrillic',
        'koi8_r',
        'koi8_u',
        'gb2312',
        'gbk',
        'gb18030',
        'big5',
        'big5hkscs',
        'shift_jis',
        'euc_jp',
        'iso2022_jp',
        'euc_kr',
        'iso2022_kr',
    ]
    
    # Default encoding
    DEFAULT_ENCODING = 'utf-8'
    
    # Font sizes (in pixels)
    FONT_SIZES = {
        'tiny': 16,
        'small': 18,
        'normal': 22,
        'medium': 26,
        'large': 30,
        'xlarge': 34,
        'huge': 38,
    }
    
    # Font colors (RGB)
    FONT_COLORS = {
        'white': (255, 255, 255),
        'yellow': (255, 255, 0),
        'cyan': (0, 255, 255),
        'green': (0, 255, 0),
        'magenta': (255, 0, 255),
        'red': (255, 0, 0),
        'blue': (0, 0, 255),
        'orange': (255, 165, 0),
        'pink': (255, 192, 203),
        'light_blue': (173, 216, 230),
    }
    
    # Subtitle positions
    POSITIONS = {
        'bottom': 90,      # 90% from top
        'middle_bottom': 80,
        'middle': 50,
        'middle_top': 20,
        'top': 10,
    }
    
    # Delay adjustment steps (in milliseconds)
    DELAY_STEPS = {
        'fine': 100,       # 0.1 second
        'normal': 1000,    # 1 second
        'coarse': 5000,    # 5 seconds
    }
    
    # Maximum delay adjustment (in seconds)
    MAX_DELAY = 60         # 60 seconds
    MIN_DELAY = -60        # -60 seconds
    
    # Subtitle providers for download
    PROVIDERS = {
        'opensubtitles': 'OpenSubtitles.org',
        'subscene': 'Subscene',
        'yifysubtitles': 'YIFY Subtitles',
        'podnapisi': 'Podnapisi',
        'addic7ed': 'Addic7ed',
        'subdivx': 'SubDivX',
    }
    
    # Languages (ISO 639-1 codes)
    LANGUAGES = {
        'en': 'English',
        'es': 'Spanish',
        'fr': 'French',
        'de': 'German',
        'it': 'Italian',
        'pt': 'Portuguese',
        'ru': 'Russian',
        'ar': 'Arabic',
        'zh': 'Chinese',
        'ja': 'Japanese',
        'ko': 'Korean',
        'hi': 'Hindi',
        'tr': 'Turkish',
        'nl': 'Dutch',
        'pl': 'Polish',
        'sv': 'Swedish',
        'da': 'Danish',
        'fi': 'Finnish',
        'no': 'Norwegian',
        'he': 'Hebrew',
        'el': 'Greek',
        'hu': 'Hungarian',
        'cs': 'Czech',
        'sk': 'Slovak',
        'ro': 'Romanian',
        'bg': 'Bulgarian',
        'hr': 'Croatian',
        'sr': 'Serbian',
        'sl': 'Slovenian',
        'uk': 'Ukrainian',
        'be': 'Belarusian',
        'et': 'Estonian',
        'lv': 'Latvian',
        'lt': 'Lithuanian',
    }
    
    # Default subtitle settings
    DEFAULT_SETTINGS = {
        'enabled': True,
        'encoding': DEFAULT_ENCODING,
        'font_size': 'normal',
        'font_color': 'white',
        'position': 'bottom',
        'background': True,
        'background_opacity': 128,
        'outline': False,
        'outline_color': 'black',
        'delay': 0,
        'language': 'en',
        'auto_download': False,
        'auto_encoding': True,
        'sync_method': 'auto',
    }
    
    # Subtitle file headers for format detection
    FILE_SIGNATURES = {
        '.srt': ['1\n', 'WEBVTT', 'SUBTITLE'],
        '.sub': ['{', '[INFORMATION]', '[SUBTITLE]'],
        '.ssa': '[Script Info]',
        '.ass': '[Script Info]',
        '.vtt': 'WEBVTT',
        '.smi': '<SMI>',
    }

# ============================================================================
# PLAYER CONSTANTS
# ============================================================================
class PLAYER:
    """Player Constants"""
    
    # Supported video formats
    VIDEO_FORMATS = [
        '.avi', '.mkv', '.mp4', '.mov', '.wmv', '.flv', '.webm', '.m4v',
        '.mpg', '.mpeg', '.vob', '.ts', '.m2ts', '.mts', '.divx', '.xvid',
        '.rm', '.rmvb', '.3gp', '.ogv', '.asf', '.f4v', '.mxf',
    ]
    
    # Supported audio formats
    AUDIO_FORMATS = [
        '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.ac3',
        '.dts', '.opus', '.ra', '.ram', '.mid', '.midi', '.amr', '.ape',
        '.alac', '.mp2', '.mp1', '.mpa', '.mka', '.weba',
    ]
    
    # Supported image formats
    IMAGE_FORMATS = [
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.svg',
        '.webp', '.ico', '.raw', '.cr2', '.nef', '.arw',
    ]
    
    # Playback states
    STATE_IDLE = 0
    STATE_PLAYING = 1
    STATE_PAUSED = 2
    STATE_STOPPED = 3
    STATE_EOF = 4
    STATE_ERROR = 5
    
    # Playback speeds (multiplier)
    SPEEDS = {
        'very_slow': 0.25,
        'slow': 0.5,
        'normal': 1.0,
        'fast': 1.5,
        'very_fast': 2.0,
        'ultra_fast': 4.0,
    }
    
    # Jump intervals (in seconds)
    JUMP_INTERVALS = {
        'small': 10,
        'medium': 30,
        'large': 60,
        'chapter': 300,
        'custom': 0,
    }
    
    # Aspect ratios
    ASPECT_RATIOS = {
        'auto': 'auto',
        '4:3': '4:3',
        '16:9': '16:9',
        '16:10': '16:10',
        '2.35:1': '2.35:1',
        '1.85:1': '1.85:1',
        'fit': 'fit',
        'full': 'full',
    }
    
    # Zoom modes
    ZOOM_MODES = {
        'none': 'none',
        'zoom': 'zoom',
        'panscan': 'panscan',
    }
    
    # Audio channels
    AUDIO_CHANNELS = {
        'stereo': 'stereo',
        'mono': 'mono',
        '5.1': '5.1',
        '7.1': '7.1',
        'pass_through': 'pass_through',
    }

# ============================================================================
# CONFIGURATION CONSTANTS
# ============================================================================
class CONFIG:
    """Configuration Constants"""
    
    # Default configuration structure
    DEFAULT_CONFIG = {
        "version": "1.0.0",
        "general": {
            "startup_path": FS.HDD,
            "default_view": "list",
            "show_hidden": False,
            "confirm_delete": True,
            "auto_refresh": True,
            "refresh_interval": 5,
            "language": "en",
            "theme": "dark",
            "animation_enabled": True,
        },
        "player": {
            "autoplay": True,
            "resume_playback": True,
            "default_volume": 75,
            "default_aspect_ratio": "auto",
            "default_zoom": "none",
            "subtitle_enabled": True,
            "audio_track": "default",
            "remember_position": True,
            "jump_step": 30,
        },
        "subtitles": SUBTITLES.DEFAULT_SETTINGS,
        "hotkeys": {
            "enabled": True,
            "long_press_delay": 500,
            "repeat_enabled": True,
            "repeat_delay": 300,
            "repeat_interval": 100,
            "profiles": {
                "default": {
                    "name": "Default",
                    "description": "Default hotkey profile",
                    "hotkeys": HOTKEYS.DEFAULT_MAPPINGS,
                }
            },
            "active_profile": "default",
        },
        "bookmarks": {
            "max_bookmarks": 100,
            "auto_bookmark": False,
            "bookmark_interval": 300,
        },
        "network": {
            "smb_enabled": True,
            "ftp_enabled": True,
            "nfs_enabled": True,
            "timeout": 10,
            "retries": 3,
        },
        "advanced": {
            "debug": False,
            "log_level": "info",
            "cache_enabled": True,
            "cache_size": 100,
            "preview_enabled": True,
            "thumbnail_size": 128,
        }
    }
    
    # Configuration sections
    SECTIONS = [
        "general",
        "player", 
        "subtitles",
        "hotkeys",
        "bookmarks",
        "network",
        "advanced",
    ]
    
    # Config file version
    CURRENT_VERSION = "1.0.0"
    
    # Minimum compatible version
    MIN_VERSION = "1.0.0"

# ============================================================================
# NETWORK CONSTANTS
# ============================================================================
class NETWORK:
    """Network Constants"""
    
    # Protocols
    PROTOCOLS = ['smb', 'ftp', 'nfs', 'sftp', 'webdav']
    
    # Default ports
    PORTS = {
        'smb': 445,
        'ftp': 21,
        'nfs': 2049,
        'sftp': 22,
        'webdav': 80,
    }
    
    # Timeout in seconds
    TIMEOUT = 10
    
    # Retry attempts
    RETRIES = 3
    
    # Buffer size for transfers (in bytes)
    BUFFER_SIZE = 8192
    
    # Maximum concurrent connections
    MAX_CONNECTIONS = 5

# ============================================================================
# DATABASE CONSTANTS
# ============================================================================
class DB:
    """Database Constants"""
    
    # Table names
    TABLES = {
        'files': 'files',
        'bookmarks': 'bookmarks',
        'history': 'history',
        'subtitles': 'subtitles',
        'thumbnails': 'thumbnails',
        'settings': 'settings',
    }
    
    # Schema version
    SCHEMA_VERSION = 1
    
    # Cache TTL (Time To Live in seconds)
    CACHE_TTL = {
        'files': 300,      # 5 minutes
        'thumbnails': 3600, # 1 hour
        'subtitles': 1800,  # 30 minutes
    }

# ============================================================================
# ERROR CODES & MESSAGES
# ============================================================================
class ERRORS:
    """Error Constants"""
    
    # Error codes
    SUCCESS = 0
    UNKNOWN_ERROR = 1
    FILE_NOT_FOUND = 2
    PERMISSION_DENIED = 3
    DISK_FULL = 4
    NETWORK_ERROR = 5
    INVALID_FORMAT = 6
    PLAYER_ERROR = 7
    SUBTITLE_ERROR = 8
    CONFIG_ERROR = 9
    DATABASE_ERROR = 10
    
    # Error messages
    MESSAGES = {
        UNKNOWN_ERROR: "An unknown error occurred",
        FILE_NOT_FOUND: "File not found",
        PERMISSION_DENIED: "Permission denied",
        DISK_FULL: "Disk is full",
        NETWORK_ERROR: "Network error",
        INVALID_FORMAT: "Invalid file format",
        PLAYER_ERROR: "Player error",
        SUBTITLE_ERROR: "Subtitle error",
        CONFIG_ERROR: "Configuration error",
        DATABASE_ERROR: "Database error",
    }
    
    # Subtitle-specific errors
    SUBTITLE_ERRORS = {
        100: "Subtitle file not found",
        101: "Invalid subtitle format",
        102: "Encoding detection failed",
        103: "Subtitle download failed",
        104: "Subtitle sync failed",
        105: "Subtitle conversion failed",
        106: "No subtitles available",
        107: "Subtitle parsing error",
    }

# ============================================================================
# LOGGING CONSTANTS
# ============================================================================
class LOGGING:
    """Logging Constants"""
    
    # Log levels
    LEVELS = {
        'DEBUG': 10,
        'INFO': 20,
        'WARNING': 30,
        'ERROR': 40,
        'CRITICAL': 50,
    }
    
    # Log formats
    FORMATS = {
        'simple': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        'detailed': '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s',
        'json': '{"time": "%(asctime)s", "name": "%(name)s", "level": "%(levelname)s", "message": "%(message)s"}',
    }
    
    # Default log level
    DEFAULT_LEVEL = 'INFO'
    
    # Maximum log file size (in bytes)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    
    # Maximum backup count
    BACKUP_COUNT = 5

# ============================================================================
# MISCELLANEOUS CONSTANTS
# ============================================================================
class MISC:
    """Miscellaneous Constants"""
    
    # Application information
    APP_NAME = "WGFileManager"
    APP_VERSION = "1.0.0"
    APP_AUTHOR = "WGTeam"
    APP_DESCRIPTION = "Advanced File Manager for Enigma2"
    
    # Plugin information
    PLUGIN_NAME = "WG File Manager"
    PLUGIN_DESCRIPTION = "File manager with subtitle support"
    PLUGIN_ICON = "plugin.png"
    PLUGIN_WHERE = ["pluginmenu", "extensionsmenu"]
    
    # Date/time formats
    DATE_FORMATS = {
        'short': '%Y-%m-%d',
        'medium': '%Y-%m-%d %H:%M',
        'long': '%Y-%m-%d %H:%M:%S',
        'file': '%Y%m%d_%H%M%S',
        'subtitle': '%H:%M:%S,%f',
    }
    
    # File size units
    SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    
    # Thumbnail sizes
    THUMBNAIL_SIZES = {
        'small': (64, 64),
        'medium': (128, 128),
        'large': (256, 256),
    }
    
    # Cache settings
    CACHE_DIR = FS.TEMP_DIR + "cache/"
    CACHE_MAX_AGE = 3600  # 1 hour
    
    # Update check interval (in seconds)
    UPDATE_CHECK_INTERVAL = 86400  # 24 hours
    
    # Default language
    DEFAULT_LANGUAGE = 'en'
    
    # Supported languages
    SUPPORTED_LANGUAGES = ['en', 'es', 'fr', 'de', 'it', 'pt', 'ru']

# ============================================================================
# EXPORT ALL CONSTANTS
# ============================================================================

# Make all constants available at module level
__all__ = ['FS', 'UI', 'HOTKEYS', 'SUBTITLES', 'PLAYER', 'CONFIG', 
           'NETWORK', 'DB', 'ERRORS', 'LOGGING', 'MISC']

# Create convenient aliases
SCREEN_WIDTH = UI.SCREEN_WIDTH
SCREEN_HEIGHT = UI.SCREEN_HEIGHT
COLORS = UI.COLORS
FONTS = UI.FONTS
ICONS = UI.ICONS
APP_NAME = MISC.APP_NAME
APP_VERSION = MISC.APP_VERSION

# Default values for quick access
DEFAULT_CONFIG = CONFIG.DEFAULT_CONFIG
DEFAULT_SUBTITLE_SETTINGS = SUBTITLES.DEFAULT_SETTINGS
DEFAULT_HOTKEY_MAPPINGS = HOTKEYS.DEFAULT_MAPPINGS
SUPPORTED_VIDEO_FORMATS = PLAYER.VIDEO_FORMATS
SUPPORTED_SUBTITLE_FORMATS = FS.SUBTITLE_EXTS
SUPPORTED_LANGUAGES = MISC.SUPPORTED_LANGUAGES
# ========================================================================
# MODULE-LEVEL ALIASES - auto-added by round-3 import checker
# core/*.py (and friends) do: from ..constants import <NAME>
# These MUST be module level; the FS/UI classes don't qualify.
# ========================================================================
BOOKMARKS_FILE = FS.BOOKMARKS_FILE
CACHE_FILE = "/tmp/wgfilemanager_cache.json"
MAX_CACHE_SIZE = 500
REMOTE_CONNECTIONS_FILE = "/etc/enigma2/wgfilemanager_remote_connections.json"
TRASH_PATH = "/media/hdd/wgfilemanager_trash/"

# ========================================================================
# MODULE-LEVEL CONSTANTS - part 2 (round-4 fix pack)
# Consumed by utils/formatters.py, utils/subtitle_utils.py, network/*.py
# ========================================================================
ARCHIVE_EXTENSIONS = ['.zip', '.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz', '.gz', '.bz2', '.xz', '.rar', '.7z']
AUDIO_EXTENSIONS = ['.mp3', '.flac', '.wav', '.aac', '.ogg', '.m4a', '.wma', '.opus', '.ac3', '.dts', '.ape', '.aiff', '.amr']
DEFAULT_CIFS_VERSION = "2.1"
DEFAULT_FTP_PORT = 21
DEFAULT_SFTP_PORT = 22
DEFAULT_TIMEOUT = 30
ICON_ARCHIVE = "[ARC]"
ICON_AUDIO = "[AUD]"
ICON_BINARY = "[BIN]"
ICON_FOLDER = "[DIR]"
ICON_IMAGE = "[IMG]"
ICON_TEXT = "[TXT]"
ICON_VIDEO = "[VID]"
IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tif', '.tiff', '.svg', '.ico']
TEXT_EXTENSIONS = ['.txt', '.log', '.cfg', '.conf', '.ini', '.xml', '.json', '.py', '.sh', '.csv', '.md', '.nfo', '.srt', '.sub', '.ssa', '.ass', '.vtt']
VIDEO_EXTENSIONS = ['.mp4', '.mkv', '.avi', '.ts', '.m2ts', '.mts', '.mov', '.wmv', '.flv', '.webm', '.mpg', '.mpeg', '.vob', '.divx', '.asf', '.3gp', '.ogv', '.m4v']
