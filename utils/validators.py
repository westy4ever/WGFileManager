import os
import re
import shlex

def validate_path(path, must_exist=False, must_be_dir=False, must_be_file=False, is_filename=False):
    """
    Validate file path with enhanced security
    
    Args:
        path: Path to validate
        must_exist: If True, path must exist
        must_be_dir: If True, path must be a directory
        must_be_file: If True, path must be a file
        is_filename: If True, validate as filename only (no path)
    
    Returns:
        bool: True if path is valid
    """
    if not path or not isinstance(path, str):
        return False
    
    # SECURITY FIX: Enhanced path traversal protection
    if is_filename:
        # For filenames, check invalid characters
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '\x00']
        if any(char in path for char in invalid_chars):
            return False
        
        # Check reserved names (Windows compatibility)
        reserved = ['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4',
                   'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2',
                   'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9']
        name_upper = os.path.splitext(path)[0].upper()
        if name_upper in reserved:
            return False
        
        return len(path) <= 255
    
    # For full paths
    # Check for null bytes
    if '\x00' in path:
        return False
    
    # Normalize path and check for directory traversal
    try:
        normalized = os.path.normpath(os.path.abspath(path))
    except (ValueError, OSError):
        return False
    
    # Define allowed base directories
    allowed_bases = [
        '/media', '/tmp', '/home', '/var/volatile',
        '/usr/lib/enigma2/python/Plugins'
    ]
    
    # Check if path starts with allowed base (unless checking system paths)
    if not path.startswith('/etc/enigma2'):  # Allow Enigma2 config
        if not any(normalized.startswith(base) for base in allowed_bases):
            # Additional check: allow if it's under current working directory
            try:
                cwd = os.getcwd()
                if not normalized.startswith(cwd):
                    return False
            except:
                return False
    
    # Prevent access to sensitive system files
    forbidden_paths = [
        '/etc/passwd', '/etc/shadow', '/etc/sudoers',
        '/root/.ssh', '/etc/ssh'
    ]
    if any(normalized.startswith(forbidden) for forbidden in forbidden_paths):
        return False
    
    # Check if path exists if required
    if must_exist and not os.path.exists(path):
        return False
    
    # Check if path is directory if required
    if must_be_dir and not os.path.isdir(path):
        return False
    
    # Check if path is file if required
    if must_be_file and not os.path.isfile(path):
        return False
    
    return True

def validate_ip(ip_address):
    """Validate IP address (IPv4)"""
    if not ip_address or not isinstance(ip_address, str):
        return False
    
    ipv4_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    
    if not re.match(ipv4_pattern, ip_address):
        return False
    
    parts = ip_address.split('.')
    for part in parts:
        try:
            num = int(part)
            if num < 0 or num > 255:
                return False
        except ValueError:
            return False
    
    return True

def validate_hostname(hostname):
    """Validate hostname"""
    if not hostname or not isinstance(hostname, str):
        return False
    
    pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
    
    return bool(re.match(pattern, hostname)) and len(hostname) <= 255

def validate_url(url):
    """Validate URL"""
    if not url or not isinstance(url, str):
        return False
    
    pattern = r'^(https?|ftp|file)://.+'
    
    return bool(re.match(pattern, url))

def validate_port(port):
    """Validate port number"""
    try:
        port_num = int(port)
        return 1 <= port_num <= 65535
    except (ValueError, TypeError):
        return False

def sanitize_string(text, max_length=255, allow_special=False):
    """
    Sanitize input string
    
    Args:
        text: Text to sanitize
        max_length: Maximum allowed length
        allow_special: Allow special characters
    
    Returns:
        str: Sanitized string or empty string if invalid
    """
    if not text or not isinstance(text, str):
        return ""
    
    # Remove null bytes and control characters
    text = ''.join(char for char in text if ord(char) >= 32)
    
    # Truncate to max length
    text = text[:max_length]
    
    if not allow_special:
        # Remove potentially dangerous characters
        dangerous = [';', '|', '&', '$', '`', '>', '<', '!']
        for char in dangerous:
            text = text.replace(char, '')
    
    return text.strip()

def validate_filename(filename):
    """Validate filename"""
    return validate_path(filename, is_filename=True)

def validate_email(email):
    """Validate email address"""
    if not email or not isinstance(email, str):
        return False
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_integer(value, min_value=None, max_value=None):
    """Validate integer"""
    try:
        num = int(value)
        
        if min_value is not None and num < min_value:
            return False
        
        if max_value is not None and num > max_value:
            return False
        
        return True
    except (ValueError, TypeError):
        return False

def validate_float(value, min_value=None, max_value=None):
    """Validate float"""
    try:
        num = float(value)
        
        if min_value is not None and num < min_value:
            return False
        
        if max_value is not None and num > max_value:
            return False
        
        return True
    except (ValueError, TypeError):
        return False

def escape_shell_argument(arg):
    """Escape shell argument to prevent injection"""
    return shlex.quote(str(arg))

def validate_json(text):
    """Validate JSON string"""
    import json
    
    try:
        json.loads(text)
        return True
    except (ValueError, TypeError):
        return False

def validate_regex(pattern):
    """Validate regex pattern"""
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False

# ==== added by round-6 fix pack (missing imports) ====

def validate_mac_address(mac):
    """True if mac looks like AA:BB:CC:DD:EE:FF (colons or dashes).
    (round-7: replaced stub)"""
    import re
    if not isinstance(mac, str):
        return False
    return bool(re.fullmatch(r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", mac.strip()))
