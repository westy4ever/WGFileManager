import subprocess
import os
from ..constants import DEFAULT_SFTP_PORT, DEFAULT_TIMEOUT
from ..exceptions import RemoteConnectionError, NetworkError
from ..utils.validators import validate_hostname, validate_port, sanitize_string
import shlex

class SFTPClient:
    def __init__(self, config):
        self.config = config
        self.timeout = DEFAULT_TIMEOUT
    
    def test_connection(self, host, port=DEFAULT_SFTP_PORT, username="root", password=""):
        """Test SSH/SFTP connection using sshpass"""
        try:
            validate_hostname(host)
            validate_port(port)
            
            # Check if sshpass is available
            sshpass_check = subprocess.run(
                ["which", "sshpass"],
                capture_output=True,
                timeout=5
            )
            if sshpass_check.returncode != 0:
                return False, "sshpass not installed. Install with: opkg install sshpass"
            
            # SECURITY FIX: Use environment variable instead of command line
            env = os.environ.copy()
            env['SSHPASS'] = password
            
            # Test connection with ssh
            test_cmd = [
                "sshpass", "-e",  # Read password from SSHPASS env var
                "ssh", "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=5",
                "-o", "StrictHostKeyChecking=no",
                "-o", "PasswordAuthentication=yes",
                "-p", str(port),
                f"{username}@{host}",
                "echo test"
            ]
            
            result = subprocess.run(
                test_cmd,
                capture_output=True,
                timeout=10,
                text=True,
                env=env
            )
            
            if result.returncode == 0 and "test" in result.stdout:
                return True, "SSH/SFTP connection successful"
            else:
                error = result.stderr[:100] if result.stderr else result.stdout[:100]
                return False, f"SSH error: {error}"
                
        except subprocess.TimeoutExpired:
            return False, "SSH connection timed out"
        except Exception as e:
            return False, f"SSH error: {str(e)}"
    
    def execute_command(self, host, port, username, password, command):
        """Execute remote command via SSH"""
        try:
            validate_hostname(host)
            validate_port(port)
            
            # SECURITY FIX: Properly escape command
            safe_command = shlex.quote(command)
            
            # Use environment variable for password
            env = os.environ.copy()
            env['SSHPASS'] = password
            
            sshpass_cmd = [
                "sshpass", "-e",
                "ssh", "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=5",
                "-o", "StrictHostKeyChecking=no",
                "-p", str(port),
                f"{username}@{host}",
                safe_command
            ]
            
            result = subprocess.run(
                sshpass_cmd,
                capture_output=True,
                timeout=15,
                text=True,
                env=env
            )
            
            return result.returncode == 0, result.stdout, result.stderr
            
        except subprocess.TimeoutExpired:
            return False, "", "Command timed out"
        except Exception as e:
            return False, "", str(e)
    
    def list_directory(self, host, port, username, password, path="/"):
        """List directory contents via SFTP/SSH"""
        try:
            # SECURITY FIX: Properly quote path
            safe_path = shlex.quote(path)
            
            # Use ls command to list directory
            command = f"ls -la {safe_path}"
            success, stdout, stderr = self.execute_command(host, port, username, password, command)
            
            if not success:
                return False, f"Failed to list directory: {stderr}"
            
            # Parse ls output
            lines = stdout.strip().split('\n')
            entries = []
            
            for line in lines[1:]:  # Skip total line
                if not line.strip():
                    continue
                
                parts = line.split()
                if len(parts) >= 8:
                    permissions = parts[0]
                    size = parts[4]
                    month = parts[5]
                    day = parts[6]
                    time_or_year = parts[7]
                    name = ' '.join(parts[8:])
                    
                    # Handle symlink
                    if "->" in name:
                        name, target = name.split("->")
                        name = name.strip()
                        target = target.strip()
                    else:
                        target = None
                    
                    is_dir = permissions.startswith('d')
                    is_link = permissions.startswith('l')
                    
                    try:
                        size_int = int(size)
                    except ValueError:
                        size_int = 0
                    
                    entries.append({
                        'name': name,
                        'path': os.path.join(path, name) if path != '/' else '/' + name,
                        'is_dir': is_dir,
                        'is_link': is_link,
                        'target': target,
                        'size': size_int,
                        'permissions': permissions,
                        'full_line': line
                    })
            
            return True, entries
            
        except Exception as e:
            return False, f"List directory failed: {e}"
    
    def download_file(self, host, port, username, password, remote_path, local_path):
        """Download file via scp"""
        try:
            validate_hostname(host)
            validate_port(port)
            
            # SECURITY FIX: Properly quote paths
            safe_remote = shlex.quote(remote_path)
            safe_local = shlex.quote(local_path)
            
            # Create local directory if it doesn't exist
            local_dir = os.path.dirname(local_path)
            if local_dir and not os.path.exists(local_dir):
                os.makedirs(local_dir, exist_ok=True)
            
            # Use environment variable for password
            env = os.environ.copy()
            env['SSHPASS'] = password
            
            # Download with scp
            scp_cmd = [
                "sshpass", "-e",
                "scp", "-o", "StrictHostKeyChecking=no",
                "-P", str(port),
                f"{username}@{host}:{safe_remote}",
                safe_local
            ]
            
            result = subprocess.run(
                scp_cmd,
                capture_output=True,
                timeout=30,
                text=True,
                env=env
            )
            
            if result.returncode == 0:
                return True, f"Downloaded: {remote_path}"
            else:
                return False, f"Download failed: {result.stderr[:100]}"
                
        except subprocess.TimeoutExpired:
            return False, "Download timed out"
        except Exception as e:
            return False, f"Download error: {e}"
    
    def upload_file(self, host, port, username, password, local_path, remote_path):
        """Upload file via scp"""
        try:
            validate_hostname(host)
            validate_port(port)
            
            # SECURITY FIX: Properly quote paths
            safe_remote = shlex.quote(remote_path)
            safe_local = shlex.quote(local_path)
            
            if not os.path.exists(local_path):
                return False, f"Local file not found: {local_path}"
            
            # Use environment variable for password
            env = os.environ.copy()
            env['SSHPASS'] = password
            
            # Upload with scp
            scp_cmd = [
                "sshpass", "-e",
                "scp", "-o", "StrictHostKeyChecking=no",
                "-P", str(port),
                safe_local,
                f"{username}@{host}:{safe_remote}"
            ]
            
            result = subprocess.run(
                scp_cmd,
                capture_output=True,
                timeout=30,
                text=True,
                env=env
            )
            
            if result.returncode == 0:
                return True, f"Uploaded: {remote_path}"
            else:
                return False, f"Upload failed: {result.stderr[:100]}"
                
        except subprocess.TimeoutExpired:
            return False, "Upload timed out"
        except Exception as e:
            return False, f"Upload error: {e}"
    
    def create_directory(self, host, port, username, password, path):
        """Create directory on remote server"""
        try:
            safe_path = shlex.quote(path)
            command = f"mkdir -p {safe_path}"
            success, stdout, stderr = self.execute_command(host, port, username, password, command)
            
            if success:
                return True, f"Created directory: {path}"
            else:
                return False, f"Create directory failed: {stderr}"
                
        except Exception as e:
            return False, f"Create directory error: {e}"
    
    def delete_file(self, host, port, username, password, path):
        """Delete file on remote server"""
        try:
            safe_path = shlex.quote(path)
            command = f"rm -f {safe_path}"
            success, stdout, stderr = self.execute_command(host, port, username, password, command)
            
            if success:
                return True, f"Deleted: {path}"
            else:
                return False, f"Delete failed: {stderr}"
                
        except Exception as e:
            return False, f"Delete error: {e}"
    
    def delete_directory(self, host, port, username, password, path):
        """Delete directory on remote server"""
        try:
            safe_path = shlex.quote(path)
            command = f"rm -rf {safe_path}"
            success, stdout, stderr = self.execute_command(host, port, username, password, command)
            
            if success:
                return True, f"Deleted directory: {path}"
            else:
                return False, f"Delete directory failed: {stderr}"
                
        except Exception as e:
            return False, f"Delete directory error: {e}"
    
    def get_file_info(self, host, port, username, password, path):
        """Get file information"""
        try:
            safe_path = shlex.quote(path)
            command = f"stat --format='%s %Y %X %F' {safe_path}"
            success, stdout, stderr = self.execute_command(host, port, username, password, command)
            
            if not success:
                return False, f"Get file info failed: {stderr}"
            
            parts = stdout.strip().split()
            if len(parts) >= 4:
                size = int(parts[0])
                modified = int(parts[1])
                accessed = int(parts[2])
                file_type = parts[3]
                
                is_dir = "directory" in file_type
                is_file = "regular" in file_type or "file" in file_type
                
                return True, {
                    'path': path,
                    'size': size,
                    'modified': modified,
                    'accessed': accessed,
                    'is_dir': is_dir,
                    'is_file': is_file,
                    'type': file_type
                }
            
            return False, "Failed to parse file info"
            
        except Exception as e:
            return False, f"Get file info error: {e}"
