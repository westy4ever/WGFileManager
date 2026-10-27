import os
from datetime import datetime
from ..constants import (
    ICON_FOLDER, ICON_VIDEO, ICON_AUDIO, ICON_IMAGE, 
    ICON_ARCHIVE, ICON_TEXT, ICON_BINARY,
    VIDEO_EXTENSIONS, AUDIO_EXTENSIONS, IMAGE_EXTENSIONS,
    ARCHIVE_EXTENSIONS, TEXT_EXTENSIONS
)

def format_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes < 0:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    
    return f"{size_bytes:.1f} YB"

def get_file_icon(file_path):
    """Get emoji icon for file type"""
    if os.path.isdir(file_path):
        return ICON_FOLDER
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext in VIDEO_EXTENSIONS:
        return ICON_VIDEO
    if ext in AUDIO_EXTENSIONS:
        return ICON_AUDIO
    if ext in IMAGE_EXTENSIONS:
        return ICON_IMAGE
    if ext in ARCHIVE_EXTENSIONS:
        return ICON_ARCHIVE
    if ext in TEXT_EXTENSIONS:
        return ICON_TEXT
    
    return ICON_BINARY

def format_time(timestamp, format_str="%Y-%m-%d %H:%M:%S"):
    """Format timestamp to readable string"""
    try:
        if isinstance(timestamp, (int, float)):
            dt = datetime.fromtimestamp(timestamp)
        elif isinstance(timestamp, datetime):
            dt = timestamp
        else:
            return str(timestamp)
        
        return dt.strftime(format_str)
    except:
        return str(timestamp)

def format_permissions(mode):
    """Format file permissions to string (e.g., rwxr-xr-x)"""
    try:
        if isinstance(mode, str):
            if mode.isdigit():
                mode = int(mode, 8)
            else:
                return mode
        
        perm_str = ''
        
        # Owner permissions
        perm_str += 'r' if mode & 0o400 else '-'
        perm_str += 'w' if mode & 0o200 else '-'
        perm_str += 'x' if mode & 0o100 else '-'
        
        # Group permissions
        perm_str += 'r' if mode & 0o040 else '-'
        perm_str += 'w' if mode & 0o020 else '-'
        perm_str += 'x' if mode & 0o010 else '-'
        
        # Other permissions
        perm_str += 'r' if mode & 0o004 else '-'
        perm_str += 'w' if mode & 0o002 else '-'
        perm_str += 'x' if mode & 0o001 else '-'
        
        # Special bits
        if mode & 0o4000:
            perm_str = perm_str[:2] + 's' + perm_str[3:]
        if mode & 0o2000:
            perm_str = perm_str[:5] + 's' + perm_str[6:]
        if mode & 0o1000:
            perm_str = perm_str[:-1] + 't'
        
        return perm_str
    except:
        return "---------"

def format_duration(seconds):
    """Format duration in seconds to readable string"""
    try:
        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
    except:
        return "0s"

def format_percentage(value, total):
    """Format percentage"""
    try:
        if total == 0:
            return "0%"
        percentage = (value / total) * 100
        return f"{percentage:.1f}%"
    except:
        return "0%"

def truncate_text(text, max_length=50, ellipsis="..."):
    """Truncate text to maximum length"""
    if not text:
        return ""
    
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(ellipsis)] + ellipsis

def format_list(items, max_items=10, separator=", "):
    """Format list of items"""
    if not items:
        return ""
    
    if len(items) <= max_items:
        return separator.join(str(item) for item in items)
    
    shown = items[:max_items]
    remaining = len(items) - max_items
    return separator.join(str(item) for item in shown) + f" and {remaining} more"

def format_file_type(file_path):
    """Get human-readable file type"""
    if os.path.isdir(file_path):
        return "Directory"
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext in VIDEO_EXTENSIONS:
        return "Video File"
    if ext in AUDIO_EXTENSIONS:
        return "Audio File"
    if ext in IMAGE_EXTENSIONS:
        return "Image File"
    if ext in ARCHIVE_EXTENSIONS:
        return "Archive File"
    if ext in TEXT_EXTENSIONS:
        return "Text File"
    if ext == '':
        return "File"
    
    return f"{ext.upper()[1:]} File"
# ==== added by round-6 fix pack (missing imports) ====

def format_subtitle_time(seconds, milliseconds=False):
    """Format a time value as an SRT-style subtitle timestamp HH:MM:SS,mmm.
    Pass milliseconds=True if the value is in ms. (round-6 fix pack)"""
    if seconds is None:
        return "00:00:00,000"
    try:
        t = float(seconds)
    except (TypeError, ValueError):
        return "00:00:00,000"
    if milliseconds:
        t = t / 1000.0
    if t < 0:
        t = 0.0
    h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms >= 1000:
        s += 1; ms -= 1000
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)

def parse_subtitle_timestamp(ts):
    """Parse 'HH:MM:SS,mmm' (or 'HH:MM:SS.mmm', 'MM:SS', plain seconds)
    into float seconds. Returns 0.0 for unparseable input.
    (round-7: replaced stub)"""
    if not ts:
        return 0.0
    t = str(ts).strip().replace(",", ".")
    try:
        parts = t.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(t)
    except (TypeError, ValueError):
        return 0.0
