import re
import base64
import hashlib
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Protocol.KDF import PBKDF2

# Check if crypto is available
try:
    from Crypto.Cipher import AES
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

def sanitize_input(text, pattern=r'^[a-zA-Z0-9\s\-_.@/]+$'):
    """
    Sanitize user input to prevent injection attacks
    
    Args:
        text: Input text to sanitize
        pattern: Regex pattern for allowed characters
    
    Returns:
        bool: True if input is valid
    """
    if not text:
        return False
    
    text = str(text).strip()
    
    # Check against pattern
    if not re.match(pattern, text):
        return False
    
    # Check for path traversal
    if '..' in text or text.startswith('/etc') or text.startswith('/sys'):
        return False
    
    # Check for command injection
    dangerous = [';', '|', '&', '$', '`', '>', '<', '!', '\n', '\r']
    for char in dangerous:
        if char in text:
            return False
    
    return True

def validate_input(text, min_length=1, max_length=255, input_type="text"):
    """
    Validate user input with type checking
    
    Args:
        text: Input text to validate
        min_length: Minimum allowed length
        max_length: Maximum allowed length
        input_type: Type of input ('text', 'number', 'email', 'path', 'filename')
    
    Returns:
        tuple: (is_valid, error_message)
    """
    if not text or not isinstance(text, str):
        return False, "Input is required"
    
    text = text.strip()
    
    # Check length
    if len(text) < min_length:
        return False, f"Input must be at least {min_length} characters"
    
    if len(text) > max_length:
        return False, f"Input must be at most {max_length} characters"
    
    # Type-specific validation
    if input_type == "number":
        if not text.isdigit():
            return False, "Input must be a number"
    
    elif input_type == "email":
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, text):
            return False, "Invalid email format"
    
    elif input_type == "path":
        # Check for path traversal
        if '..' in text or '\x00' in text:
            return False, "Invalid path"
        
        # Check for dangerous characters in paths
        dangerous = [';', '|', '&', '$', '`', '>', '<', '!']
        for char in dangerous:
            if char in text:
                return False, "Invalid characters in path"
    
    elif input_type == "filename":
        # Check for invalid filename characters
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '\x00']
        for char in invalid_chars:
            if char in text:
                return False, "Invalid characters in filename"
        
        # Check for reserved names
        reserved = ['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'LPT1']
        name_without_ext = text.split('.')[0].upper()
        if name_without_ext in reserved:
            return False, "Reserved filename"
    
    return True, ""

def hash_password(password, salt=None):
    """
    Hash password with salt
    
    Args:
        password: Password to hash
        salt: Optional salt (will generate if None)
    
    Returns:
        tuple: (hashed_password, salt)
    """
    if salt is None:
        salt = get_random_bytes(32)
    
    # Use PBKDF2 for key derivation
    key = PBKDF2(password, salt, dkLen=32, count=100000)
    
    # Hash the key
    hashed = hashlib.sha256(key).digest()
    
    return base64.b64encode(hashed).decode('utf-8'), base64.b64encode(salt).decode('utf-8')

def verify_password(password, hashed_password, salt):
    """
    Verify password against hash
    
    Args:
        password: Password to verify
        hashed_password: Stored hash
        salt: Stored salt
    
    Returns:
        bool: True if password matches
    """
    try:
        salt_bytes = base64.b64decode(salt)
        computed_hash, _ = hash_password(password, salt_bytes)
        return computed_hash == hashed_password
    except:
        return False

def encrypt_password(password, key=None):
    """
    Encrypt password (if crypto is available)
    
    Args:
        password: Password to encrypt
        key: Encryption key (will generate if None)
    
    Returns:
        tuple: (encrypted_password, key, iv) or (None, None, None) if crypto not available
    """
    if not CRYPTO_AVAILABLE:
        return None, None, None
    
    try:
        if key is None:
            key = get_random_bytes(32)
        
        # Generate IV
        iv = get_random_bytes(16)
        
        # Create cipher
        cipher = AES.new(key, AES.MODE_CBC, iv)
        
        # Pad password
        block_size = AES.block_size
        padding_length = block_size - (len(password) % block_size)
        padding = bytes([padding_length]) * padding_length
        padded_password = password.encode('utf-8') + padding
        
        # Encrypt
        encrypted = cipher.encrypt(padded_password)
        
        return (
            base64.b64encode(encrypted).decode('utf-8'),
            base64.b64encode(key).decode('utf-8'),
            base64.b64encode(iv).decode('utf-8')
        )
    except Exception as e:
        print(f"Encryption error: {e}")
        return None, None, None

def decrypt_password(encrypted_password, key, iv):
    """
    Decrypt password (if crypto is available)
    
    Args:
        encrypted_password: Encrypted password
        key: Encryption key
        iv: Initialization vector
    
    Returns:
        str: Decrypted password or None if decryption fails
    """
    if not CRYPTO_AVAILABLE:
        return None
    
    try:
        # Decode from base64
        encrypted_bytes = base64.b64decode(encrypted_password)
        key_bytes = base64.b64decode(key)
        iv_bytes = base64.b64decode(iv)
        
        # Create cipher
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
        
        # Decrypt
        decrypted = cipher.decrypt(encrypted_bytes)
        
        # Remove padding
        padding_length = decrypted[-1]
        if padding_length < 1 or padding_length > AES.block_size:
            return None
        
        return decrypted[:-padding_length].decode('utf-8')
    except Exception as e:
        print(f"Decryption error: {e}")
        return None

def generate_api_key(length=32):
    """
    Generate random API key
    
    Args:
        length: Length of API key
    
    Returns:
        str: Random API key
    """
    import secrets
    import string
    
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_secure_token(length=64):
    """
    Generate secure random token
    
    Args:
        length: Length of token
    
    Returns:
        str: Random token
    """
    import secrets
    return secrets.token_urlsafe(length)

def mask_sensitive_data(data):
    """
    Mask sensitive data for logging
    
    Args:
        data: Data to mask
    
    Returns:
        str: Masked data
    """
    if not data or not isinstance(data, str):
        return ""
    
    # Mask passwords in URLs
    url_pattern = r'(https?://[^:]+):([^@]+)@'
    masked = re.sub(url_pattern, r'\1:****@', data)
    
    # Mask passwords in command lines
    password_patterns = [
        r'(--password=)([^\s]+)',
        r'(-p\s+)([^\s]+)',
        r'(passwd=)([^\s]+)',
        r'(password:\s*)([^\s]+)'
    ]
    
    for pattern in password_patterns:
        masked = re.sub(pattern, r'\1****', masked)
    
    # Mask API keys
    api_key_pattern = r'([A-Za-z0-9]{32,})'
    # This is a simple pattern, might need adjustment
    masked = re.sub(api_key_pattern, '****', masked)
    
    return masked

def check_file_permissions(filepath):
    """
    Check file permissions for security
    
    Args:
        filepath: Path to check
    
    Returns:
        tuple: (is_secure, issues)
    """
    import os
    import stat
    
    issues = []
    
    try:
        st = os.stat(filepath)
        
        # Check if file is world-writable
        if st.st_mode & stat.S_IWOTH:
            issues.append("File is world-writable")
        
        # Check if file is owned by root but writable by others
        if st.st_uid == 0 and (st.st_mode & stat.S_IWGRP or st.st_mode & stat.S_IWOTH):
            issues.append("Root-owned file is writable by others")
        
        # Check if file is a symlink (potential security issue)
        if os.path.islink(filepath):
            issues.append("File is a symbolic link")
        
        return len(issues) == 0, issues
    
    except Exception as e:
        return False, [f"Error checking permissions: {e}"]
# ==== added by round-6 fix pack (missing imports) ====

def check_permissions(path, mode="r"):
    """Check access to a path. mode: string containing r, w and/or x.
    (round-7: replaced stub)"""
    import os
    flags = {"r": os.R_OK, "w": os.W_OK, "x": os.X_OK}
    mask = 0
    for ch in str(mode):
        mask |= flags.get(ch, 0)
    if not mask:
        mask = os.F_OK
    return os.access(path, mask)

def generate_token(length=32):
    """Generate a random hex token of roughly 'length' characters.
    (round-7: replaced stub)"""
    import secrets
    try:
        length = int(length)
    except (TypeError, ValueError):
        length = 32
    if length < 2:
        length = 2
    return secrets.token_hex(length // 2)

def sanitize_path(path):
    """Clean a path string: strip quotes/whitespace and null bytes,
    then normalise. (round-7: replaced stub)"""
    import os
    if path is None:
        return ""
    p = str(path).strip().strip('"').strip("'")
    p = p.replace("\x00", "")
    return os.path.normpath(p) if p else ""

def validate_password_strength(*args, **kwargs):
    """TEMPORARY STUB added by round-6 fix pack - real code pending."""
    import logging
    logging.getLogger("WGFileManager.STUB").warning("STUB called: validate_password_strength")
    return None
