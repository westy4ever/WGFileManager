import json
import os
from datetime import datetime
from ..constants import REMOTE_CONNECTIONS_FILE
from ..exceptions import RemoteConnectionError

class RemoteConnectionManager:
    def __init__(self, config):
        self.config = config
        self.connections_file = REMOTE_CONNECTIONS_FILE
        self.connections = self.load_connections()
        self.active_connections = {}
    
    def load_connections(self):
        """Load saved remote connections"""
        try:
            if os.path.exists(self.connections_file):
                with open(self.connections_file, 'r') as f:
                    connections = json.load(f)
                    # Validate connections structure
                    valid_connections = {}
                    for name, conn in connections.items():
                        if self._validate_connection(conn):
                            valid_connections[name] = conn
                    return valid_connections
        except Exception:
            pass
        return {}
    
    def save_connections(self):
        """Save remote connections"""
        try:
            with open(self.connections_file, 'w') as f:
                json.dump(self.connections, f, indent=2)
            return True
        except Exception as e:
            raise RemoteConnectionError(f"Failed to save connections: {e}")
    
    def add_connection(self, name, connection_type, host, port, username, password, path="/", options=None):
        """Add a new remote connection"""
        try:
            connection = {
                'type': connection_type,
                'host': host,
                'port': port,
                'username': username,
                'password': password,
                'path': path,
                'options': options or {},
                'last_used': datetime.now().isoformat(),
                'created': datetime.now().isoformat()
            }
            
            if not self._validate_connection(connection):
                raise RemoteConnectionError("Invalid connection parameters")
            
            self.connections[name] = connection
            self.save_connections()
            return True
            
        except Exception as e:
            raise RemoteConnectionError(f"Failed to add connection: {e}")
    
    def update_connection(self, name, **kwargs):
        """Update existing connection"""
        try:
            if name not in self.connections:
                raise RemoteConnectionError(f"Connection not found: {name}")
            
            connection = self.connections[name]
            connection.update(kwargs)
            connection['last_used'] = datetime.now().isoformat()
            
            if not self._validate_connection(connection):
                raise RemoteConnectionError("Invalid connection parameters after update")
            
            self.connections[name] = connection
            self.save_connections()
            return True
            
        except Exception as e:
            raise RemoteConnectionError(f"Failed to update connection: {e}")
    
    def remove_connection(self, name):
        """Remove a remote connection"""
        try:
            if name in self.connections:
                del self.connections[name]
                self.save_connections()
                return True
            return False
        except Exception as e:
            raise RemoteConnectionError(f"Failed to remove connection: {e}")
    
    def get_connection(self, name):
        """Get connection by name"""
        return self.connections.get(name)
    
    def list_connections(self, connection_type=None):
        """List all connections, optionally filtered by type"""
        if connection_type:
            return {k: v for k, v in self.connections.items() if v.get('type') == connection_type}
        return self.connections.copy()
    
    def test_connection(self, name):
        """Test a saved connection"""
        try:
            connection = self.get_connection(name)
            if not connection:
                raise RemoteConnectionError(f"Connection not found: {name}")
            
            # Import here to avoid circular imports
            from .ftp_client import FTPClient
            from .sftp_client import SFTPClient
            
            conn_type = connection['type']
            
            if conn_type == 'ftp':
                client = FTPClient(self.config)
                success, message = client.test_connection(
                    connection['host'],
                    connection['port'],
                    connection['username'],
                    connection['password']
                )
            elif conn_type == 'sftp':
                client = SFTPClient(self.config)
                success, message = client.test_connection(
                    connection['host'],
                    connection['port'],
                    connection['username'],
                    connection['password']
                )
            else:
                success, message = False, f"Unsupported connection type: {conn_type}"
            
            if success:
                # Update last used time
                self.update_connection(name)
            
            return success, message
            
        except Exception as e:
            raise RemoteConnectionError(f"Test connection failed: {e}")
    
    def _validate_connection(self, connection):
        """Validate connection parameters"""
        required_fields = ['type', 'host', 'port', 'username']
        
        for field in required_fields:
            if field not in connection:
                return False
        
        # Validate type
        if connection['type'] not in ['ftp', 'sftp', 'webdav', 'cifs']:
            return False
        
        # Validate host
        if not connection['host'] or len(connection['host']) > 255:
            return False
        
        # Validate port
        try:
            port = int(connection['port'])
            if port < 1 or port > 65535:
                return False
        except (ValueError, TypeError):
            return False
        
        return True
    
    def clear_connections(self):
        """Clear all connections"""
        try:
            self.connections = {}
            self.save_connections()
            return True
        except Exception as e:
            raise RemoteConnectionError(f"Failed to clear connections: {e}")