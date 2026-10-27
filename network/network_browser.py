"""
Network Browser - Enables browsing remote filesystems in dual-pane view
"""
import os
from Components.config import config 
from ..exceptions import RemoteConnectionError

class NetworkBrowser:
    """Browse network locations as if they were local"""
    
    def __init__(self, config):
        self.config = config
        self.active_connections = {}
        self.mount_points = {}
    
    def is_network_path(self, path):
        """Check if path is a network location"""
        return path.startswith('ftp://') or path.startswith('sftp://') or path.startswith('webdav://')
    
    def parse_network_path(self, path):
        """Parse network path into components"""
        if path.startswith('ftp://'):
            protocol = 'ftp'
            path = path[6:]
        elif path.startswith('sftp://'):
            protocol = 'sftp'
            path = path[7:]
        elif path.startswith('webdav://'):
            protocol = 'webdav'
            path = path[9:]
        else:
            return None
        
        # Parse user@host:port/path
        parts = path.split('/', 1)
        host_part = parts[0]
        remote_path = '/' + parts[1] if len(parts) > 1 else '/'
        
        # Parse user@host:port
        if '@' in host_part:
            user_host = host_part.split('@')
            username = user_host[0]
            host_port = user_host[1]
        else:
            username = None
            host_port = host_part
        
        if ':' in host_port:
            host, port = host_port.split(':')
            port = int(port)
        else:
            host = host_port
            port = 21 if protocol == 'ftp' else (22 if protocol == 'sftp' else 80)
        
        return {
            'protocol': protocol,
            'host': host,
            'port': port,
            'username': username,
            'path': remote_path
        }
    
    def list_directory(self, network_path, ftp_client, sftp_client, webdav_client):
        """List directory on network location"""
        parsed = self.parse_network_path(network_path)
        if not parsed:
            raise RemoteConnectionError("Invalid network path: " + network_path)
        
        protocol = parsed['protocol']
        host = parsed['host']
        port = parsed['port']
        path = parsed['path']
        username = parsed.get('username', 'anonymous')
        
        # Get password from config if available
        if protocol == 'ftp':
            password = config.plugins.wgfilemanager.ftp_pass.value
            client = ftp_client
            
            # Connect if not connected
            if not client.is_connected():
                client.connect(host, port, username, password)
            
            # List directory
            entries = client.list_directory(path)
            
            # Convert to standard format
            result = []
            for entry in entries:
                result.append({
                    'name': entry['name'],
                    'path': network_path.rstrip('/') + '/' + entry['name'],
                    'is_dir': entry['is_dir'],
                    'size': entry['size'],
                    'date': entry.get('date'),
                })
            return result
            
        elif protocol == 'sftp':
            password = config.plugins.wgfilemanager.sftp_pass.value
            success, entries = sftp_client.list_directory(host, port, username, password, path)
            
            if not success:
                raise RemoteConnectionError("SFTP list failed: " + str(entries))
            
            result = []
            for entry in entries:
                result.append({
                    'name': entry['name'],
                    'path': network_path.rstrip('/') + '/' + entry['name'],
                    'is_dir': entry['is_dir'],
                    'size': entry['size'],
                })
            return result
            
        elif protocol == 'webdav':
            password = config.plugins.wgfilemanager.webdav_pass.value
            username = config.plugins.wgfilemanager.webdav_user.value
            url = config.plugins.wgfilemanager.webdav_url.value + path
            
            success, entries = webdav_client.list_directory(url, username, password)
            
            if not success:
                raise RemoteConnectionError("WebDAV list failed: " + str(entries))
            
            result = []
            for entry in entries:
                result.append({
                    'name': entry['name'],
                    'path': network_path.rstrip('/') + '/' + entry['name'],
                    'is_dir': entry['is_dir'],
                    'size': entry.get('size', 0),
                })
            return result
        
        else:
            raise RemoteConnectionError("Unsupported protocol: " + protocol)
    
    def download_file(self, network_path, local_path, ftp_client, sftp_client, webdav_client):
        """Download file from network location"""
        parsed = self.parse_network_path(network_path)
        if not parsed:
            raise RemoteConnectionError("Invalid network path")
        
        protocol = parsed['protocol']
        host = parsed['host']
        port = parsed['port']
        path = parsed['path']
        username = parsed.get('username', 'anonymous')
        
        if protocol == 'ftp':
            password = config.plugins.wgfilemanager.ftp_pass.value
            if not ftp_client.is_connected():
                ftp_client.connect(host, port, username, password)
            success, msg = ftp_client.download_file(path, local_path)
            return success, msg
            
        elif protocol == 'sftp':
            password = config.plugins.wgfilemanager.sftp_pass.value
            return sftp_client.download_file(host, port, username, password, path, local_path)
            
        elif protocol == 'webdav':
            password = config.plugins.wgfilemanager.webdav_pass.value
            username = config.plugins.wgfilemanager.webdav_user.value
            url = config.plugins.wgfilemanager.webdav_url.value + path
            return webdav_client.download_file(url, local_path, username, password)
        
        else:
            raise RemoteConnectionError("Unsupported protocol")
