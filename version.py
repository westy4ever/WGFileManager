"""
Version information for WGFileManager
"""

VERSION = "1.1.0"
BUILD_DATE = "2024-01-15"
RELEASE_NAME = "Subtitle Edition"

# Feature flags
FEATURES = {
    'subtitle_support': True,
    'multi_format_subtitles': True,
    'subtitle_menu': True,
    'auto_load_subtitles': True,
    'subtitle_delay_adjustment': True,
    'subtitle_encoding_support': True,
    'player_bar': True,
    'hotkey_configuration': True,
    'network_support': True,
    'archive_support': True,
    'remote_connections': True,
}

def get_version_info():
    """Get complete version information"""
    return f"""
WG File Manager PRO v{VERSION} - {RELEASE_NAME}
Build Date: {BUILD_DATE}

Features Enabled:
{', '.join([f for f, enabled in FEATURES.items() if enabled])}
"""

def check_feature(feature_name):
    """Check if a feature is enabled"""
    return FEATURES.get(feature_name, False)