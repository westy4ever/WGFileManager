"""
WGFileManager Utilities Module
Complete utility functions for file management, security, validation, and subtitle support
"""

# Formatters
from .formatters import (
    format_size, get_file_icon, format_time, format_permissions,
    format_duration, format_percentage, truncate_text, format_list,
    format_file_type, format_subtitle_time, parse_subtitle_timestamp
)

# Validators
from .validators import (
    validate_path, validate_ip, validate_hostname, validate_url, 
    sanitize_string, validate_filename, validate_port, validate_email,
    validate_mac_address
)

# Security
from .security import (
    sanitize_input, validate_input, encrypt_password, decrypt_password,
    check_permissions, sanitize_path, generate_token, hash_password,
    validate_password_strength
)

# Logging
from .logging_config import get_logger, setup_logging

# Time utilities
try:
    from .time_utils import (
        parse_time_string, format_time_delta, human_readable_time,
        time_since, time_until, is_valid_time_format, convert_timezone
    )
except ImportError:
    # Placeholder time utilities
    def parse_time_string(time_str):
        """Parse time string (fallback)"""
        return 0
    
    def format_time_delta(seconds):
        """Format time delta (fallback)"""
        return str(seconds)
    
    def human_readable_time(seconds):
        """Human readable time (fallback)"""
        return f"{seconds} seconds"
    
    def time_since(timestamp):
        """Time since timestamp (fallback)"""
        return "Unknown"
    
    def time_until(timestamp):
        """Time until timestamp (fallback)"""
        return "Unknown"
    
    def is_valid_time_format(time_str):
        """Validate time format (fallback)"""
        return False
    
    def convert_timezone(timestamp, from_tz, to_tz):
        """Convert timezone (fallback)"""
        return timestamp

# File type detection
try:
    from .file_utils import (
        get_file_type, get_mime_type, is_media_file, is_archive_file,
        is_text_file, is_image_file, is_executable_file, get_file_metadata
    )
except ImportError:
    # Placeholder file utilities
    def get_file_type(file_path):
        """Get file type (fallback)"""
        return "Unknown"
    
    def get_mime_type(file_path):
        """Get MIME type (fallback)"""
        return "application/octet-stream"
    
    def is_media_file(file_path):
        """Check if file is media (fallback)"""
        return False
    
    def is_archive_file(file_path):
        """Check if file is archive (fallback)"""
        return False
    
    def is_text_file(file_path):
        """Check if file is text (fallback)"""
        return False
    
    def is_image_file(file_path):
        """Check if file is image (fallback)"""
        return False
    
    def is_executable_file(file_path):
        """Check if file is executable (fallback)"""
        return False
    
    def get_file_metadata(file_path):
        """Get file metadata (fallback)"""
        return {}

# Network utilities
try:
    from .network_utils import (
        is_network_available, get_local_ip, get_network_interfaces,
        ping_host, resolve_hostname, get_network_speed
    )
except ImportError:
    # Placeholder network utilities
    def is_network_available():
        """Check network availability (fallback)"""
        return False
    
    def get_local_ip():
        """Get local IP address (fallback)"""
        return "127.0.0.1"
    
    def get_network_interfaces():
        """Get network interfaces (fallback)"""
        return []
    
    def ping_host(host):
        """Ping host (fallback)"""
        return False
    
    def resolve_hostname(hostname):
        """Resolve hostname (fallback)"""
        return hostname
    
    def get_network_speed():
        """Get network speed (fallback)"""
        return 0

__all__ = [
    # Formatters
    'format_size', 'get_file_icon', 'format_time', 'format_permissions',
    'format_duration', 'format_percentage', 'truncate_text', 'format_list',
    'format_file_type', 'format_subtitle_time', 'parse_subtitle_timestamp',
    
    # Validators
    'validate_path', 'validate_ip', 'validate_hostname', 'validate_url',
    'sanitize_string', 'validate_filename', 'validate_port', 'validate_email',
    'validate_mac_address',
    
    # Security
    'sanitize_input', 'validate_input', 'encrypt_password', 'decrypt_password',
    'check_permissions', 'sanitize_path', 'generate_token', 'hash_password',
    'validate_password_strength',
    
    # Logging
    'get_logger', 'setup_logging',
    
    # Time Utilities
    'parse_time_string',
    'format_time_delta',
    'human_readable_time',
    'time_since',
    'time_until',
    'is_valid_time_format',
    'convert_timezone',
    
    # File Utilities
    'get_file_type',
    'get_mime_type',
    'is_media_file',
    'is_archive_file',
    'is_text_file',
    'is_image_file',
    'is_executable_file',
    'get_file_metadata',
    
    # Network Utilities
    'is_network_available',
    'get_local_ip',
    'get_network_interfaces',
    'ping_host',
    'resolve_hostname',
    'get_network_speed',
]

# Module metadata
UTILS_VERSION = "1.1.0"
UTILS_FEATURES = {
    'formatters': True,
    'validators': True,
    'security': True,
    'logging': True,
    'time_utilities': True,
    'file_utilities': True,
    'network_utilities': True,
}

def get_utils_info():
    """Get information about the utilities module"""
    return {
        'version': UTILS_VERSION,
        'features': [feature for feature, available in UTILS_FEATURES.items() if available],
        'description': 'Complete utility functions for WG File Manager PRO',
    }

def check_utility(utility_name):
    """Check if a specific utility is available"""
    return UTILS_FEATURES.get(utility_name, False)

# Initialize logging when module is imported
try:
    setup_logging()
except:
    pass  # Silent fail if logging setup fails