from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Label import Label
from enigma import getDesktop
import os
import threading

from ..utils.logging_config import get_logger

logger = get_logger(__name__)

class RemoteBrowser(Screen):
    """Remote file browser with dual-pane support for FTP/SFTP/WebDAV"""
    
    def __init__(self, session, remote_mgr, ftp_client, sftp_client, webdav_client, local_pane=None):
        Screen.__init__(self, session)
        
        # Get screen dimensions
        w, h = getDesktop(0).size().width(), getDesktop(0).size().height()
        
        # Initialize components
        self.remote_mgr = remote_mgr
        self.ftp_client = ftp_client
        self.sftp_client = sftp_client
        self.webdav_client = webdav_client
        self.local_pane = local_pane
        
        # State
        self.current_connection = None
        self.current_path = "/"
        self.file_list = []
        self.loading = False
        
        # Create skin
        self.skin = f"""
        <screen name="RemoteBrowser" position="0,0" size="{w},{h}" backgroundColor="#0d1117" flags="wfNoBorder">
            <eLabel position="0,0" size="{w},80" backgroundColor="#161b22" />
            <eLabel position="0,68" size="{w},2" backgroundColor="#1976d2" />
            
            <eLabel text=" Remote File Browser" position="0,15" size="{w},50" font="Regular;42" halign="center" valign="center" transparent="1" foregroundColor="#58a6ff" shadowColor="#000000" shadowOffset="-2,-2" />
            
            <widget name="connection_info" position="20,100" size="{w-40},40" font="Regular;24" foregroundColor="#00ff00" transparent="1" />
            <widget name="current_path" position="20,150" size="{w-40},35" font="Regular;20" foregroundColor="#ffaa00" transparent="1" />
            
            <widget name="file_list" position="20,200" size="{w-40},{h-350}" scrollbarMode="showOnDemand" itemHeight="45" />
            
            <widget name="status_bar" position="20,{h-140}" size="{w-40},35" font="Regular;22" foregroundColor="#ffffff" transparent="1" />
            
            <eLabel position="0,{h-90}" size="{w},2" backgroundColor="#30363d" />
            <eLabel position="0,{h-88}" size="{w},90" backgroundColor="#010409" />
            
            <eLabel position="100,{h-70}" size="200,50" backgroundColor="#7d1818" />
            <eLabel position="350,{h-70}" size="200,50" backgroundColor="#1e5128" />
            <eLabel position="600,{h-70}" size="200,50" backgroundColor="#1976d2" />
            
            <eLabel text="Exit" position="110,{h-65}" size="180,40" zPosition="1" font="Regular;26" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
            <eLabel text="Download" position="360,{h-65}" size="180,40" zPosition="1" font="Regular;26" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
            <eLabel text="Refresh" position="610,{h-65}" size="180,40" zPosition="1" font="Regular;26" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
        </screen>"""
        
        # Create widgets
        self["connection_info"] = Label("")
        self["current_path"] = Label("")
        self["file_list"] = MenuList([])
        self["status_bar"] = Label("Select a connection to browse")
        
        # Setup actions
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
            "ok": self.navigate_or_action,
            "cancel": self.exit_browser,
            "red": self.exit_browser,
            "green": self.download_selected,
            "blue": self.refresh_list,
            "up": self.up,
            "down": self.down,
        }, -1)
        
        # Show connection selector on startup
        self.onLayoutFinish.append(self.show_connection_selector)
    
    def show_connection_selector(self):
        """Show available connections - FIXED"""
        try:
            connections = self.remote_mgr.list_connections()
        
            if not connections:
                # FIXED: Don't use openWithCallback in __init__ context
                self["status_bar"].setText("No saved connections! Configure in Settings.")
            
                # Close after a delay
                import threading
                def delayed_close():
                    import time
                    time.sleep(3)
                    self.close()
            
                threading.Thread(target=delayed_close, daemon=True).start()
                return
        
            # Build connection list
            conn_list = []
            for name, conn in connections.items():
                conn_type = conn.get('type', 'unknown').upper()
                host = conn.get('host', 'unknown')
                conn_list.append((f"{conn_type}: {name} ({host})", name))
        
            if conn_list:
                # FIXED: Use ChoiceBox instead of MessageBox
                from Screens.ChoiceBox import ChoiceBox
            
                def select_connection(choice):
                    if choice:
                        self.connection_selected(choice[1])
                    else:
                        self.close()
            
                self.session.openWithCallback(
                    select_connection,
                    ChoiceBox,
                    title="Select Remote Connection",
                    list=conn_list
                )
            
            # For now, auto-select first connection for demo
            if conn_list:
                self.connection_selected(conn_list[0][1])
            
        except Exception as e:
            logger.error(f"Error showing connection selector: {e}")
            self.session.open(MessageBox, f"Error loading connections:\n{e}", MessageBox.TYPE_ERROR)
    
    def connection_selected(self, connection_name):
        """Handle connection selection"""
        try:
            if not connection_name:
                self.close()
                return
            
            self.current_connection = self.remote_mgr.get_connection(connection_name)
            
            if not self.current_connection:
                self.session.open(MessageBox, "Connection not found!", MessageBox.TYPE_ERROR)
                self.close()
                return
            
            # Update connection info
            conn_type = self.current_connection.get('type', 'unknown').upper()
            host = self.current_connection.get('host', 'unknown')
            self["connection_info"].setText(f"Connected: {conn_type} - {host}")
            
            # Connect and browse
            self.connect_and_browse()
            
        except Exception as e:
            logger.error(f"Error selecting connection: {e}")
            self.session.open(MessageBox, f"Connection error:\n{e}", MessageBox.TYPE_ERROR)
    
    def connect_and_browse(self):
        """Connect to remote server and browse"""
        def connect_thread():
            try:
                self["status_bar"].setText("Connecting...")
                self.loading = True
                
                conn_type = self.current_connection.get('type')
                host = self.current_connection.get('host')
                port = self.current_connection.get('port')
                username = self.current_connection.get('username')
                password = self.current_connection.get('password')
                
                if conn_type == 'ftp':
                    success, message = self.ftp_client.connect(host, port, username, password)
                    if success:
                        self.browse_directory(self.current_path)
                    else:
                        self.show_error(f"FTP connection failed:\n{message}")
                
                elif conn_type == 'sftp':
                    success, result = self.sftp_client.list_directory(host, port, username, password, self.current_path)
                    if success:
                        self.update_file_list(result)
                    else:
                        self.show_error(f"SFTP connection failed:\n{result}")
                
                else:
                    self.show_error(f"Unsupported connection type: {conn_type}")
                
                self.loading = False
                
            except Exception as e:
                logger.error(f"Connection thread error: {e}")
                self.show_error(f"Connection error:\n{e}")
                self.loading = False
        
        threading.Thread(target=connect_thread, daemon=True).start()
    
    def browse_directory(self, path):
        """Browse directory on remote server"""
        try:
            conn_type = self.current_connection.get('type')
            
            if conn_type == 'ftp':
                entries = self.ftp_client.list_directory(path)
                self.update_file_list(entries)
            
            self.current_path = path
            self["current_path"].setText(f"Path: {path}")
            
        except Exception as e:
            logger.error(f"Browse error: {e}")
            self.show_error(f"Browse failed:\n{e}")
    
    def update_file_list(self, entries):
        """Update file list display"""
        try:
            # Add parent directory entry if not at root
            display_list = []
            
            if self.current_path != "/":
                display_list.append((" ..", ".."))
            
            # Add entries
            for entry in entries:
                name = entry.get('name', 'unknown')
                is_dir = entry.get('is_dir', False)
                size = entry.get('size', 0)
                
                icon = "" if is_dir else ""
                
                if is_dir:
                    display = f"{icon} {name}/"
                else:
                    from ..utils.formatters import format_size
                    display = f"{icon} {name} ({format_size(size)})"
                
                display_list.append((display, entry))
            
            self.file_list = entries
            self["file_list"].setList(display_list)
            self["status_bar"].setText(f"Files: {len(entries)}")
            
        except Exception as e:
            logger.error(f"Update file list error: {e}")
    
    def navigate_or_action(self):
        """Handle OK button - navigate into directories or download files"""
        try:
            current = self["file_list"].getCurrent()
            if not current:
                return
            
            item = current[1]
            
            # Handle parent directory
            if item == "..":
                parent = os.path.dirname(self.current_path)
                self.browse_directory(parent)
                return
            
            # Handle directory navigation
            if isinstance(item, dict) and item.get('is_dir'):
                new_path = item.get('path', self.current_path + '/' + item.get('name'))
                self.browse_directory(new_path)
            else:
                # File selected - download it
                self.download_selected()
            
        except Exception as e:
            logger.error(f"Navigate error: {e}")
            self.show_error(f"Navigation failed:\n{e}")
    
    def download_selected(self):
        """Download selected file"""
        try:
            current = self["file_list"].getCurrent()
            if not current:
                return
            
            item = current[1]
            
            if not isinstance(item, dict) or item.get('is_dir'):
                self.session.open(MessageBox, "Please select a file to download", MessageBox.TYPE_INFO, timeout=2)
                return
            
            # Get local destination
            if self.local_pane:
                local_dir = self.local_pane.getCurrentDirectory()
            else:
                local_dir = "/tmp"
            
            remote_path = item.get('path')
            filename = item.get('name')
            local_path = os.path.join(local_dir, filename)
            
            # Confirm download
            self.session.openWithCallback(
                lambda res: self.execute_download(res, remote_path, local_path, filename),
                MessageBox,
                f"Download file?\n\n{filename}\n\nTo: {local_dir}",
                MessageBox.TYPE_YESNO
            )
            
        except Exception as e:
            logger.error(f"Download selected error: {e}")
            self.show_error(f"Download failed:\n{e}")
    
    def execute_download(self, confirmed, remote_path, local_path, filename):
        """Execute file download"""
        if not confirmed:
            return
        
        def download_thread():
            try:
                self["status_bar"].setText(f"Downloading {filename}...")
                
                conn_type = self.current_connection.get('type')
                
                if conn_type == 'ftp':
                    success, message = self.ftp_client.download_file(remote_path, local_path)
                elif conn_type == 'sftp':
                    host = self.current_connection.get('host')
                    port = self.current_connection.get('port')
                    username = self.current_connection.get('username')
                    password = self.current_connection.get('password')
                    success, message = self.sftp_client.download_file(host, port, username, password, remote_path, local_path)
                else:
                    success = False
                    message = "Unsupported protocol"
                
                if success:
                    self["status_bar"].setText(f"[OK] Downloaded: {filename}")
                    self.session.open(MessageBox, f"Download complete!\n\n{filename}", MessageBox.TYPE_INFO, timeout=3)
                else:
                    self.show_error(f"Download failed:\n{message}")
                
            except Exception as e:
                logger.error(f"Download thread error: {e}")
                self.show_error(f"Download error:\n{e}")
        
        threading.Thread(target=download_thread, daemon=True).start()
    
    def refresh_list(self):
        """Refresh current directory"""
        try:
            self.browse_directory(self.current_path)
        except Exception as e:
            logger.error(f"Refresh error: {e}")
    
    def up(self):
        """Move up in list"""
        self["file_list"].up()
    
    def down(self):
        """Move down in list"""
        self["file_list"].down()
    
    def show_error(self, message):
        """Show error message"""
        self.session.open(MessageBox, message, MessageBox.TYPE_ERROR)
    
    def exit_browser(self):
        """Exit remote browser"""
        try:
            # Disconnect if connected
            conn_type = self.current_connection.get('type') if self.current_connection else None
            
            if conn_type == 'ftp':
                self.ftp_client.disconnect()
            
            self.close()
        except Exception as e:
            logger.error(f"Exit error: {e}")
            self.close()