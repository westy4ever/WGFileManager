import ftplib
import os
from datetime import datetime
from ..constants import DEFAULT_FTP_PORT, DEFAULT_TIMEOUT
from ..exceptions import RemoteConnectionError, NetworkError
from ..utils.validators import validate_hostname, validate_port
from ..utils.logging_config import get_logger

logger = get_logger(__name__)

class FTPClient:
    def __init__(self, config):
        self.config = config
        self.connection = None
        self.timeout = DEFAULT_TIMEOUT
    
    def connect(self, host, port=DEFAULT_FTP_PORT, username="anonymous", password="", timeout=None):
        """Connect to FTP server"""
        try:
            validate_hostname(host)
            validate_port(port)
            
            if timeout is None:
                timeout = self.timeout
            
            self.connection = ftplib.FTP()
            self.connection.connect(host, port, timeout=timeout)
            self.connection.login(username, password)
            
            return True, "Connected successfully"
            
        except ftplib.error_perm as e:
            raise RemoteConnectionError(f"Authentication failed: {e}")
        except ftplib.error_temp as e:
            raise NetworkError(f"Temporary FTP error: {e}")
        except ftplib.error_reply as e:
            raise RemoteConnectionError(f"FTP protocol error: {e}")
        except ConnectionRefusedError:
            raise NetworkError(f"Connection refused to {host}:{port}")
        except TimeoutError:
            raise NetworkError(f"Connection timeout to {host}:{port}")
        except Exception as e:
            raise RemoteConnectionError(f"FTP connection failed: {e}")
    
    def disconnect(self):
        """Disconnect from FTP server"""
        if not self.connection:
            return True
            
        try:
            self.connection.quit()
            self.connection = None
            return True
        except (ftplib.error_perm, ftplib.error_temp) as e:
            logger.warning(f"Error during quit: {e}")
            # Try to close forcefully
            try:
                if self.connection:
                    self.connection.close()
                    self.connection = None
            except Exception as close_error:
                logger.error(f"Error during force close: {close_error}")
            return False
        except Exception as e:
            logger.error(f"Unexpected disconnect error: {e}")
            try:
                if self.connection:
                    self.connection.close()
                    self.connection = None
            except Exception:
                pass
            return False
    
    def is_connected(self):
        """Check if connected to FTP server"""
        if not self.connection:
            return False
        
        try:
            # Send a NOOP command to check connection
            self.connection.voidcmd("NOOP")
            return True
        except Exception:
            return False
    
    def test_connection(self, host, port=DEFAULT_FTP_PORT, username="anonymous", password=""):
        """Test FTP connection"""
        try:
            success, message = self.connect(host, port, username, password)
            if success:
                self.disconnect()
                return True, message
            return False, message
        except Exception as e:
            return False, str(e)
    
    def list_directory(self, path="/"):
        """List directory contents"""
        try:
            if not self.is_connected():
                raise RemoteConnectionError("Not connected to FTP server")
            
            # Try MLSD first (structured listing)
            try:
                entries = []
                for name, facts in self.connection.mlsd(path):
                    if name in ['.', '..']:
                        continue
                    
                    is_dir = facts.get('type', '').lower() == 'dir'
                    size = int(facts.get('size', 0))
                    
                    # Parse modify time if available
                    date = None
                    if 'modify' in facts:
                        try:
                            # Format: YYYYMMDDhhmmss
                            date_str = facts['modify']
                            date = datetime.strptime(date_str, "%Y%m%d%H%M%S")
                        except Exception:
                            pass
                    
                    entries.append({
                        'name': name,
                        'path': os.path.join(path, name) if path != '/' else '/' + name,
                        'is_dir': is_dir,
                        'is_link': False,
                        'size': size,
                        'permissions': facts.get('unix.mode', ''),
                        'date': date
                    })
                
                return entries
                
            except (ftplib.error_perm, AttributeError):
                # MLSD not supported, fall back to DIR
                pass
            
            # Fallback: Use DIR command
            if path and path != "/":
                self.connection.cwd(path)
            
            # Get directory listing
            lines = []
            self.connection.dir(lines.append)
            
            # Parse directory listing
            entries = []
            for line in lines:
                try:
                    parts = line.split()
                    if len(parts) >= 9:
                        # Typical format: drwxr-xr-x 2 user group 4096 Jan 1 00:00 filename
                        permissions = parts[0]
                        name = ' '.join(parts[8:])
                        
                        # Check if it's a directory or file
                        is_dir = permissions.startswith('d')
                        is_link = permissions.startswith('l')
                        
                        # Try to extract size
                        size = 0
                        try:
                            size = int(parts[4])
                        except (ValueError, IndexError):
                            pass
                        
                        # Try to extract date
                        date_str = ' '.join(parts[5:8])
                        date = None
                        try:
                            date = datetime.strptime(date_str, "%b %d %H:%M")
                            # Add current year
                            date = date.replace(year=datetime.now().year)
                        except Exception:
                            pass
                        
                        entries.append({
                            'name': name,
                            'path': os.path.join(path, name) if path != '/' else '/' + name,
                            'is_dir': is_dir,
                            'is_link': is_link,
                            'size': size,
                            'permissions': permissions,
                            'date': date,
                            'full_line': line
                        })
                except Exception as parse_error:
                    logger.warning(f"Failed to parse FTP listing line: {parse_error}")
                    continue
            
            return entries
            
        except ftplib.error_perm as e:
            raise RemoteConnectionError(f"Permission denied: {e}")
        except Exception as e:
            raise RemoteConnectionError(f"List directory failed: {e}")
    
    def download_file(self, remote_path, local_path):
        """Download file from FTP server"""
        try:
            if not self.is_connected():
                raise RemoteConnectionError("Not connected to FTP server")
            
            # Create local directory if it doesn't exist
            local_dir = os.path.dirname(local_path)
            if local_dir and not os.path.exists(local_dir):
                os.makedirs(local_dir, exist_ok=True)
            
            # Download file
            with open(local_path, 'wb') as f:
                self.connection.retrbinary(f'RETR {remote_path}', f.write)
            
            return True, f"Downloaded: {remote_path}"
            
        except ftplib.error_perm as e:
            raise RemoteConnectionError(f"Permission denied: {e}")
        except Exception as e:
            raise RemoteConnectionError(f"Download failed: {e}")
    
    def upload_file(self, local_path, remote_path):
        """Upload file to FTP server"""
        try:
            if not self.is_connected():
                raise RemoteConnectionError("Not connected to FTP server")
            
            if not os.path.exists(local_path):
                raise RemoteConnectionError(f"Local file not found: {local_path}")
            
            # Upload file
            with open(local_path, 'rb') as f:
                self.connection.storbinary(f'STOR {remote_path}', f)
            
            return True, f"Uploaded: {remote_path}"
            
        except ftplib.error_perm as e:
            raise RemoteConnectionError(f"Permission denied: {e}")
        except Exception as e:
            raise RemoteConnectionError(f"Upload failed: {e}")
    
    def create_directory(self, path):
        """Create directory on FTP server"""
        try:
            if not self.is_connected():
                raise RemoteConnectionError("Not connected to FTP server")
            
            self.connection.mkd(path)
            return True, f"Created directory: {path}"
            
        except ftplib.error_perm as e:
            raise RemoteConnectionError(f"Permission denied: {e}")
        except Exception as e:
            raise RemoteConnectionError(f"Create directory failed: {e}")
    
    def delete_file(self, path):
        """Delete file on FTP server"""
        try:
            if not self.is_connected():
                raise RemoteConnectionError("Not connected to FTP server")
            
            self.connection.delete(path)
            return True, f"Deleted: {path}"
            
        except ftplib.error_perm as e:
            raise RemoteConnectionError(f"Permission denied: {e}")
        except Exception as e:
            raise RemoteConnectionError(f"Delete failed: {e}")
    
    def delete_directory(self, path):
        """Delete directory on FTP server"""
        try:
            if not self.is_connected():
                raise RemoteConnectionError("Not connected to FTP server")
            
            self.connection.rmd(path)
            return True, f"Deleted directory: {path}"
            
        except ftplib.error_perm as e:
            raise RemoteConnectionError(f"Permission denied: {e}")
        except Exception as e:
            raise RemoteConnectionError(f"Delete directory failed: {e}")
    
    def rename(self, old_path, new_path):
        """Rename file or directory on FTP server"""
        try:
            if not self.is_connected():
                raise RemoteConnectionError("Not connected to FTP server")
            
            self.connection.rename(old_path, new_path)
            return True, f"Renamed {old_path} to {new_path}"
            
        except ftplib.error_perm as e:
            raise RemoteConnectionError(f"Permission denied: {e}")
        except Exception as e:
            raise RemoteConnectionError(f"Rename failed: {e}")
    
    def get_file_size(self, path):
        """Get file size from FTP server"""
        try:
            if not self.is_connected():
                raise RemoteConnectionError("Not connected to FTP server")
            
            # Use SIZE command if supported
            try:
                size = self.connection.size(path)
                if size is not None:
                    return size
            except (ftplib.error_perm, AttributeError):
                pass
            
            # Fallback: list directory and find file
            dir_path = os.path.dirname(path)
            file_name = os.path.basename(path)
            
            entries = self.list_directory(dir_path)
            for entry in entries:
                if entry['name'] == file_name and not entry['is_dir']:
                    return entry['size']
            
            return 0
            
        except Exception as e:
            raise RemoteConnectionError(f"Get file size failed: {e}")
