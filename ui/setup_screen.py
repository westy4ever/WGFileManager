import os
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.ConfigList import ConfigList, ConfigListScreen
from Components.config import config, getConfigListEntry, ConfigNothing, configfile
from enigma import getDesktop

# Corrected: We only need the logger here now 
# because we use the global 'config' object directly in __init__
from ..utils.logging_config import get_logger

logger = get_logger(__name__)

class WGFileManagerSetup(ConfigListScreen, Screen):
    def __init__(self, session, plugin_config=None):
        """Fixed initialization for WGFileManagerSetup"""
        Screen.__init__(self, session)
        self.session = session

        # 1. Initialize config
        from ..core.config import WGFileManagerConfig
        self.config_manager = WGFileManagerConfig()
        self.config_manager.setup_config()

        # 2. Create widgets FIRST (critical for ConfigListScreen)
        self.list = []
        self["config"] = ConfigList(self.list)
        
        # 3. Create labels
        self["key_red"] = Label("Cancel")
        self["key_yellow"] = Label("Defaults")
        self["key_green"] = Label("Save")
        
        # 4. Build config list
        self.init_config_list()
        
        # 5. Initialize ConfigListScreen (AFTER widgets exist)
        ConfigListScreen.__init__(self, self.list, session=session)

        # 6. Setup actions
        self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
            "red": self.key_cancel,
            "yellow": self.load_defaults,
            "green": self.key_save,
            "cancel": self.key_cancel,
            "left": self.keyLeft,
            "right": self.keyRight,
            "ok": self.keyOK
        }, -2)
        
        # 7. Create skin
        desktop_w, desktop_h = getDesktop(0).size().width(), getDesktop(0).size().height()
        panel_w = desktop_w
        panel_h = desktop_h
        config_h = panel_h - 180
        button_y = panel_h - 70
        
        self.skin = f"""
        <screen name="WGFileManagerSetup" position="0,0" size="{panel_w},{panel_h}" title=" WGFileManager Configuration" backgroundColor="#0d1117" flags="wfNoBorder">
            <eLabel position="0,0" size="{panel_w},80" backgroundColor="#161b22" />
            <eLabel position="0,68" size="{panel_w},2" backgroundColor="#1976d2" />
            
            <eLabel text=" File Manager Configuration" position="0,15" size="{panel_w},50" font="Regular;42" halign="center" valign="center" transparent="1" foregroundColor="#58a6ff" shadowColor="#000000" shadowOffset="-2,-2" />
            
            <widget name="config" position="100,100" size="{panel_w-200},{panel_h-220}" itemHeight="70" scrollbarMode="showOnDemand" backgroundColor="#0d1117" foregroundColor="#c9d1d9" selectionBackground="#1976d2" />
            
            <eLabel position="0,{button_y-10}" size="{panel_w},2" backgroundColor="#30363d" />
            <eLabel position="0,{button_y-8}" size="{panel_w},80" backgroundColor="#010409" />
            
            <eLabel position="100,{button_y}" size="220,60" backgroundColor="#7d1818" />
            <eLabel position="400,{button_y}" size="220,60" backgroundColor="#9e6a03" />
            <eLabel position="700,{button_y}" size="220,60" backgroundColor="#1e5128" />

            <widget name="key_red" position="110,{button_y+5}" size="200,50" zPosition="1" font="Regular;26" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
            <widget name="key_yellow" position="410,{button_y+5}" size="200,50" zPosition="1" font="Regular;26" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
            <widget name="key_green" position="710,{button_y+5}" size="200,50" zPosition="1" font="Regular;26" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
        </screen>"""

    def init_config_list(self):
        """Initialize configuration list - FIXED version"""
        self.list = []

        # --- STEP 1: FORCE THE SYSTEM TO RECOGNIZE YOUR PLUGIN ---
        from Components.config import config, ConfigSubsection
        # --- STEP 2: RUN YOUR REGISTRATION ---
        from ..core.config import WGFileManagerConfig
        self.config_manager = WGFileManagerConfig()
        self.config_manager.setup_config()

        # --- STEP 3: ASSIGN 'p' AFTER REGISTRATION IS DONE ---
        p = config.plugins.wgfilemanager
        
        # --- STEP 4: BUILD THE LIST ---
        try:
            self.list.append(getConfigListEntry("══════ General Settings ══════", ConfigNothing()))
            self.list.append(getConfigListEntry("Default Left Path:", p.left_path))
            self.list.append(getConfigListEntry("Default Right Path:", p.right_path))
            self.list.append(getConfigListEntry("Starting Pane:", p.starting_pane))
            self.list.append(getConfigListEntry("Show Directories First:", p.show_dirs_first))
            self.list.append(getConfigListEntry("Left Pane Sort Mode:", p.left_sort_mode))
            self.list.append(getConfigListEntry("Right Pane Sort Mode:", p.right_sort_mode))
            
            # Context Menu
            self.list.append(getConfigListEntry("══════ Context Menu Settings ══════", ConfigNothing()))
            self.list.append(getConfigListEntry("Enable Smart Context Menus:", p.enable_smart_context))
            self.list.append(getConfigListEntry("OK Long Press Time (ms):", p.ok_long_press_time))
            self.list.append(getConfigListEntry("Group Tools Menu:", p.group_tools_menu))
            
            # File Operations
            self.list.append(getConfigListEntry("══════ File Operations ══════", ConfigNothing()))
            self.list.append(getConfigListEntry("Enable Trash:", p.trash_enabled))
            self.list.append(getConfigListEntry("Enable Cache:", p.cache_enabled))
            self.list.append(getConfigListEntry("Preview Size Limit:", p.preview_size))
            
            # Exit Behavior
            self.list.append(getConfigListEntry("══════ Exit Behavior ══════", ConfigNothing()))
            self.list.append(getConfigListEntry("Save Left Path on Exit:", p.save_left_on_exit))
            self.list.append(getConfigListEntry("Save Right Path on Exit:", p.save_right_on_exit))
            
            # Media Player
            self.list.append(getConfigListEntry("══════ Media Player ══════", ConfigNothing()))
            self.list.append(getConfigListEntry("Use Internal Player:", p.use_internal_player))
            self.list.append(getConfigListEntry("Fallback to External:", p.fallback_to_external))
            
            # Remote & Network
            self.list.append(getConfigListEntry("══════ Remote Access ══════", ConfigNothing()))
            self.list.append(getConfigListEntry("Remote IP for Mount:", p.remote_ip))
            
            # FTP Settings
            self.list.append(getConfigListEntry("--- FTP Settings ---", ConfigNothing()))
            self.list.append(getConfigListEntry("FTP Host:", p.ftp_host))
            self.list.append(getConfigListEntry("FTP Port:", p.ftp_port))
            self.list.append(getConfigListEntry("FTP User:", p.ftp_user))
            self.list.append(getConfigListEntry("FTP Password:", p.ftp_pass))
            
            # SFTP Settings
            self.list.append(getConfigListEntry("--- SFTP Settings ---", ConfigNothing()))
            self.list.append(getConfigListEntry("SFTP Host:", p.sftp_host))
            self.list.append(getConfigListEntry("SFTP Port:", p.sftp_port))
            self.list.append(getConfigListEntry("SFTP User:", p.sftp_user))
            self.list.append(getConfigListEntry("SFTP Password:", p.sftp_pass))
            
            # WebDAV Settings
            self.list.append(getConfigListEntry("--- WebDAV Settings ---", ConfigNothing()))
            self.list.append(getConfigListEntry("WebDAV URL:", p.webdav_url))
            self.list.append(getConfigListEntry("WebDAV User:", p.webdav_user))
            self.list.append(getConfigListEntry("WebDAV Password:", p.webdav_pass))

        except AttributeError as e:
            print("[WGFileManager] ERROR: Missing config variable -> %s" % str(e))
        
        # --- 4. UPDATE UI ---
        # Note: We use the safer check and correct list setter for Enigma2
        if "config" in self:
            self["config"].list = self.list
            self["config"].setList(self.list)

    def changedEntry(self):
        """Standard handler for ConfigListScreen to refresh logic on change"""
        for x in self.onChangedEntry:
            x()

    def key_save(self):
        """Save configuration changes and close screen"""
        try:
            # 1. Use the built-in ConfigListScreen saver to process all entries
            from Components.ConfigList import ConfigListScreen
            ConfigListScreen.saveAll(self)
            
            # 2. Write the changes to the physical settings file (/etc/enigma2/settings)
            from Components.config import configfile
            configfile.save()
            
            # 3. Close the screen and return to the previous menu
            self.close()
            
        except Exception as e:
            # 4. Comprehensive error handling with logging
            logger.error(f"Error saving WGFileManager settings: {e}")
            from Screens.MessageBox import MessageBox
            self.session.open(MessageBox, f"Error saving settings: {e}", MessageBox.TYPE_ERROR)

    def key_cancel(self):
        # Simple fix: just close without confirmation
        self.close(False)  # False = don't save changes

    def load_defaults(self):
        """Use the reset logic from config.py"""
        self.session.openWithCallback(self.confirm_defaults, MessageBox, "Reset all settings to defaults?", MessageBox.TYPE_YESNO)

    def confirm_defaults(self, result):
        if result:
            # Use your professional reset method from config.py
            if self.config_manager.reset_to_defaults():
                self.init_config_list()
            else:
                logger.error("Failed to reset defaults")

    def keyLeft(self):
        ConfigListScreen.keyLeft(self)

    def keyRight(self):
        ConfigListScreen.keyRight(self)

    def keyOK(self):
        pass

    # Change this in setup_screen.py
def update_help_text(self):
    try:
        # Ensure we are accessing the widget, not the global config module
        current = self["config"].getCurrent() 
        if current and len(current) > 2:
            # If you have help text in your config entries
            self["help_label"].setText(current[2])
    except Exception as e:
        logger.debug(f"Error updating help text: {e}")