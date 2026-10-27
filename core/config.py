from Components.config import config, ConfigSubsection, ConfigText, ConfigSelection, ConfigInteger, ConfigYesNo
import json
import os
from ..constants import BOOKMARKS_FILE, REMOTE_CONNECTIONS_FILE
from ..utils.logging_config import get_logger

logger = get_logger(__name__)

class WGFileManagerConfig:
    # Change the class to a standard function
    def __init__(self):
        # FIX: Ensure global plugins exist before assignment
        from Components.config import config as en_config, ConfigSubsection
        if not hasattr(en_config, 'plugins'):
            en_config.plugins = ConfigSubsection()
            
        self.plugins = en_config.plugins 
        self.setup_config()
    
    def setup_config(self):
        """Initialize configuration sections"""
        # Ensure config.plugins exists
        if not hasattr(config, 'plugins'):
            config.plugins = ConfigSubsection()
        
        # Ensure config.plugins.wgfilemanager exists
        if not hasattr(config.plugins, 'wgfilemanager'):
            config.plugins.wgfilemanager = ConfigSubsection()

        
        p = config.plugins.wgfilemanager
        
        # --- Paths ---
        if not hasattr(p, 'left_path'):
            p.left_path = ConfigText(default="/media/hdd/", fixed_size=False)
        if not hasattr(p, 'right_path'):
            p.right_path = ConfigText(default="/", fixed_size=False)
        
        # --- Display & Sorting ---
        if not hasattr(p, 'starting_pane'):
            p.starting_pane = ConfigSelection(default="left", choices=[("left", "Left"), ("right", "Right")])
        if not hasattr(p, 'show_dirs_first'):
            p.show_dirs_first = ConfigSelection(default="yes", choices=[("yes", "Yes"), ("no", "No")])
        if not hasattr(p, 'left_sort_mode'):
            p.left_sort_mode = ConfigSelection(default="name", choices=[("name", "Name"), ("size", "Size"), ("date", "Date")])
        if not hasattr(p, 'right_sort_mode'):
            p.right_sort_mode = ConfigSelection(default="name", choices=[("name", "Name"), ("size", "Size"), ("date", "Date")])
        
        # --- Context Menu Settings ---
        if not hasattr(p, 'enable_smart_context'):
            p.enable_smart_context = ConfigYesNo(default=True)
        if not hasattr(p, 'ok_long_press_time'):
            p.ok_long_press_time = ConfigInteger(default=400, limits=(100, 2000))
        if not hasattr(p, 'group_tools_menu'):
            p.group_tools_menu = ConfigYesNo(default=True)
            
        # --- File Operations ---
        if not hasattr(p, 'trash_enabled'):
            p.trash_enabled = ConfigSelection(default="yes", choices=[("yes", "Yes"), ("no", "No")])
        if not hasattr(p, 'cache_enabled'):
            p.cache_enabled = ConfigYesNo(default=True)
        if not hasattr(p, 'preview_size'):
            p.preview_size = ConfigSelection(default="1024", choices=[("512", "512KB"), ("1024", "1MB"), ("2048", "2MB")])
            
        # --- Exit Behavior ---
        if not hasattr(p, 'save_left_on_exit'):
            p.save_left_on_exit = ConfigSelection(default="yes", choices=[("yes", "Yes"), ("no", "No")])
        if not hasattr(p, 'save_right_on_exit'):
            p.save_right_on_exit = ConfigSelection(default="yes", choices=[("yes", "Yes"), ("no", "No")])

        # --- Media Player ---
        if not hasattr(p, 'use_internal_player'):
            p.use_internal_player = ConfigYesNo(default=True)
        if not hasattr(p, 'fallback_to_external'):
            p.fallback_to_external = ConfigYesNo(default=True)

        # --- Remote Access ---
        if not hasattr(p, 'remote_ip'):
            p.remote_ip = ConfigText(default="192.168.1.10", fixed_size=False)
        
        # FTP
        if not hasattr(p, 'ftp_host'): p.ftp_host = ConfigText(default="", fixed_size=False)
        if not hasattr(p, 'ftp_port'): p.ftp_port = ConfigInteger(default=21, limits=(1, 65535))
        if not hasattr(p, 'ftp_user'): p.ftp_user = ConfigText(default="anonymous", fixed_size=False)
        if not hasattr(p, 'ftp_pass'): p.ftp_pass = ConfigText(default="", fixed_size=False)
        
        # SFTP
        if not hasattr(p, 'sftp_host'): p.sftp_host = ConfigText(default="", fixed_size=False)
        if not hasattr(p, 'sftp_port'): p.sftp_port = ConfigInteger(default=22, limits=(1, 65535))
        if not hasattr(p, 'sftp_user'): p.sftp_user = ConfigText(default="root", fixed_size=False)
        if not hasattr(p, 'sftp_pass'): p.sftp_pass = ConfigText(default="", fixed_size=False)
        
        # WebDAV
        if not hasattr(p, 'webdav_url'): p.webdav_url = ConfigText(default="", fixed_size=False)
        if not hasattr(p, 'webdav_user'): p.webdav_user = ConfigText(default="", fixed_size=False)
        if not hasattr(p, 'webdav_pass'): p.webdav_pass = ConfigText(default="", fixed_size=False)

    def load_bookmarks(self):
        """Load bookmarks from file"""
        try:
            if os.path.exists(BOOKMARKS_FILE):
                with open(BOOKMARKS_FILE, 'r') as f:
                    bookmarks = json.load(f)
                if isinstance(bookmarks, dict):
                    return {str(k): v for k, v in bookmarks.items()
                            if isinstance(v, str) and os.path.isabs(v)}
        except Exception as e:
            logger.error(f"Error loading bookmarks: {e}")
        return {}

    def save_bookmarks(self, bookmarks):
        """Save bookmarks to file"""
        try:
            bookmark_dir = os.path.dirname(BOOKMARKS_FILE)
            if not os.path.exists(bookmark_dir):
                os.makedirs(bookmark_dir, exist_ok=True)
            with open(BOOKMARKS_FILE, 'w') as f:
                json.dump(bookmarks, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving bookmarks: {e}")
            return False

    def load_remote_connections(self):
        """Load remote connections from file with validation"""
        try:
            if os.path.exists(REMOTE_CONNECTIONS_FILE):
                with open(REMOTE_CONNECTIONS_FILE, 'r') as f:
                    connections = json.load(f)
                
                if isinstance(connections, dict):
                    valid_connections = {}
                    for name, conn in connections.items():
                        if (isinstance(name, str) and isinstance(conn, dict) and
                            'type' in conn and 'host' in conn):
                            valid_connections[name] = conn
                    return valid_connections
        except Exception as e:
            logger.error(f"Error loading remote connections: {e}")
        return {}

    def save_remote_connections(self, connections):
        """Save remote connections to file with validation"""
        try:
            if not isinstance(connections, dict): return False
            validated = {}
            for name, conn in connections.items():
                if (isinstance(name, str) and isinstance(conn, dict) and
                    'type' in conn and 'host' in conn):
                    if conn['type'] in ['ftp', 'sftp', 'webdav', 'cifs']:
                        validated[name] = conn
            
            remote_dir = os.path.dirname(REMOTE_CONNECTIONS_FILE)
            if not os.path.exists(remote_dir):
                os.makedirs(remote_dir, exist_ok=True)
            
            with open(REMOTE_CONNECTIONS_FILE, 'w') as f:
                json.dump(validated, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving remote connections: {e}")
            return False

    def validate_config(self):
        """Validate all configuration values"""
        try:
            issues = []
            p = self.plugins.wgfilemanager
            if not os.path.isabs(p.left_path.value): issues.append("Left path must be absolute")
            if not os.path.isabs(p.right_path.value): issues.append("Right path must be absolute")
            
            import re
            ip_pattern = r'^((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$'
            if p.remote_ip.value and not re.match(ip_pattern, p.remote_ip.value):
                issues.append(f"Invalid IP format: {p.remote_ip.value}")
            
            if issues: return False, issues
            return True, []
        except Exception as e:
            return False, [str(e)]

    def reset_to_defaults(self):
        """Reset all configuration to defaults"""
        try:
            p = self.plugins.wgfilemanager
            p.left_path.value = "/media/hdd/"
            p.right_path.value = "/"
            p.starting_pane.value = "left"
            p.show_dirs_first.value = "yes"
            p.left_sort_mode.value = "name"
            p.right_sort_mode.value = "name"
            p.enable_smart_context.value = True
            p.ok_long_press_time.value = 400
            p.group_tools_menu.value = True
            p.trash_enabled.value = "yes"
            p.cache_enabled.value = True
            p.preview_size.value = "1024"
            p.save_left_on_exit.value = "yes"
            p.save_right_on_exit.value = "yes"
            p.use_internal_player.value = True
            p.fallback_to_external.value = True
            p.remote_ip.value = "192.168.1.10"
            p.ftp_host.value = ""
            p.ftp_port.value = 21
            p.ftp_user.value = "anonymous"
            p.ftp_pass.value = ""
            p.sftp_host.value = ""
            p.sftp_port.value = 22
            p.sftp_user.value = "root"
            p.sftp_pass.value = ""
            p.webdav_url.value = ""
            p.webdav_user.value = ""
            p.webdav_pass.value = ""
            
            for attr_name in dir(p):
                if not attr_name.startswith('_'):
                    item = getattr(p, attr_name)
                    if hasattr(item, 'save'):
                        item.save()
            config.save()
            return True
        except Exception as e:
            logger.error(f"Error resetting to defaults: {e}")
            return False

# ========================================================================
# round-10 fix pack: corrected config key types
# round-9 registered these with generic types, which SHADOWED the richer
# definitions SubtitleManager._init_config() wanted to install. Types below
# mirror the manager's own definitions so both agree. subt_* keys stay
# generic (only the subtitle menu uses them; nothing else registers them).
# ========================================================================
if not hasattr(config.plugins, 'wgfilemanager'):
    config.plugins.wgfilemanager = ConfigSubsection()
_wg_p = config.plugins.wgfilemanager


if not hasattr(_wg_p, 'subtitle_delay'):
    _wg_p.subtitle_delay = ConfigInteger(default=0, limits=(-3600000, 3600000))
if not hasattr(_wg_p, 'subtitle_font_size'):
    _wg_p.subtitle_font_size = ConfigSelection(default="24", choices=[
        ("20", "Small (20)"), ("24", "Medium (24)"), ("28", "Large (28)"),
        ("32", "Extra Large (32)"), ("36", "Huge (36)")])
if not hasattr(_wg_p, 'subtitle_font_color'):
    _wg_p.subtitle_font_color = ConfigSelection(default="#FFFFFF", choices=[
        ("#FFFFFF", "White"), ("#FFFF00", "Yellow"), ("#00FFFF", "Cyan"),
        ("#00FF00", "Green"), ("#FF0000", "Red"), ("#FF00FF", "Magenta"),
        ("#FFA500", "Orange"), ("#ADD8E6", "Light Blue")])
if not hasattr(_wg_p, 'subtitle_position'):
    _wg_p.subtitle_position = ConfigSelection(default="bottom", choices=[
        ("top", "Top"), ("center_top", "Center Top"), ("center", "Center"),
        ("center_bottom", "Center Bottom"), ("bottom", "Bottom")])
if not hasattr(_wg_p, 'subtitle_encoding'):
    _wg_p.subtitle_encoding = ConfigSelection(default="utf-8", choices=[
        ("utf-8", "UTF-8"), ("latin-1", "Latin-1"), ("cp1252", "Western (CP1252)"),
        ("cp1256", "Arabic (CP1256)"), ("cp1251", "Cyrillic (CP1251)"),
        ("gbk", "Chinese GBK"), ("big5", "Traditional Chinese")])
if not hasattr(_wg_p, 'subtitle_auto_load'):
    _wg_p.subtitle_auto_load = ConfigYesNo(default=True)
if not hasattr(_wg_p, 'subtitle_preferred_lang'):
    _wg_p.subtitle_preferred_lang = ConfigText(default="", fixed_size=False)
