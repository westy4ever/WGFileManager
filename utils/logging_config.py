import logging
import logging.handlers
import os
from datetime import datetime

# Default log file path
DEFAULT_LOG_FILE = "/tmp/wgfilemanager.log"
DEFAULT_LOG_LEVEL = logging.WARNING
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5

def setup_logging():
    """Set up logging for WGFileManager.

    Writes to /tmp/wgfilemanager.log (with rotation) and mirrors
    warnings+ to the console. Handlers attach ONLY to this plugin's
    "WGFileManager" logger - the old version hijacked the root logger,
    which would have redirected the whole system's logging.

    round-7 fix pack: max_size / backup_count / level were undefined
    names (NameError) so no log file was ever created; the dead code
    after the first return is also removed.
    """
    log_file = "/tmp/wgfilemanager.log"

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    logger = logging.getLogger("WGFileManager")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Clear only OUR handlers so re-calls don't duplicate lines
    for h in list(logger.handlers):
        logger.removeHandler(h)

    # Console handler: warnings and worse only (keeps the box quiet)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler: everything, with rotation. If it can't be created,
    # keep going console-only instead of crashing the plugin.
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=MAX_LOG_SIZE,
            backupCount=BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print("[WGFileManager] could not create %s: %s" % (log_file, e))

    logger.info("WGFileManager logging initialised -> %s", log_file)
    return logger

def get_logger(name):
    """Get a logger instance with proper naming"""
    # Extract module name
    if name.startswith('Plugins.Extensions.WGFileManager.'):
        name = name.replace('Plugins.Extensions.WGFileManager.', '')
    
    # Special handling for subtitle modules
    if 'subtitle' in name.lower():
        return logging.getLogger(f'WGFileManager.Subtitle.{name}')
    
    return logging.getLogger(f'WGFileManager.{name}')

def log_exception(logger, exception, context=""):
    """
    Log exception with context
    
    Args:
        logger: Logger instance
        exception: Exception to log
        context: Context information
    """
    if context:
        logger.error(f"{context}: {exception}", exc_info=True)
    else:
        logger.error(f"Exception: {exception}", exc_info=True)

def log_operation(logger, operation, status, details=""):
    """
    Log operation with status
    
    Args:
        logger: Logger instance
        operation: Operation name
        status: Status (success, failed, etc.)
        details: Additional details
    """
    message = f"Operation: {operation} - Status: {status}"
    if details:
        message += f" - Details: {details}"
    
    if status.lower() in ["success", "completed", "ok"]:
        logger.info(message)
    elif status.lower() in ["failed", "error", "exception"]:
        logger.error(message)
    else:
        logger.warning(message)

def log_performance(logger, operation, start_time, end_time=None, details=""):
    """
    Log performance metrics
    
    Args:
        logger: Logger instance
        operation: Operation name
        start_time: Start time (datetime or timestamp)
        end_time: End time (datetime or timestamp, defaults to now)
        details: Additional details
    """
    if end_time is None:
        end_time = datetime.now()
    
    # Convert to datetime if needed
    if isinstance(start_time, (int, float)):
        start_time = datetime.fromtimestamp(start_time)
    if isinstance(end_time, (int, float)):
        end_time = datetime.fromtimestamp(end_time)
    
    # Calculate duration
    duration = (end_time - start_time).total_seconds()
    
    message = f"Performance: {operation} - Duration: {duration:.3f}s"
    if details:
        message += f" - {details}"
    
    logger.info(message)

def log_security_event(logger, event_type, severity, details):
    """
    Log security event
    
    Args:
        logger: Logger instance
        event_type: Type of security event
        severity: Severity level (info, warning, error, critical)
        details: Event details
    """
    message = f"Security: {event_type} - {details}"
    
    if severity == "critical":
        logger.critical(message)
    elif severity == "error":
        logger.error(message)
    elif severity == "warning":
        logger.warning(message)
    else:
        logger.info(message)

def cleanup_old_logs(log_dir, pattern="*.log", days_to_keep=30):
    """
    Cleanup old log files
    
    Args:
        log_dir: Directory containing log files
        pattern: File pattern to match
        days_to_keep: Number of days to keep logs
    
    Returns:
        int: Number of files deleted
    """
    import glob
    import time
    
    if not os.path.isdir(log_dir):
        return 0
    
    deleted = 0
    cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
    
    for log_file in glob.glob(os.path.join(log_dir, pattern)):
        try:
            if os.path.getmtime(log_file) < cutoff_time:
                os.remove(log_file)
                deleted += 1
        except Exception as e:
            logger = get_logger(__name__)
            logger.warning(f"Failed to delete old log file {log_file}: {e}")
    
    return deleted

def get_log_stats(log_file):
    """
    Get statistics from log file
    
    Args:
        log_file: Path to log file
    
    Returns:
        dict: Log statistics
    """
    stats = {
        'file_size': 0,
        'last_modified': None,
        'line_count': 0,
        'error_count': 0,
        'warning_count': 0,
        'info_count': 0
    }
    
    if not os.path.exists(log_file):
        return stats
    
    try:
        stats['file_size'] = os.path.getsize(log_file)
        stats['last_modified'] = datetime.fromtimestamp(os.path.getmtime(log_file))
        
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                stats['line_count'] += 1
                if 'ERROR' in line:
                    stats['error_count'] += 1
                elif 'WARNING' in line:
                    stats['warning_count'] += 1
                elif 'INFO' in line:
                    stats['info_count'] += 1
    
    except Exception as e:
        logger = get_logger(__name__)
        logger.error(f"Failed to get log stats: {e}")
    
    return stats