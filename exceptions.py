"""
Custom Exceptions for WGFileManager
"""

class WGFileManagerError(Exception):
    """Base exception for WGFileManager"""
    pass

class SubtitleError(WGFileManagerError):
    """Subtitle-related errors"""
    pass

class SubtitleNotFoundError(SubtitleError):
    """Subtitle file not found"""
    pass

class SubtitleFormatError(SubtitleError):
    """Unsupported subtitle format"""
    pass

class SubtitleEncodingError(SubtitleError):
    """Subtitle encoding error"""
    pass

class SubtitleSyncError(SubtitleError):
    """Subtitle synchronization error"""
    pass

class SubtitleDownloadError(SubtitleError):
    """Subtitle download error"""
    pass

class PlayerError(WGFileManagerError):
    """Player-related errors"""
    pass

class FileOperationError(WGFileManagerError):
    """File operation errors"""
    pass

class NetworkError(WGFileManagerError):
    """Network-related errors"""
    pass

class PermissionError(WGFileManagerError):
    """Permission denied"""
    pass

class DiskSpaceError(WGFileManagerError):
    """Insufficient disk space"""
    pass

class CacheError(WGFileManagerError):
    """Cache operation failed"""
    pass

class RemoteConnectionError(WGFileManagerError):
    """Remote connection failed"""
    pass

class InvalidInputError(WGFileManagerError):
    """Invalid user input"""
    pass

class ArchiveError(WGFileManagerError):
    """Archive operation failed"""
    pass

class MediaPlaybackError(WGFileManagerError):
    """Media playback failed"""
    pass