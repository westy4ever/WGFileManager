import subprocess
import os
from ..constants import DEFAULT_TIMEOUT
from ..exceptions import RemoteConnectionError, NetworkError
from ..utils.validators import validate_url, sanitize_string

class WebDAVClient:
    def __init__(self, config):
        self.config = config
        self.timeout = DEFAULT_TIMEOUT
    
    def test_connection(self, url, username="", password=""):
        """Test WebDAV connection using curl"""
        try:
            validate_url(url)
            
            # Check if curl is available
            curl_check = subprocess.run(
                ["which", "curl"],
                capture_output=True,
                timeout=5
            )
            if curl_check.returncode != 0:
                return False, "curl not installed. Install with: opkg install curl"
            
            # Build curl command
            curl_cmd = ["curl", "-s", "-I", "-X", "PROPFIND"]
            
            if username:
                curl_cmd.extend(["--user", f"{username}:{password}"])
            
            curl_cmd.extend(["--connect-timeout", "5", url])
            
            result = subprocess.run(
                curl_cmd,
                capture_output=True,
                timeout=10,
                text=True
            )
            
            if result.returncode == 0 and "200" in result.stdout:
                return True, "WebDAV connection successful"
            else:
                error = result.stderr[:100] if result.stderr else result.stdout[:100]
                return False, f"WebDAV error: {error}"
                
        except subprocess.TimeoutExpired:
            return False, "WebDAV connection timed out"
        except Exception as e:
            return False, f"WebDAV error: {str(e)}"
    
    def download_file(self, url, local_path, username="", password=""):
        """Download file from WebDAV"""
        try:
            validate_url(url)
            
            # Create local directory if it doesn't exist
            local_dir = os.path.dirname(local_path)
            if local_dir and not os.path.exists(local_dir):
                os.makedirs(local_dir, exist_ok=True)
            
            # Build curl command
            curl_cmd = ["curl", "-s", "-o", local_path]
            
            if username:
                curl_cmd.extend(["--user", f"{username}:{password}"])
            
            curl_cmd.extend(["--connect-timeout", "10", url])
            
            result = subprocess.run(
                curl_cmd,
                capture_output=True,
                timeout=30,
                text=True
            )
            
            if result.returncode == 0:
                return True, f"Downloaded: {url}"
            else:
                return False, f"Download failed: {result.stderr[:100]}"
                
        except subprocess.TimeoutExpired:
            return False, "Download timed out"
        except Exception as e:
            return False, f"Download error: {e}"
    
    def upload_file(self, local_path, url, username="", password=""):
        """Upload file to WebDAV"""
        try:
            validate_url(url)
            
            if not os.path.exists(local_path):
                return False, f"Local file not found: {local_path}"
            
            # Build curl command
            curl_cmd = ["curl", "-s", "-T", local_path]
            
            if username:
                curl_cmd.extend(["--user", f"{username}:{password}"])
            
            curl_cmd.extend(["--connect-timeout", "10", url])
            
            result = subprocess.run(
                curl_cmd,
                capture_output=True,
                timeout=30,
                text=True
            )
            
            if result.returncode == 0:
                return True, f"Uploaded to: {url}"
            else:
                return False, f"Upload failed: {result.stderr[:100]}"
                
        except subprocess.TimeoutExpired:
            return False, "Upload timed out"
        except Exception as e:
            return False, f"Upload error: {e}"
    
    def list_directory(self, url, username="", password="", depth=1):
        """List WebDAV directory contents"""
        try:
            validate_url(url)
            
            # Build curl command for PROPFIND
            curl_cmd = ["curl", "-s", "-X", "PROPFIND", "--header", f"Depth: {depth}"]
            
            if username:
                curl_cmd.extend(["--user", f"{username}:{password}"])
            
            curl_cmd.extend(["--connect-timeout", "10", url])
            
            result = subprocess.run(
                curl_cmd,
                capture_output=True,
                timeout=15,
                text=True
            )
            
            if result.returncode != 0:
                return False, f"List failed: {result.stderr[:100]}"
            
            # Parse XML response (simplified)
            entries = []
            lines = result.stdout.split('\n')
            
            for line in lines:
                if '<d:href>' in line:
                    # Extract path
                    start = line.find('<d:href>') + 8
                    end = line.find('</d:href>')
                    if start < end:
                        href = line[start:end]
                        # Remove URL base
                        if href.startswith(url):
                            href = href[len(url):]
                        
                        if href and href != '/':
                            # Check if it's a collection (directory)
                            is_dir = False
                            if '</d:collection>' in line or 'collection' in line.lower():
                                is_dir = True
                            
                            name = href.rstrip('/').split('/')[-1]
                            
                            entries.append({
                                'name': name,
                                'path': href,
                                'is_dir': is_dir,
                                'url': url.rstrip('/') + href
                            })
            
            return True, entries
            
        except subprocess.TimeoutExpired:
            return False, "List directory timed out"
        except Exception as e:
            return False, f"List directory error: {e}"
    
    def create_directory(self, url, username="", password=""):
        """Create directory on WebDAV"""
        try:
            validate_url(url)
            
            # Build curl command for MKCOL
            curl_cmd = ["curl", "-s", "-X", "MKCOL"]
            
            if username:
                curl_cmd.extend(["--user", f"{username}:{password}"])
            
            curl_cmd.extend(["--connect-timeout", "10", url])
            
            result = subprocess.run(
                curl_cmd,
                capture_output=True,
                timeout=15,
                text=True
            )
            
            if result.returncode == 0 or "405" in result.stdout:  # 405 = Already exists
                return True, f"Created directory: {url}"
            else:
                return False, f"Create directory failed: {result.stderr[:100]}"
                
        except subprocess.TimeoutExpired:
            return False, "Create directory timed out"
        except Exception as e:
            return False, f"Create directory error: {e}"
    
    def delete(self, url, username="", password=""):
        """Delete file or directory on WebDAV"""
        try:
            validate_url(url)
            
            # Build curl command for DELETE
            curl_cmd = ["curl", "-s", "-X", "DELETE"]
            
            if username:
                curl_cmd.extend(["--user", f"{username}:{password}"])
            
            curl_cmd.extend(["--connect-timeout", "10", url])
            
            result = subprocess.run(
                curl_cmd,
                capture_output=True,
                timeout=15,
                text=True
            )
            
            if result.returncode == 0:
                return True, f"Deleted: {url}"
            else:
                return False, f"Delete failed: {result.stderr[:100]}"
                
        except subprocess.TimeoutExpired:
            return False, "Delete timed out"
        except Exception as e:
            return False, f"Delete error: {e}"