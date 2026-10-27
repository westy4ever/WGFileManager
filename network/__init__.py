# In network/__init__.py, add:
from .network_tools import NetworkToolsScreen

__all__ = [
    'RemoteConnectionManager', 
    'FTPClient', 
    'SFTPClient', 
    'WebDAVClient', 
    'MountManager', 
    'NetworkBrowser',
    'NetworkToolsScreen'  # Add this
]