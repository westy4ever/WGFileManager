from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap
from Components.config import config, configfile
from Components.FileList import FileList
from Components.Label import Label
from Components.ProgressBar import ProgressBar
from enigma import getDesktop, eTimer, eLabel, gFont, gRGB, RT_HALIGN_LEFT, RT_VALIGN_CENTER
from enigma import eServiceReference
import threading
import os
import time

from ..core.config import WGFileManagerConfig
from ..core.file_operations import FileOperations
from ..core.archive import ArchiveManager
from ..core.search import SearchEngine
from ..network.remote_manager import RemoteConnectionManager
from ..network.mount import MountManager
from ..utils.formatters import get_file_icon, format_size
from ..utils.logging_config import get_logger
from .context_menu import ContextMenuHandler
from .dialogs import Dialogs

# Import for subtitle support

logger = get_logger(__name__)

class EnhancedFileList(FileList):
    _debug_enabled = False    # round-13: referenced by getCurrentDirectory but never defined
    alwaysshow_parent = True  # round-13: this image's FileList does not set it
    """Enhanced FileList that always shows parent directory (..) with comprehensive debugging"""
    
    def __init__(self, directory, **kwargs):
        """Initialize EnhancedFileList with debug logging"""
        logger.debug(f"[EnhancedFileList] Initializing with directory: {directory}")
        try:
            # Initialize parent class
            FileList.__init__(self, directory, **kwargs)
            
            # Enable parent directory display
            self.alwaysshow_parent = True  
            
            # Enable comprehensive debugging
            self._debug_enabled = True  
            
            # Force enable directory navigation
            self.inhibitDirs = []  # Don't inhibit any directories
            self.isTop = False     # Not at top level
            
            logger.debug(f"[EnhancedFileList] Initialized successfully. Parent dir enabled: {self.alwaysshow_parent}")
            logger.debug(f"[EnhancedFileList] InhibitDirs: {self.inhibitDirs}, isTop: {self.isTop}")
        except Exception as e:
            logger.error(f"[EnhancedFileList] Init error: {e}")
            raise
    
    def changeDir(self, directory, select=None):
        """Override to always show parent directory with detailed debugging"""
        logger.debug(f"[EnhancedFileList] changeDir called: {directory}, select={select}")
        
        try:
            # Store original directory for comparison
            old_dir = self.getCurrentDirectory()
            logger.debug(f"[EnhancedFileList] Changing from {old_dir} to {directory}")
            
            # Call parent method
            FileList.changeDir(self, directory, select)
            
            # Get new directory
            new_dir = self.getCurrentDirectory()
            logger.debug(f"[EnhancedFileList] Now in directory: {new_dir}")
            
            # round-19 fix (Bug 62): during construction this image's FileList
            # triggers changeDir(None) before the real directory is set.
            # getCurrentDirectory() then returns None and os.path.dirname(None)
            # raised TypeError (expected str, bytes or os.PathLike object,
            # not NoneType) - four times at startup. The base class has
            # already handled the None directory by now; only the
            # parent-entry logic must be skipped.
            if new_dir is None:
                logger.debug("[EnhancedFileList] directory not set yet - skipping parent entry")
                return

            # Check if we're at root
            is_root = (new_dir == "/")
            logger.debug(f"[EnhancedFileList] Is root directory: {is_root}")
            
            # Only add parent directory if not at root AND parent display is enabled
            if not is_root and self.alwaysshow_parent:
                logger.debug(f"[EnhancedFileList] Adding parent directory entry for: {new_dir}")
                
                # Check if ".." is already in the list
                has_parent = False
                
                for item in self.list:
                    try:
                        item_path = item[0][0]
                        item_name = item[0][2] if len(item[0]) > 2 else ""
                        
                        # Check for parent directory marker
                        if ".." in str(item_path) or ".." in str(item_name):
                            has_parent = True
                            logger.debug(f"[EnhancedFileList] Found existing '..' entry")
                            break
                    except Exception as e:
                        logger.debug(f"[EnhancedFileList] Error checking item: {e}")
                        continue
                
                # Add ".." at the top if missing
                if not has_parent:
                    try:
                        parent_dir = os.path.dirname(new_dir)
                        logger.debug(f"[EnhancedFileList] Creating parent entry for: {parent_dir}")
                        
                        # Create parent directory entry
                        parent_entry = (
                            (parent_dir, True, "..", False),  # (path, is_dir, name, is_marked)
                            ".."
                        )
                        
                        # Insert at beginning
                        self.list.insert(0, parent_entry)
                        logger.debug(f"[EnhancedFileList] Inserted '..' at position 0")
                        
                        # Update the list display
                        self.l.setList(self.list)
                        logger.debug(f"[EnhancedFileList] Updated list display. Total items: {len(self.list)}")
                        
                        # Log first few items for debugging
                        if len(self.list) > 0 and self._debug_enabled:
                            logger.debug(f"[EnhancedFileList] First few items in list:")
                            for i, item in enumerate(self.list[:3]):
                                try:
                                    item_info = {
                                        'index': i,
                                        'path': item[0][0],
                                        'is_dir': item[0][1],
                                        'name': item[0][2] if len(item[0]) > 2 else '',
                                        'marked': item[0][3] if len(item[0]) > 3 else False
                                    }
                                    logger.debug(f"[EnhancedFileList]   Item {i}: {item_info}")
                                except Exception as item_error:
                                    logger.debug(f"[EnhancedFileList]   Item {i} error: {item_error}")
                                
                    except Exception as e:
                        logger.error(f"[EnhancedFileList] Error adding parent directory: {e}")
                else:
                    logger.debug(f"[EnhancedFileList] '..' already exists in list")
            else:
                if is_root:
                    logger.debug(f"[EnhancedFileList] At root, not adding '..'")
                else:
                    logger.debug(f"[EnhancedFileList] Parent display disabled")
                    
        except Exception as e:
            logger.error(f"[EnhancedFileList] Error in changeDir: {e}")
            # Re-raise to maintain compatibility
            raise
    
    def refresh(self):
        """Refresh the file list with debugging"""
        logger.debug(f"[EnhancedFileList] refresh() called")
        try:
            current_dir = self.getCurrentDirectory()
            logger.debug(f"[EnhancedFileList] Refreshing directory: {current_dir}")
            
            # Call parent refresh
            result = FileList.refresh(self)
            
            # Re-add parent directory if needed
            if current_dir != "/" and self.alwaysshow_parent:
                logger.debug(f"[EnhancedFileList] Re-adding parent directory after refresh")
                self.changeDir(current_dir)  # This will re-add the parent directory
                
            logger.debug(f"[EnhancedFileList] Refresh completed successfully")
            return result
        except Exception as e:
            logger.error(f"[EnhancedFileList] Error in refresh: {e}")
            return False
    
    def getCurrentDirectory(self):
        """Get current directory with debugging"""
        try:
            dir_path = FileList.getCurrentDirectory(self)
            if self._debug_enabled:
                logger.debug(f"[EnhancedFileList] getCurrentDirectory: {dir_path}")
            return dir_path
        except Exception as e:
            logger.error(f"[EnhancedFileList] Error getting current directory: {e}")
            return ""

class WGFileManagerMain(Screen):
    def __init__(self, session):
        """Initialize main screen with comprehensive debugging"""
        logger.info("[MainScreen] Initializing WGFileManagerMain")
        Screen.__init__(self, session)
        
        # 1. Initialize config FIRST - with proper error handling
        try:
            logger.debug("[MainScreen] Creating WGFileManagerConfig instance")
            self.config = WGFileManagerConfig()
            logger.debug("[MainScreen] Config created successfully")
        except Exception as e:
            logger.error(f"[MainScreen] Config init error: {e}")
            from Components.config import config as en_config
            self.config = en_config
            logger.warning("[MainScreen] Using global config as fallback")
        
        # 2. Get screen dimensions
        w, h = getDesktop(0).size().width(), getDesktop(0).size().height()
        pane_width = (w - 60) // 2
        pane_height = h - 320 
        logger.debug(f"[MainScreen] Screen dimensions: {w}x{h}, pane: {pane_width}x{pane_height}")
        
        # 3. Initialize backend core components
        try:
            logger.debug("[MainScreen] Initializing core components")
            self.file_ops = FileOperations(self.config)
            self.archive_mgr = ArchiveManager(self.file_ops)
            self.search_engine = SearchEngine()
            self.remote_mgr = RemoteConnectionManager(self.config)
            self.mount_mgr = MountManager(self.config)
            logger.debug("[MainScreen] Core components initialized")
        except Exception as e:
            logger.error(f"[MainScreen] Error initializing core components: {e}")
        
        # 4. Initialize subtitle manager
        self.subtitle_manager = None  # round-25: legacy engine removed; kept as None for safety
        
        # 5. Initialize state
        self.marked_files = set()
        self.active_pane = None
        
        # 6. Initialize UI components
        logger.debug("[MainScreen] Initializing UI components")
        self.dialogs = Dialogs(self.session)
        self.context_menu = ContextMenuHandler(self, self.config)
        logger.debug("[MainScreen] UI components initialized")
        
        # 7. Setup UI
        self.setup_ui(w, h, pane_width, pane_height)
        
        # 8. Finalize state and actions
        self.init_state()
        self.setup_actions()
        
        # 9. Start
        self.onLayoutFinish.append(self.startup)
        logger.info("[MainScreen] Initialization complete")

    def setup_ui(self, w, h, pane_width, pane_height):
        """Setup user interface with debugging"""
        logger.debug("[MainScreen] Setting up UI")
        
        button_y = h - 60
        label_y = h - 45
        
        # Skin with proper attributes
        self.skin = f"""
        <screen name="WGFileManagerMain" position="0,0" size="{w},{h}" backgroundColor="#1a1a1a" flags="wfNoBorder">
            <eLabel position="0,0" size="{w},60" backgroundColor="#0055aa" />
            <eLabel text="WG FILE MANAGER PRO" position="20,8" size="600,44" font="Regular;30" halign="left" valign="center" transparent="1" foregroundColor="#ffffff" />
            <eLabel text="v1.0 Professional" position="{w-250},12" size="230,36" font="Regular;22" halign="right" valign="center" transparent="1" foregroundColor="#00ffff" />
            
            <widget name="left_banner" position="25,70" size="{pane_width},28" font="Regular;20" halign="left" valign="center" backgroundColor="#333333" foregroundColor="#ffff00" />
            <eLabel position="{pane_width + 30},70" size="10,28" backgroundColor="#555555" />
            <widget name="right_banner" position="{pane_width + 45},70" size="{pane_width},28" font="Regular;20" halign="left" valign="center" backgroundColor="#333333" foregroundColor="#aaaaaa" />
            
            <widget name="left_pane" position="25,110" size="{pane_width},{pane_height}" font="Regular;18" itemHeight="38" selectionColor="#FF5555" scrollbarMode="showOnDemand" />
            <widget name="right_pane" position="{pane_width + 45},110" size="{pane_width},{pane_height}" font="Regular;18" itemHeight="38" selectionColor="#FF5555" scrollbarMode="showOnDemand" />
            
            <widget name="progress_bar" position="20,{h-150}" size="{w-40},8" backgroundColor="#333333" foregroundColor="#00aaff" borderWidth="2" borderColor="#aaaaaa" />
            <widget name="info_panel" position="20,{h-135}" size="{w-40},30" font="Regular;20" foregroundColor="#ff8800" transparent="1" />
            <widget name="status_bar" position="20,{h-100}" size="{w-40},35" font="Regular;22" foregroundColor="#ffffff" transparent="1" />
            
            <eLabel position="0,{h-60}" size="{w},60" backgroundColor="#000000" />
            <ePixmap pixmap="buttons/red.png" position="20,{button_y}" size="30,30" alphatest="on" />
            <ePixmap pixmap="buttons/green.png" position="180,{button_y}" size="30,30" alphatest="on" />
            <ePixmap pixmap="buttons/yellow.png" position="340,{button_y}" size="30,30" alphatest="on" />
            <ePixmap pixmap="buttons/blue.png" position="500,{button_y}" size="30,30" alphatest="on" />
            
            <eLabel text="Delete" position="60,{label_y}" size="100,30" font="Regular;20" transparent="1" foregroundColor="#ffffff" />
            <eLabel text="Rename" position="220,{label_y}" size="100,30" font="Regular;20" transparent="1" foregroundColor="#ffffff" />
            <eLabel text="Select" position="380,{label_y}" size="100,30" font="Regular;20" transparent="1" foregroundColor="#ffffff" />
            <eLabel text="Copy/Move" position="540,{label_y}" size="150,30" font="Regular;20" transparent="1" foregroundColor="#ffffff" />
            <widget name="help_text" position="50,{h-80}" size="{w-100},30" font="Regular;18" halign="right" transparent="1" foregroundColor="#aaaaaa" />
        </screen>"""
        
        # Create widgets
        left_path = self.config.plugins.wgfilemanager.left_path.value
        right_path = self.config.plugins.wgfilemanager.right_path.value
        
        logger.debug(f"[MainScreen] Creating EnhancedFileList widgets")
        logger.debug(f"[MainScreen] Left pane path: {left_path}")
        logger.debug(f"[MainScreen] Right pane path: {right_path}")
        
        try:
            self["left_pane"] = EnhancedFileList(left_path, showDirectories=True, showFiles=True)
            self["right_pane"] = EnhancedFileList(right_path, showDirectories=True, showFiles=True)
            self["left_pane"].useSelection = True
            self["right_pane"].useSelection = True
            logger.debug("[MainScreen] EnhancedFileList widgets created successfully")
        except Exception as e:
            logger.error(f"[MainScreen] Error creating EnhancedFileList: {e}")
            # Fallback to standard FileList
            self["left_pane"] = FileList(left_path, showDirectories=True, showFiles=True)
            self["right_pane"] = FileList(right_path, showDirectories=True, showFiles=True)
            self["left_pane"].useSelection = True
            self["right_pane"].useSelection = True
            logger.warning("[MainScreen] Using standard FileList as fallback")
        
        # Force enable parent directory navigation
        for pane_name, pane in [("left_pane", self["left_pane"]), ("right_pane", self["right_pane"])]:
            try:
                pane.inhibitDirs = []  # Don't inhibit any directories
                pane.isTop = False  # Not at top level
                logger.debug(f"[MainScreen] Configured {pane_name}: inhibitDirs={pane.inhibitDirs}, isTop={pane.isTop}")
            except Exception as e:
                logger.error(f"[MainScreen] Error configuring {pane_name}: {e}")
         
        # Other widgets
        self["progress_bar"] = ProgressBar()
        self["status_bar"] = Label("Loading...")
        self["info_panel"] = Label("")
        self["left_banner"] = Label("◀ LEFT PANE")
        self["right_banner"] = Label("RIGHT PANE ▶")
        self["help_text"] = Label("OK:Navigate(hold:Menu) 0:Menu YEL:Select MENU:Tools")

        # Apply styling
        try:
            for pane_name, pane in [("left_pane", self["left_pane"]), ("right_pane", self["right_pane"])]:
                try:
                    # Force the row height to stop overlapping
                    pane.itemHeight = 48  # round-31 (Bug 90): match the listbox row height
                    if hasattr(pane, "l"):
                        pane.l.setItemHeight(48)  # round-30 (Bug 87): roomier rows
                        try:
                            pane.l.setFont(gFont("Regular", 26))  # round-30 (Bug 87): readable text
                        except TypeError:
                            # round-14: newer images use setFont(font_index, gFont)
                            try:
                                pane.l.setFont(0, gFont("Regular", 26))
                            except Exception:
                                pass
                        logger.debug(f"[MainScreen] Applied styling to {pane_name}")
                    else:
                        logger.warning(f"[MainScreen] No 'l' attribute on {pane_name}")
                except Exception as e:
                    logger.error(f"[MainScreen] Error applying styling to {pane_name}: {e}")
        except Exception as e:
            logger.error(f"[MainScreen] Error in UI styling: {e}")
        
        logger.debug("[MainScreen] UI setup complete")

    def init_state(self):
        """Initialize application state"""
        logger.debug("[MainScreen] Initializing state")
        
        # Operation state
        self.operation_in_progress = False
        self.operation_lock = threading.Lock()
        self.operation_timer = eTimer()
        self.operation_timer.callback.append(self.update_operation_progress)
        self.operation_current = 0
        self.operation_total = 0
        
        # Clipboard
        self.clipboard = []
        self.clipboard_mode = None  # 'copy' or 'cut'
        
        # Bookmarks
        self.bookmarks = self.config.load_bookmarks()
        logger.debug(f"[MainScreen] Loaded {len(self.bookmarks)} bookmarks")
        
        # Active pane
        starting_pane = self.config.plugins.wgfilemanager.starting_pane.value
        if starting_pane == "left":
            self.active_pane = self["left_pane"]
            self.inactive_pane = self["right_pane"]
        else:
            self.active_pane = self["right_pane"]
            self.inactive_pane = self["left_pane"]
        
        logger.debug(f"[MainScreen] Active pane: {'left' if starting_pane == 'left' else 'right'}")
        
        # Sort modes
        self.left_sort_mode = self.config.plugins.wgfilemanager.left_sort_mode.value
        self.right_sort_mode = self.config.plugins.wgfilemanager.right_sort_mode.value
        logger.debug(f"[MainScreen] Sort modes - Left: {self.left_sort_mode}, Right: {self.right_sort_mode}")
        
        # Filter
        self.filter_pattern = None
        
        # Preview state
        self.preview_in_progress = False
        
        # Track marked files for color changes
        self.marked_files = set()
        logger.debug(f"[MainScreen] State initialization complete")

    def setup_actions(self):
        """Setup key mappings"""
        logger.debug("[MainScreen] Setting up action map")
        self["actions"] = ActionMap([
            "WGFileManagerActions",
            "OkCancelActions", "ColorActions", "DirectionActions", 
            "MenuActions", "NumberActions", "ChannelSelectBaseActions"
        ], {
            "ok": self.ok_pressed,
            "ok_long": self.play_whole_folder,   # round-60 (Bug 128): hold OK
            "cancel": self.exit,
            "exit": self.exit,
            "up": self.up,
            "down": self.down,
            "left": self.focus_left,
            "right": self.focus_right,
            "red": self.delete_request,
            "green": self.rename_request,
            "yellow": self.toggle_selection,
            "yellow_long": self.unmark_all,
            "blue": self.quick_copy,
            "menu": self.open_tools,
            "0": self.zero_pressed,
            "1": lambda: self.quick_bookmark(1),
            "2": lambda: self.quick_bookmark(2),
            "3": lambda: self.quick_bookmark(3),
            "4": lambda: self.quick_bookmark(4),
            "5": lambda: self.quick_bookmark(5),
            "6": lambda: self.quick_bookmark(6),
            "7": lambda: self.quick_bookmark(7),
            "8": lambda: self.quick_bookmark(8),
            "9": lambda: self.quick_bookmark(9),
            "play": self.preview_media,
            "playpause": self.preview_media,
            "info": self.show_storage_quick_selector,
            "text": self.preview_file,
            "nextBouquet": self.next_sort,
            "prevBouquet": self.prev_sort,
            "channelUp": self.next_sort,
            "channelDown": self.prev_sort,
            "audio": self.show_storage_selector,
            "pageUp": lambda: self.page_up(),
            "pageDown": lambda: self.page_down(),
            "back": self.navigate_to_parent,
            "home": lambda: self.go_home(),
            "end": lambda: self.go_end(),
            "subtitle": self.open_subtitle_settings,
            "help": self.open_hotkey_settings,
        }, -1)
        logger.debug("[MainScreen] Action map setup complete")

    def startup(self):
        """Startup initialization"""
        logger.info("[MainScreen] Starting up...")
        
        # Show loading message
        self["status_bar"].setText("Initializing...")
        
        # Validate config first
        if not self.validate_config():
            self.dialogs.show_message(
                "Configuration issues detected!\n\nUsing default paths.",
                type="warning"
            )
        
        self.check_dependencies()
        self.update_ui()
        self.update_help_text()
        
        if self.config.plugins.wgfilemanager.show_dirs_first.value == "yes":
            self.apply_show_dirs_first()
        
        logger.info("[MainScreen] WGFileManager started successfully")
        self["status_bar"].setText("Ready")
        logger.debug(f"[MainScreen] Startup complete. Active pane: {self.active_pane.getCurrentDirectory()}")

    def validate_config(self):
        """Validate configuration with debugging"""
        logger.debug("[MainScreen] Validating configuration")
        issues = []
        
        # Check paths exist
        left_path = self.config.plugins.wgfilemanager.left_path.value
        if not os.path.isdir(left_path):
            issues.append(f"Left path not found: {left_path}")
            logger.warning(f"[MainScreen] Left path not found: {left_path}")
        
        right_path = self.config.plugins.wgfilemanager.right_path.value
        if not os.path.isdir(right_path):
            issues.append(f"Right path not found: {right_path}")
            logger.warning(f"[MainScreen] Right path not found: {right_path}")
        
        if issues:
            logger.warning(f"[MainScreen] Config issues: {issues}")
            return False
        
        logger.debug("[MainScreen] Configuration validated successfully")
        return True

    # UI Update Methods
    def update_ui(self):
        """Update user interface with debugging"""
        logger.debug("[MainScreen] Updating UI")
        try:
            self.update_banners()
            self.update_status_bar()
            self.update_info_panel()
            logger.debug("[MainScreen] UI update complete")
        except Exception as e:
            logger.error(f"[MainScreen] Error updating UI: {e}")

    def update_banners(self):
        """Update pane banners - shows full path information"""
        try:
            is_left_active = (self.active_pane == self["left_pane"])
            is_right_active = (self.active_pane == self["right_pane"])
            
            logger.debug(f"[MainScreen] Active pane: {'left' if is_left_active else 'right'}")
            
            # Get directory paths
            try:
                left_dir = self["left_pane"].getCurrentDirectory()
                right_dir = self["right_pane"].getCurrentDirectory()
                
                logger.debug(f"[MainScreen] Left dir: {left_dir}")
                logger.debug(f"[MainScreen] Right dir: {right_dir}")
                
                # Build text with indicators
                if is_left_active:
                    left_text = "◀ LEFT: " + left_dir
                    right_text = "RIGHT: " + right_dir
                else:
                    left_text = "LEFT: " + left_dir
                    right_text = "RIGHT: " + right_dir + " ▶"
                
                # Shorten if too long
                if len(left_text) > 50:
                    left_text = left_text[:47] + "..."
                if len(right_text) > 50:
                    right_text = right_text[:47] + "..."
                    
            except Exception as e:
                logger.error(f"[MainScreen] Error getting directory paths: {e}")
                left_text = "◀ LEFT" if is_left_active else "LEFT"
                right_text = "RIGHT ▶" if is_right_active else "RIGHT"
            
            self["left_banner"].setText(left_text)
            self["right_banner"].setText(right_text)
            
            # Update colors
            try:
                from enigma import gRGB
                
                ACTIVE_COLOR = gRGB(0xffff00)  # Yellow
                INACTIVE_COLOR = gRGB(0xaaaaaa)  # Gray
                
                left_instance = self["left_banner"].instance
                right_instance = self["right_banner"].instance
                
                if left_instance:
                    left_instance.setForegroundColor(ACTIVE_COLOR if is_left_active else INACTIVE_COLOR)
                
                if right_instance:
                    right_instance.setForegroundColor(ACTIVE_COLOR if is_right_active else INACTIVE_COLOR)
                    
                logger.debug(f"[MainScreen] Banner colors updated")
            except Exception as e:
                logger.error(f"[MainScreen] Banner styling error: {e}")
                
        except Exception as e:
            logger.error(f"[MainScreen] Error updating banners: {e}")

    def update_status_bar(self):
        """Update the bottom status bar with selection info"""
        try:
            # 1. Get the number of marked items
            count = len(self.marked_files)
            logger.debug(f"[MainScreen] Marked files count: {count}")
            
            # 2. Get current path info for the active pane
            sel = self.active_pane.getSelection()
            current_name = ""
            if sel and sel[0]:
                current_name = os.path.basename(sel[0])
                logger.debug(f"[MainScreen] Current selection: {current_name}")

            # 3. Create the status text
            if count > 0:
                status_text = "✓ SELECTED: %d items | Current: %s" % (count, current_name)
            else:
                current_dir = self.active_pane.getCurrentDirectory()
                status_text = "Path: %s" % current_dir
                logger.debug(f"[MainScreen] Current directory: {current_dir}")

            # 4. Update the Label widget
            self["status_bar"].setText(status_text)
            
            logger.debug(f"[MainScreen] Status bar updated: {status_text[:50]}...")
            
        except Exception as e:
            logger.error(f"[MainScreen] Error updating status bar: {e}")

    def update_info_panel(self):
        """Update info panel with current file details"""
        try:
            sel = self.active_pane.getSelection()
            if sel and sel[0]:
                path = sel[0]
                name = os.path.basename(path)
                icon = get_file_icon(path)
                
                logger.debug(f"[MainScreen] Updating info panel for: {name}")
                
                # Check if file is marked
                is_marked = False
                for item in self.active_pane.list:
                    if item[0][0] == path and item[0][3]:  # Marked
                        is_marked = True
                        break
                logger.debug(f"[MainScreen] File marked: {is_marked}")
                
                # Only get size for files, not directories
                if os.path.isfile(path):
                    try:
                        size = os.path.getsize(path)
                        size_str = format_size(size)
                        logger.debug(f"[MainScreen] File size: {size_str}")
                    except:
                        size_str = "?"
                else:
                    size_str = "DIR"
                
                # Show in RED if marked
                if is_marked:
                    text = f" {icon} {name} | {size_str}"
                else:
                    text = f"{icon} {name} | {size_str}"
                    
                self["info_panel"].setText(text)
                logger.debug(f"[MainScreen] Info panel text set: {text}")
                return
        except Exception as e:
            logger.debug(f"[MainScreen] Error updating info panel: {e}")
        
        self["info_panel"].setText("")
        logger.debug("[MainScreen] Info panel cleared")

    def update_operation_progress(self):
        """Update progress bar during operations"""
        try:
            if self.operation_total > 0:
                progress = int((self.operation_current / self.operation_total) * 100)
                self["progress_bar"].setValue(progress)
                logger.debug(f"[MainScreen] Operation progress: {progress}% ({self.operation_current}/{self.operation_total})")
            self.update_ui()
        except Exception as e:
            logger.error(f"[MainScreen] Error updating operation progress: {e}")

    def update_help_text(self):
        """Update help text"""
        help_text = "OK:Play/Open 0:Menu INFO:Storage 1-9:BMark MENU:Tools SUBTITLE:Subtitle Settings"
        self["help_text"].setText(help_text)
        logger.debug(f"[MainScreen] Help text updated")

    # OK Button Long Press Detection
    def ok_pressed(self):
        """Handle OK button press - SIMPLE NAVIGATION"""
        logger.debug("[MainScreen] OK button pressed")
        self.execute_ok_navigation()

    def execute_ok_navigation(self):
        """Execute navigation - PERFECT SMART BEHAVIOR"""
        try:
            sel = self.active_pane.getSelection()
            if not sel or not sel[0]:
                logger.debug("[MainScreen] No selection for OK navigation")
                return
            
            path = sel[0]
            logger.debug(f"[MainScreen] OK navigation for: {path}")
            
            # Handle parent directory (..)
            if path.endswith("..") or os.path.basename(path) == "..":
                current_dir = self.active_pane.getCurrentDirectory()
                logger.debug(f"[MainScreen] Navigating to parent directory from: {current_dir}")
                
                if current_dir != "/":
                    parent_dir = os.path.dirname(current_dir)
                    logger.debug(f"[MainScreen] Changing to parent directory: {parent_dir}")
                    self.active_pane.changeDir(parent_dir)
                    self.update_ui()
                else:
                    logger.debug("[MainScreen] Already at root directory")
                return
            
            # Continue with normal navigation
            if os.path.isdir(path):
                # Folders: Enter directory
                logger.debug(f"[MainScreen] Entering directory: {path}")
                self.active_pane.changeDir(path)
                self.update_ui()
            else:
                # Files: Smart behavior based on type
                ext = os.path.splitext(path)[1].lower()
                logger.debug(f"[MainScreen] File extension: {ext}")
                
                # Video files: Show playback options
                if ext in ['.mp4', '.mkv', '.avi', '.ts', '.m2ts', '.mov', '.m4v', '.mpg', '.mpeg', '.wmv', '.flv']:
                    logger.debug(f"[MainScreen] Video file detected, showing playback options")
                    self.play_media_file(path)   # round-61: direct play (dialog removed)
                # Audio files: SHOW MENU
                elif ext in ['.mp3', '.flac', '.wav', '.aac', '.ogg', '.m4a', '.wma', '.ac3', '.dts']:
                    logger.debug(f"[MainScreen] Audio file detected, showing smart menu")
                    self.context_menu.show_smart_context_menu(path)
                # Script files: Show menu
                elif ext in ['.sh', '.py', '.pl']:
                    logger.debug(f"[MainScreen] Script file detected, showing smart menu")
                    self.context_menu.show_smart_context_menu(path)
                # Archive files: Show menu
                elif ext in ['.zip', '.tar', '.tar.gz', '.tgz', '.rar', '.7z', '.gz']:
                    logger.debug(f"[MainScreen] Archive file detected, showing smart menu")
                    self.context_menu.show_smart_context_menu(path)
                # IPK packages: Show menu
                elif ext == '.ipk':
                    logger.debug(f"[MainScreen] IPK package detected, showing smart menu")
                    self.context_menu.show_smart_context_menu(path)
                # Text files: Preview
                elif ext in ['.txt', '.log', '.conf', '.cfg', '.ini', '.xml', '.json', '.md']:
                    logger.debug(f"[MainScreen] Text file detected, previewing")
                    self.preview_file()
                # Image files: Preview
                elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']:
                    logger.debug(f"[MainScreen] Image file detected, previewing")
                    self.dialogs.preview_image(path, self.file_ops)
                # Default: Show file info
                else:
                    logger.debug(f"[MainScreen] Unknown file type, showing file info")
                    self.show_file_info()
                    
        except Exception as e:
            logger.error(f"[MainScreen] Error in OK navigation: {e}")
            self.show_error("Navigation", e)

    def _show_media_playback_choice(self, file_path):
        """Show media playback options for video files"""
        from Screens.ChoiceBox import ChoiceBox
        
        menu_items = [
            ("Play ALL media in this folder", "play_folder"),
        ]
        
        logger.debug(f"[MainScreen] Showing media playback choice for: {os.path.basename(file_path)}")
        
        self.session.openWithCallback(
            lambda choice: self._handle_media_playback_choice(choice, file_path) if choice else None,
            ChoiceBox,
            title=f"Play: {os.path.basename(file_path)[:30]}",
            list=menu_items
        )
    
    def _handle_media_playback_choice(self, choice, file_path):
        """Handle media playback choice"""
        if not choice:
            logger.debug("[MainScreen] Media playback choice cancelled")
            return
        
        action = choice[1]
        logger.debug(f"[MainScreen] Media playback action selected: {action}")
        
        try:
            if action == "play_no_subs":
                logger.debug(f"[MainScreen] Playing without subtitles")
                self.play_media_file(file_path)
            elif action == "play_with_subs":
                logger.debug(f"[MainScreen] Playing with subtitles")
                self.play_media_file(file_path)
            elif action == "play_folder":
                logger.debug(f"[MainScreen] Playing entire folder")
                from ..player.custom_media_player import playDirectory
                playDirectory(self.session, os.path.dirname(file_path))
        except Exception as e:
            logger.error(f"[MainScreen] Error handling playback choice: {e}")
            self.dialogs.show_message(f"Playback error: {e}", type="error")

    def navigate_to_parent(self):
        """Navigate to parent directory - Enhanced with visual feedback"""
        try:
            current_dir = self.active_pane.getCurrentDirectory()
            logger.debug(f"[MainScreen] Navigating to parent from: {current_dir}")
        
            if current_dir and current_dir != "/":
                parent_dir = os.path.dirname(current_dir)
                logger.debug(f"[MainScreen] Parent directory: {parent_dir}")
            
                # Visual feedback
                self["status_bar"].setText(f"↑ {parent_dir}")
            
                # Navigate
                self.active_pane.changeDir(parent_dir)
                self.update_ui()
            
                logger.info(f"[MainScreen] Navigated to parent: {parent_dir}")
            else:
                # Flash indicator when already at root
                self["status_bar"].setText("Already at root directory")
            
                # Reset message after 1 second
                # round-15 fix (Bug 53): sleeping thread touched the GUI -
                # crashes on this image (StackTrace %d error). Main-loop timer:
                from enigma import eTimer
                _t = eTimer()
                _t.callback.append(self.update_status_bar)
                _t.start(1000, True)
                if not hasattr(self, "_wg_timers"):
                    self._wg_timers = []
                self._wg_timers.append(_t)
            
        except Exception as e:
            logger.error(f"[MainScreen] Error navigating to parent: {e}")
            self.show_error("Navigate parent", e)

    def toggle_selection(self):
        """Toggle mark/unmark for current item - YELLOW button"""
        try:
            # 1. Get the current active pane and what is highlighted
            pane = self.active_pane
            sel = pane.getSelection()
            
            if sel and sel[0]:
                # 2. Toggle the visual mark in the Enigma2 FileList component
                pane.markSelected()
                
                # 3. Update our internal tracker
                path = sel[0]
                if path in self.marked_files:
                    self.marked_files.remove(path)
                else:
                    self.marked_files.add(path)
                
                # 4. Refresh the UI
                self.update_info_panel()
                self.update_status_bar()
                
                logger.debug(f"[MainScreen] Toggled selection for: {path}")
        except Exception as e:
            logger.error(f"[MainScreen] Error toggling selection: {e}")

    def unmark_all(self):
        """Clears all marked files from memory and refreshes the UI"""
        logger.debug("[MainScreen] Unmark all called")
        if self.marked_files:
            self.marked_files.clear()
            # Refresh both panes so the visual markers disappear
            self["left_pane"].refresh()
            self["right_pane"].refresh()
            self["status_bar"].setText("All selections cleared.")
            logger.info("[MainScreen] Marked files cleared by user")
        else:
            self["status_bar"].setText("Nothing was selected.")
            logger.debug("[MainScreen] No marked files to clear")

    def up(self):
        """Move up in file list"""
        try:
            self.active_pane.up()
            self.update_info_panel()
            logger.debug("[MainScreen] Moved up in list")
        except Exception as e:
            logger.error(f"[MainScreen] Error moving up: {e}")

    def down(self):
        """Move down in file list"""
        try:
            self.active_pane.down()
            self.update_info_panel()
            logger.debug("[MainScreen] Moved down in list")
        except Exception as e:
            logger.error(f"[MainScreen] Error moving down: {e}")

    def page_up(self):
        """Page up in file list"""
        try:
            for _ in range(10):
                self.active_pane.up()
            self.update_info_panel()
            logger.debug("[MainScreen] Page up (10 items)")
        except Exception as e:
            logger.error(f"[MainScreen] Error page up: {e}")

    def page_down(self):
        """Page down in file list"""
        try:
            for _ in range(10):
                self.active_pane.down()
            self.update_info_panel()
            logger.debug("[MainScreen] Page down (10 items)")
        except Exception as e:
            logger.error(f"[MainScreen] Error page down: {e}")

    def go_home(self):
        """Go to first item"""
        try:
            self.active_pane.instance.moveSelection(self.active_pane.instance.moveTop)
            self.update_info_panel()
            logger.debug("[MainScreen] Went to first item")
        except Exception as e:
            logger.error(f"[MainScreen] Error going home: {e}")

    def go_end(self):
        """Go to last item"""
        try:
            self.active_pane.instance.moveSelection(self.active_pane.instance.moveBottom)
            self.update_info_panel()
            logger.debug("[MainScreen] Went to last item")
        except Exception as e:
            logger.error(f"[MainScreen] Error going end: {e}")

    def focus_left(self):
        """Switch focus to left pane"""
        try:
            self.active_pane = self["left_pane"]
            self.inactive_pane = self["right_pane"]
            self.update_ui()
            self.update_help_text()
            logger.debug("[MainScreen] Focus switched to left pane")
        except Exception as e:
            logger.error(f"[MainScreen] Error focusing left pane: {e}")

    def focus_right(self):
        """Switch focus to right pane"""
        try:
            self.active_pane = self["right_pane"]
            self.inactive_pane = self["left_pane"]
            self.update_ui()
            self.update_help_text()
            logger.debug("[MainScreen] Focus switched to right pane")
        except Exception as e:
            logger.error(f"[MainScreen] Error focusing right pane: {e}")

    # File Operations
    def delete_request(self):
        """Request file deletion - RED button"""
        try:
            # Check for multi-selected files first
            marked = [x for x in self.active_pane.list if x[0][3]]
            
            if marked:
                # Multi-select delete
                files = [x[0][0] for x in marked]
                logger.debug(f"[MainScreen] Delete request for {len(files)} selected items")
                self.dialogs.show_confirmation(
                    f"Delete {len(files)} selected items?\n\nThis cannot be undone!",
                    lambda res: self._execute_delete_multiple(res, files) if res else None
                )
            else:
                # Single file delete
                sel = self.active_pane.getSelection()
                if not sel or not sel[0]:
                    self.dialogs.show_message("No file selected!", type="info")
                    return
                
                item_path = sel[0]
                item_name = os.path.basename(item_path)
                is_dir = os.path.isdir(item_path)
                item_type = "folder" if is_dir else "file"
                
                logger.debug(f"[MainScreen] Delete request for {item_type}: {item_name}")
                
                self.dialogs.show_confirmation(
                    f"Delete {item_type} '{item_name}'?\n\nThis cannot be undone!",
                    lambda res: self._execute_delete(res, item_path, item_name) if res else None
                )
        except Exception as e:
            logger.error(f"[MainScreen] Error in delete request: {e}")
            self.show_error("Delete", e)

    def _execute_delete(self, confirmed, item_path, item_name):
        """Execute deletion"""
        if not confirmed:
            logger.debug(f"[MainScreen] Delete cancelled for: {item_name}")
            return
        
        try:
            logger.debug(f"[MainScreen] Executing delete for: {item_path}")
            self.file_ops.delete(item_path)
            self.active_pane.refresh()
            self.update_ui()
            
            if self.config.plugins.wgfilemanager.trash_enabled.value == "yes":
                msg = f"Moved to trash: {item_name}"
            else:
                msg = f"Permanently deleted: {item_name}"
            
            self.dialogs.show_message(msg, type="info", timeout=2)
            logger.info(f"[MainScreen] Deleted: {item_name}")
        except Exception as e:
            logger.error(f"[MainScreen] Error executing delete: {e}")
            self.show_error("Delete", e)

    def _execute_delete_multiple(self, confirmed, files):
        """Execute deletion of multiple items"""
        if not confirmed:
            logger.debug(f"[MainScreen] Multiple delete cancelled")
            return
        
        try:
            logger.debug(f"[MainScreen] Executing delete for {len(files)} items")
            success = 0
            errors = []
            
            for item_path in files:
                try:
                    self.file_ops.delete(item_path)
                    success += 1
                except Exception as e:
                    errors.append(f"{os.path.basename(item_path)}: {str(e)[:30]}")
            
            msg = f"Deleted: {success} items\n"
            if errors:
                msg += f"\nFailed: {len(errors)}\n"
                msg += "\n".join(errors[:3])
                if len(errors) > 3:
                    msg += f"\n... and {len(errors) - 3} more"
            
            self.active_pane.refresh()
            self.update_ui()
            self.dialogs.show_message(msg, type="info")
            logger.info(f"[MainScreen] Multiple delete completed: {success} successful, {len(errors)} failed")
        except Exception as e:
            logger.error(f"[MainScreen] Error deleting multiple items: {e}")
            self.dialogs.show_message(f"Delete multiple failed: {e}", type="error")

    def rename_request(self):
        """Request file rename - GREEN button"""
        try:
            # Check for multi-selected files
            marked = [x for x in self.active_pane.list if x[0][3]]
        
            if len(marked) > 1:
                logger.debug(f"[MainScreen] Rename request for {len(marked)} items - showing bulk rename suggestion")
                self.dialogs.show_message(
                    f"Multiple files selected ({len(marked)} items)\n\nUse MENU -> Tools -> Bulk Rename\nfor renaming multiple files",
                    type="info"
                )
                return
        
            # Single file rename
            sel = self.active_pane.getSelection()
            if not sel or not sel[0]:
                self.dialogs.show_message("No file selected!", type="info")
                return
        
            item_path = sel[0]
            current_name = os.path.basename(item_path)
            logger.debug(f"[MainScreen] Rename request for: {current_name}")
        
            def rename_callback(new_name):
                if new_name and new_name != current_name:
                    self._execute_rename(new_name, item_path, current_name)
        
            # Instantiate keyboard with filename
            keyboard_screen = self.session.instantiateDialog(
                VirtualKeyBoard,
                title="Rename: " + current_name[:30],
                text=current_name
            )
        
            # Force the text to be the filename
            if hasattr(keyboard_screen, 'text'):
                keyboard_screen.text = current_name
            if hasattr(keyboard_screen, 'Text'):
                keyboard_screen.Text = current_name
        
            self.session.openWithCallback(rename_callback, keyboard_screen)
        
        except Exception as e:
            logger.error(f"[MainScreen] Error in rename request: {e}")
            self.show_error("Rename", e)

    def _execute_rename(self, new_name, old_path, old_name):
        """Execute rename"""
        if not new_name or new_name == old_name:
            logger.debug(f"[MainScreen] Rename cancelled or same name: {new_name}")
            return
        
        try:
            logger.debug(f"[MainScreen] Executing rename: {old_name} -> {new_name}")
            new_path = self.file_ops.rename(old_path, new_name)
            self.active_pane.refresh()
            self.update_ui()
            self.dialogs.show_message(f"Renamed to: {new_name}", type="info", timeout=2)
            logger.info(f"[MainScreen] Renamed: {old_name} -> {new_name}")
        except Exception as e:
            logger.error(f"[MainScreen] Error executing rename: {e}")
            self.show_error("Rename", e)

    def quick_copy(self):
        """Quick copy/move operation - BLUE button"""
        try:
            if self.clipboard:
                logger.debug("[MainScreen] Clipboard has items, performing paste")
                self.paste_from_clipboard()
                return
            
            # Get destination
            if self.active_pane == self["left_pane"]:
                dest_pane = self["right_pane"]
            else:
                dest_pane = self["left_pane"]
            
            dest = dest_pane.getCurrentDirectory()
            files = self.get_selected_files()
            
            if not files:
                self.dialogs.show_message("No files selected!", type="info")
                return
            
            logger.debug(f"[MainScreen] Quick copy: {len(files)} files to {dest}")
            self.dialogs.show_transfer_dialog(files, dest, self.execute_transfer)
        except Exception as e:
            logger.error(f"[MainScreen] Error in quick copy: {e}")
            self.show_error("Copy", e)

    def get_selected_files(self):
        """Get selected files"""
        files = []
        try:
            for item in self.active_pane.list:
                if item[0][3]:  # Marked
                    files.append(item[0][0])
            
            if not files:
                sel = self.active_pane.getSelection()
                if sel and sel[0]:
                    files.append(sel[0])
            
            logger.debug(f"[MainScreen] Selected files: {len(files)} items")
        except Exception as e:
            logger.error(f"[MainScreen] Error getting selected files: {e}")
        
        return files

    def paste_from_clipboard(self):
        """Paste files from clipboard"""
        if not self.clipboard:
            logger.debug("[MainScreen] Clipboard empty")
            return
        
        try:
            dest = self.active_pane.getCurrentDirectory()
            logger.debug(f"[MainScreen] Paste from clipboard: {len(self.clipboard)} items to {dest}")
            
            if not os.path.isdir(dest):
                self.dialogs.show_message(f"Invalid destination: {dest}", type="error")
                return
            
            mode = "cp" if self.clipboard_mode == "copy" else "mv"
            action = "Copy" if mode == "cp" else "Move"
            
            self.dialogs.show_confirmation(
                f"{action} {len(self.clipboard)} items to:\n{dest}?",
                lambda res: self.execute_paste(res, mode, self.clipboard[:], dest)
            )
        except Exception as e:
            logger.error(f"[MainScreen] Error pasting from clipboard: {e}")
            self.show_error("Paste", e)

    def execute_paste(self, confirmed, mode, files, dest):
        """Execute paste operation"""
        if not confirmed:
            logger.debug("[MainScreen] Paste cancelled")
            return
        
        with self.operation_lock:
            if self.operation_in_progress:
                self.dialogs.show_message("Another operation is in progress!", type="warning")
                return
            self.operation_in_progress = True
        
        try:
            logger.debug(f"[MainScreen] Starting paste operation: {mode}, {len(files)} files to {dest}")
            self.operation_current = 0
            self.operation_total = len(files)
            self.operation_timer.start(500)
            
            thread = threading.Thread(
                target=self._perform_paste,
                args=(mode, files, dest),
                daemon=True
            )
            thread.start()
        except Exception as e:
            logger.error(f"[MainScreen] Error starting paste operation: {e}")
            with self.operation_lock:
                self.operation_in_progress = False
            self.show_error("Paste", e)

    def _perform_paste(self, mode, files, dest):
        """Perform paste operation in thread"""
        try:
            logger.debug(f"[MainScreen] Performing paste operation: {mode}, {len(files)} files")
            
            for i, src in enumerate(files):
                try:
                    if mode == "cp":
                        logger.debug(f"[MainScreen] Copying: {src} -> {dest}")
                        self.file_ops.copy(src, dest)
                    elif mode == "mv":
                        logger.debug(f"[MainScreen] Moving: {src} -> {dest}")
                        self.file_ops.move(src, dest)
                    
                    with self.operation_lock:
                        self.operation_current = i + 1
                    
                except Exception as e:
                    logger.error(f"[MainScreen] Paste failed for {src}: {e}")
                    # Continue with next file
            
            # Operation complete
            with self.operation_lock:
                self.operation_in_progress = False
                self.operation_timer.stop()
            
            # Clear clipboard if it was a cut operation
            if mode == "mv":
                self.clipboard = []
                self.clipboard_mode = None
                logger.debug("[MainScreen] Clipboard cleared (cut operation)")
            
            # Update UI in main thread
            self.session.openWithCallback(
                lambda: None,
                MessageBox,
                "Paste complete!",
                type=MessageBox.TYPE_INFO,
                timeout=2
            )
            
            # Refresh panes
            self.active_pane.refresh()
            self.inactive_pane.refresh()
            self.update_ui()
            
            logger.info(f"[MainScreen] Paste operation completed successfully")
            
        except Exception as e:
            logger.error(f"[MainScreen] Paste operation failed: {e}")
            with self.operation_lock:
                self.operation_in_progress = False
                self.operation_timer.stop()
            
            # Show error in main thread
            self.session.openWithCallback(
                lambda: None,
                MessageBox,
                f"Paste failed:\n{e}",
                type=MessageBox.TYPE_ERROR
            )

    def execute_transfer(self, mode, files, dest):
        """Execute file transfer"""
        with self.operation_lock:
            if self.operation_in_progress:
                self.dialogs.show_message("Another operation is in progress!", type="warning")
                return
            self.operation_in_progress = True
        
        try:
            logger.debug(f"[MainScreen] Starting transfer operation: {mode}, {len(files)} files to {dest}")
            self.operation_current = 0
            self.operation_total = len(files)
            self.operation_timer.start(500)
            
            thread = threading.Thread(
                target=self._perform_transfer,
                args=(mode, files, dest),
                daemon=True
            )
            thread.start()
        except Exception as e:
            logger.error(f"[MainScreen] Error starting transfer operation: {e}")
            with self.operation_lock:
                self.operation_in_progress = False
            self.show_error("Transfer", e)

    def _perform_transfer(self, mode, files, dest):
        """Perform transfer in thread"""
        try:
            logger.debug(f"[MainScreen] Performing transfer operation: {mode}, {len(files)} files")
            
            for i, src in enumerate(files):
                try:
                    if mode == "cp":
                        logger.debug(f"[MainScreen] Copying: {src} -> {dest}")
                        self.file_ops.copy(src, dest)
                    elif mode == "mv":
                        logger.debug(f"[MainScreen] Moving: {src} -> {dest}")
                        self.file_ops.move(src, dest)
                    
                    with self.operation_lock:
                        self.operation_current = i + 1
                    
                except Exception as e:
                    logger.error(f"[MainScreen] Transfer failed for {src}: {e}")
                    # Continue with next file
            
            # Operation complete
            with self.operation_lock:
                self.operation_in_progress = False
                self.operation_timer.stop()
            
            # Update UI in main thread
            self.session.openWithCallback(
                lambda: None,
                MessageBox,
                "Transfer complete!",
                type=MessageBox.TYPE_INFO,
                timeout=2
            )
            
            # Refresh panes
            self.active_pane.refresh()
            self.inactive_pane.refresh()
            self.update_ui()
            
            logger.info(f"[MainScreen] Transfer operation completed successfully")
            
        except Exception as e:
            logger.error(f"[MainScreen] Transfer operation failed: {e}")
            with self.operation_lock:
                self.operation_in_progress = False
                self.operation_timer.stop()
            
            # Show error in main thread
            self.session.openWithCallback(
                lambda: None,
                MessageBox,
                f"Transfer failed:\n{e}",
                type=MessageBox.TYPE_ERROR
            )

    # Tools and Features
    def open_tools(self):
        """Open tools menu"""
        if self.operation_in_progress:
            self.dialogs.show_message("Please wait for current operation to complete!", type="info")
            return
        
        try:
            logger.debug("[MainScreen] Opening tools menu")
            self.context_menu.show_tools_menu()
        except Exception as e:
            logger.error(f"[MainScreen] Error opening tools menu: {e}")
            self.show_error("Tools menu", e)

    def zero_pressed(self):
        """0 button - Show context menu"""
        try:
            logger.debug("[MainScreen] 0 pressed - showing context menu")
            
            if not self.config.plugins.wgfilemanager.enable_smart_context.value:
                self.show_file_info()
                return
            
            marked = [x for x in self.active_pane.list if x[0][3]]
            
            if marked:
                logger.debug(f"[MainScreen] Showing multi-selection context menu for {len(marked)} items")
                self.context_menu.show_multi_selection_context_menu(marked)
            else:
                logger.debug("[MainScreen] Showing regular context menu")
                self.context_menu.show_context_menu()
        except Exception as e:
            logger.error(f"[MainScreen] Error in zero pressed: {e}")
            self.show_error("Context menu", e)

    def quick_bookmark(self, num):
        """Quick bookmark access"""
        try:
            key = str(num)
            logger.debug(f"[MainScreen] Quick bookmark {num} pressed")
            
            if key in self.bookmarks:
                path = self.bookmarks[key]
                if os.path.isdir(path):
                    self.active_pane.changeDir(path)
                    self.update_ui()
                    self["status_bar"].setText(f"Jumped to bookmark {num}: {os.path.basename(path)}")
                    logger.debug(f"[MainScreen] Jumped to bookmark {num}: {path}")
                else:
                    self.dialogs.show_message(f"Bookmark {num} path not found: {path}", type="error")
                    logger.warning(f"[MainScreen] Bookmark {num} path not found: {path}")
            else:
                current = self.active_pane.getCurrentDirectory()
                self.bookmarks[key] = current
                self.config.save_bookmarks(self.bookmarks)
                self.dialogs.show_message(f"Bookmark {num} set to:\n{current}", type="info", timeout=2)
                logger.info(f"[MainScreen] Bookmark {num} set to: {current}")
        except Exception as e:
            logger.error(f"[MainScreen] Error in quick bookmark: {e}")
            self.show_error("Bookmark", e)

    def play_whole_folder(self):
        """round-60 (Bug 128): hold OK on any media file -> play the entire
        folder as a playlist (recursive=False: current folder only).
        Restores the 'Play ALL media in this folder' feature that round 57's
        direct-play change orphaned for videos."""
        try:
            sel = self.active_pane.getSelection()
            if not sel or not sel[0]:
                self.dialogs.show_message("Select a media file first", type="info")
                return
            path = sel[0]
            d = os.path.dirname(path)
            logger.info(f"[MainScreen] Folder play: {d}")
            from ..player.custom_media_player import playDirectory
            playDirectory(self.session, d)
        except Exception as e:
            logger.error(f"[MainScreen] Folder play failed: {e}")
            self.dialogs.show_message(f"Folder play failed:\n{e}", type="error")

    def preview_file(self):
        """Preview file contents"""
        try:
            sel = self.active_pane.getSelection()
            if not sel or not sel[0]:
                return
            
            file_path = sel[0]
            logger.debug(f"[MainScreen] Preview file request: {file_path}")
            
            if os.path.isdir(file_path):
                self.dialogs.show_message("Cannot preview directory!\n\nPress OK to enter folder.", type="info")
                return
            
            # Check file size
            try:
                size = self.file_ops.get_file_size(file_path)
                max_size = int(self.config.plugins.wgfilemanager.preview_size.value) * 1024
                if size > max_size:
                    self.dialogs.show_message(
                        f"File too large to preview!\n\nSize: {format_size(size)}\nLimit: {format_size(max_size)}",
                        type="info"
                    )
                    return
            except:
                pass
            
            # Delegate to dialogs
            self.dialogs.preview_file(file_path, self.file_ops, self.config)
            logger.debug(f"[MainScreen] Previewing file: {os.path.basename(file_path)}")
        except Exception as e:
            logger.error(f"[MainScreen] Error previewing file: {e}")
            self.show_error("Preview", e)

    def preview_media(self):
        """Preview media file - IMPROVED with subtitle support"""
        try:
            if self.preview_in_progress:
                self.dialogs.show_message("Media preview already in progress!", type="warning")
                return
            
            sel = self.active_pane.getSelection()
            if not sel or not sel[0]:
                return
            
            file_path = sel[0]
            logger.debug(f"[MainScreen] Preview media request: {file_path}")
            
            # Check if file can be played
            if not self.can_play_file(file_path):
                self.dialogs.show_message(
                    "Not a playable media file!\n\nSupported: MP4, MKV, AVI, TS, MP3, FLAC, etc.",
                    type="info"
                )
                return
            
            self.preview_in_progress = True
            
            # Check file type and show appropriate options
            ext = os.path.splitext(file_path)[1].lower()
            video_extensions = ['.mp4', '.mkv', '.avi', '.ts', '.m2ts', '.mov', '.m4v', '.mpg', '.mpeg', '.wmv', '.flv']
            
            if ext in video_extensions:
                # round-57 direct play: no more with/without-subs dialog -
                # play immediately; subtitles (if found) auto-load, toggle
                # with TEXT, pick with YELLOW inside the player.
                logger.debug(f"[MainScreen] Video file detected - direct play")
                self.play_media_file(file_path)
            else:
                # Audio or other files: Use existing method
                if self.config.plugins.wgfilemanager.use_internal_player.value:
                    try:
                        logger.debug(f"[MainScreen] Using internal player for: {file_path}")
                        self.play_media_file(file_path)
                    except Exception as e:
                        logger.error(f"[MainScreen] Internal player failed: {e}")
                        if self.config.plugins.wgfilemanager.fallback_to_external.value:
                            logger.debug(f"[MainScreen] Falling back to external player")
                            self.play_with_external_player(file_path)
                        else:
                            self.dialogs.show_message(f"Media playback failed:\n{e}", type="error")
                else:
                    logger.debug(f"[MainScreen] Using external player for: {file_path}")
                    self.play_with_external_player(file_path)
            
            self.preview_in_progress = False
            
        except Exception as e:
            logger.error(f"[MainScreen] Error previewing media: {e}")
            self.preview_in_progress = False
            self.show_error("Media preview", e)

    def can_play_file(self, path):
        """Check if file can be played"""
        if not os.path.exists(path):
            return False
        
        # Check file size
        try:
            size = os.path.getsize(path)
            if size == 0:
                return False
        except:
            return False
        
        # Check extension
        ext = os.path.splitext(path)[1].lower()
        supported = ['.mp4', '.mkv', '.avi', '.ts', '.m2ts', '.mp3', '.flac', '.wav', '.aac', '.ogg', '.m4a']
        return ext in supported

    def show_storage_quick_selector(self):
        """round-30 (Bug 88): INFO key - full storage picker (same as AUDIO).
        The old quick list showed only a subset; this shows EVERYTHING:
        internal HDD, USB devices, network mounts and the system root."""
        self.show_storage_selector()

    def show_storage_selector(self):
        """round-30 (Bug 88): full storage picker - ALL mounted storage
        (HDD, USB, network shares, system root) with free/total space."""
        try:
            entries = self._scan_storage_locations()
            if not entries:
                self.dialogs.show_message("No storage locations found", type="info")
                return
            choices = []
            for label, path, space in entries:
                text = "%s   %s" % (label, path)
                if space:
                    text += "   (%s)" % space
                choices.append((text, path))
            from Screens.ChoiceBox import ChoiceBox
            self.session.openWithCallback(
                self._storage_selected, ChoiceBox,
                title="Storage (%d locations)" % len(entries),
                list=choices)
            logger.info(f"[MainScreen] Storage selector: {len(entries)} locations")
        except Exception as e:
            logger.error(f"[MainScreen] Storage selector error: {e}")
            self.dialogs.show_message(f"Storage selector failed:\n{e}", type="error")

    def _storage_selected(self, choice):
        """round-30: jump the active pane to the chosen storage."""
        if not choice:
            return
        path = choice[1]
        try:
            logger.debug(f"[MainScreen] Storage selected: {path}")
            self.active_pane.changeDir(path)
            self.update_ui()
        except Exception as e:
            logger.error(f"[MainScreen] Cannot change to {path}: {e}")
            self.dialogs.show_message(f"Cannot open:\n{path}", type="error")

    def _scan_storage_locations(self):
        """round-30 (Bug 88): enumerate every storage location on the box.
        Sources, merged and de-duplicated:
          1. Enigma2's partition manager (device descriptions)
          2. /proc/mounts (catches USB sticks and network mounts - cifs/nfs -
             that the partition manager misses)
          3. Well-known locations (/media/hdd, /media/usb, /media/net...)
        Returns [(label, path, 'free / total'), ...] sorted HDD, USB, NET,
        other, system-root last."""
        from ..utils.formatters import format_size
        entries = {}

        def add(path, label):
            try:
                path = str(path).replace("\\040", " ").rstrip("/") or "/"
            except Exception:
                return
            if path in entries or not os.path.isdir(path):
                return
            space = ""
            try:
                st = os.statvfs(path)
                free = st.f_bavail * st.f_frsize
                total = st.f_blocks * st.f_frsize
                if total > 10 * 1024 * 1024:   # round-31 (Bug 91): hide silly
                                                # tmpfs/placeholder sizes (<10 MB)
                    space = "%s free / %s" % (format_size(free), format_size(total))
            except Exception:
                pass
            entries[path] = (label, path, space)

        # --- 1) Enigma2 partition manager ---
        try:
            from Components.Harddisk import harddiskmanager
            for part in harddiskmanager.getMountedPartitions():
                try:
                    mp = part.mountpoint
                    if callable(mp):
                        mp = mp()
                    if not mp:
                        continue
                    mp = str(mp)
                    kind = "HDD" if "hdd" in mp.lower() else ("USB" if "usb" in mp.lower() else "DISK")
                    desc = ""
                    try:
                        d = getattr(part, "description", "")
                        desc = d() if callable(d) else str(d or "")
                    except Exception:
                        pass
                    add(mp, "%s: %s" % (kind, desc or (os.path.basename(mp.rstrip("/")) or mp)))
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[MainScreen] harddiskmanager unavailable: {e}")

        # --- 2) /proc/mounts (USB + network mounts) ---
        SKIP_FS = ("proc", "sysfs", "devpts", "tmpfs", "devtmpfs", "squashfs",
                   "ramfs", "cgroup", "fusectl", "securityfs", "debugfs",
                   "pstore", "bpf", "tracefs", "configfs", "autofs", "overlay",
                   "ubifs", "mtd")
        NET_FS = ("cifs", "smb", "smb2", "smb3", "nfs", "nfs4")
        try:
            with open("/proc/mounts", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) < 3:
                        continue
                    dev, mp, fs = parts[0], parts[1], parts[2]
                    if fs in SKIP_FS or fs.startswith("fuse"):
                        continue
                    if not (mp.startswith("/media") or mp.startswith("/mnt") or mp == "/"):
                        continue
                    mp_u = mp.replace("\\040", " ")
                    if fs in NET_FS:
                        kind = "NET"
                        name = dev.replace("//", "").split("/")[-1] or dev
                    elif "hdd" in mp_u.lower():
                        kind = "HDD"          # round-32 (Bug 92): recognize the hard disk
                        name = os.path.basename(dev) or mp_u
                    elif "usb" in dev.lower() or "usb" in mp_u.lower():
                        kind = "USB"
                        name = os.path.basename(dev) or mp_u
                    elif mp_u == "/":
                        kind = "System"       # round-32: honest label, sorts last
                        name = "root"
                    else:
                        kind = "DISK"
                        name = os.path.basename(dev) or mp_u
                    add(mp_u, "%s: %s" % (kind, name))
        except Exception as e:
            logger.debug(f"[MainScreen] /proc/mounts unreadable: {e}")

        # --- 3) well-known locations ---
        for p, lbl in (("/media/hdd", "HDD: hard disk"),
                       ("/media/usb", "USB: usb device"),
                       ("/media/net", "NET: network shares"),
                       ("/media", "Media root"),
                       ("/", "System: root")):
            add(p, lbl)

        # --- 4) every immediate subdirectory of /media (round-31, Bug 91:
        # image-specific names - this box uses /media/network, not /media/net;
        # usb/network appear as autofs placeholders even when nothing is
        # mounted, and plugging a device later makes it appear automatically) ---
        try:
            for name in sorted(os.listdir("/media")):
                p = os.path.join("/media", name)
                if name == "autofs":
                    continue   # round-32 (Bug 92): automounter's internal dir - noise
                if os.path.isdir(p) and p not in entries:
                    if name.lower() in ("net", "network", "nfs"):
                        lbl = "NET: %s" % name
                    elif "usb" in name.lower():
                        lbl = "USB: %s" % name
                    else:
                        lbl = "MEDIA: %s" % name
                    add(p, lbl)
        except Exception as e:
            logger.debug(f"[MainScreen] /media enumeration failed: {e}")

        def prio(item):
            lbl = item[0]
            if lbl.startswith("HDD"):
                return 0
            if lbl.startswith("USB"):
                return 1
            if lbl.startswith("NET"):
                return 2
            if lbl.startswith("System"):
                return 9
            return 5

        return sorted(entries.values(), key=prio)

    def show_file_info(self):
        """Show detailed file information"""
        try:
            sel = self.active_pane.getSelection()
            if not sel or not sel[0]:
                return
            
            file_path = sel[0]
            logger.debug(f"[MainScreen] Showing file info for: {file_path}")
            
            info = self.file_ops.get_file_info(file_path)
            if info:
                text = f"File: {info['name']}\n"
                text += f"Path: {os.path.dirname(info['path'])}\n"
                text += f"Size: {info['size_formatted']}\n"
                text += f"Modified: {info['modified'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                text += f"Permissions: {info['permissions']}\n"
                
                if info['is_dir']:
                    text += f"Type: Directory\n"
                    if 'item_count' in info:
                        text += f"Items: {info['item_count']}\n"
                else:
                    text += f"Type: File\n"
                
                self.dialogs.show_message(text, type="info")
        except Exception as e:
            logger.error(f"[MainScreen] Error showing file info: {e}")
            self.show_error("File info", e)

    # Subtitle Methods
    def open_subtitle_settings(self, video_path=None):
        """round-24: the standalone subtitle-settings screen was removed
        together with the old subtitle engine. Subtitles are managed in
        the player (YELLOW / TEXT during playback)."""
        try:
            self.dialogs.show_message(
                "Subtitles are handled during playback:\n\n"
                "YELLOW - select subtitle (external + embedded)\n"
                "TEXT   - toggle subtitles on/off\n"
                "In the selection menu:\n"
                "YELLOW/BLUE - sync +/-100ms",
                type="info", timeout=6
            )
        except Exception as e:
            logger.debug(f"[MainScreen] subtitle info: {e}")

    def next_sort(self):
        """Cycle to next sort mode"""
        try:
            if self.active_pane == self["left_pane"]:
                modes = ["name", "size", "date", "type"]
                current_idx = modes.index(self.left_sort_mode) if self.left_sort_mode in modes else 0
                self.left_sort_mode = modes[(current_idx + 1) % len(modes)]
                self.config.plugins.wgfilemanager.left_sort_mode.value = self.left_sort_mode
                self.config.plugins.wgfilemanager.left_sort_mode.save()
                logger.debug(f"[MainScreen] Left sort mode changed to: {self.left_sort_mode}")
            else:
                modes = ["name", "size", "date", "type"]
                current_idx = modes.index(self.right_sort_mode) if self.right_sort_mode in modes else 0
                self.right_sort_mode = modes[(current_idx + 1) % len(modes)]
                self.config.plugins.wgfilemanager.right_sort_mode.value = self.right_sort_mode
                self.config.plugins.wgfilemanager.right_sort_mode.save()
                logger.debug(f"[MainScreen] Right sort mode changed to: {self.right_sort_mode}")
            
            self.apply_sorting()
            self.update_ui()
            self.dialogs.show_message(f"Sort: {self.left_sort_mode if self.active_pane == self['left_pane'] else self.right_sort_mode.upper()}", 
                                     type="info", timeout=1)
        except Exception as e:
            logger.error(f"[MainScreen] Error in next sort: {e}")

    def prev_sort(self):
        """Cycle to previous sort mode"""
        try:
            if self.active_pane == self["left_pane"]:
                modes = ["name", "size", "date", "type"]
                current_idx = modes.index(self.left_sort_mode) if self.left_sort_mode in modes else 0
                self.left_sort_mode = modes[(current_idx - 1) % len(modes)]
                self.config.plugins.wgfilemanager.left_sort_mode.value = self.left_sort_mode
                self.config.plugins.wgfilemanager.left_sort_mode.save()
                logger.debug(f"[MainScreen] Left sort mode changed to: {self.left_sort_mode}")
            else:
                modes = ["name", "size", "date", "type"]
                current_idx = modes.index(self.right_sort_mode) if self.right_sort_mode in modes else 0
                self.right_sort_mode = modes[(current_idx - 1) % len(modes)]
                self.config.plugins.wgfilemanager.right_sort_mode.value = self.right_sort_mode
                self.config.plugins.wgfilemanager.right_sort_mode.save()
                logger.debug(f"[MainScreen] Right sort mode changed to: {self.right_sort_mode}")
            
            self.apply_sorting()
            self.update_ui()
            self.dialogs.show_message(f"Sort: {self.left_sort_mode if self.active_pane == self['left_pane'] else self.right_sort_mode.upper()}", 
                                     type="info", timeout=1)
        except Exception as e:
            logger.error(f"[MainScreen] Error in prev sort: {e}")

    def apply_sorting(self):
        """Apply current sort mode to active pane"""
        try:
            items = self.active_pane.list
            if not items:
                return
            
            # Determine sort mode
            if self.active_pane == self["left_pane"]:
                current_sort = self.left_sort_mode
            else:
                current_sort = self.right_sort_mode
            
            logger.debug(f"[MainScreen] Applying {current_sort} sorting to active pane")
            
            # Sort based on mode
            if current_sort == "name":
                items.sort(key=lambda x: x[0][0].lower())
            elif current_sort == "size":
                items.sort(key=lambda x: self.file_ops.get_file_size(x[0][0]), reverse=True)
            elif current_sort == "date":
                items.sort(key=lambda x: os.path.getmtime(x[0][0]) if os.path.exists(x[0][0]) else 0, reverse=True)
            elif current_sort == "type":
                items.sort(key=lambda x: (not x[0][1], os.path.splitext(x[0][0])[1].lower()))
            
            # Apply show directories first
            if self.config.plugins.wgfilemanager.show_dirs_first.value == "yes":
                dirs = [item for item in items if item[0][1]]
                files = [item for item in items if not item[0][1]]
                items = dirs + files
            
            self.active_pane.list = items
            self.active_pane.l.setList(items)
            logger.debug(f"[MainScreen] Sorting applied. Total items: {len(items)}")
        except Exception as e:
            logger.error(f"[MainScreen] Sorting failed: {e}")

    def apply_show_dirs_first(self):
        """Apply show directories first setting"""
        try:
            items = self.active_pane.list
            if not items:
                return
            
            dirs = [item for item in items if item[0][1]]
            files = [item for item in items if not item[0][1]]
            
            self.active_pane.list = dirs + files
            self.active_pane.l.setList(self.active_pane.list)
            logger.debug(f"[MainScreen] Show dirs first applied. Dirs: {len(dirs)}, Files: {len(files)}")
        except Exception as e:
            logger.error(f"[MainScreen] Show dirs first failed: {e}")

    # System Methods
    def check_dependencies(self):
        """Check if required tools are available"""
        tools = {
            'rclone': 'Cloud sync',
            'zip': 'ZIP archives',
            'unzip': 'ZIP extraction',
            'tar': 'TAR archives',
            'cifs-utils': 'Network mounts',
            'smbclient': 'Network scanning',
            'curl': 'WebDAV support',
            'ftp': 'FTP client',
        }
        
        missing = []
        for tool, desc in tools.items():
            try:
                import subprocess
                result = subprocess.run(["which", tool], capture_output=True, timeout=2)
                if result.returncode != 0:
                    missing.append(f"{tool} ({desc})")
            except:
                missing.append(f"{tool} ({desc})")
        
        if missing:
            logger.warning(f"[MainScreen] Missing tools: {', '.join(missing)}")
        else:
            logger.debug("[MainScreen] All dependencies satisfied")

    def play_media_file(self, path):
        """Play media file with the AjPanel-style player.
        round-68: full-branch logging + traceback. Whatever fails, the
        diary now names file, line, and exception - no more invisible
        fallbacks."""
        import traceback as _tb
        logger.info("[MainScreen] play_media_file: %s", path)
        try:
            from ..player.custom_media_player import CustomMediaPlayer
            logger.info("[MainScreen] CustomMediaPlayer class imported OK")
        except Exception as e:
            logger.error("[MainScreen] IMPORT failed: %s\n%s", e, _tb.format_exc())
            self.play_with_external_player(path)
            return
        try:
            self.session.open(CustomMediaPlayer, filePath=path)
            logger.info("[MainScreen] CustomMediaPlayer opened for: %s", path)
        except Exception as e:
            logger.error("[MainScreen] OPEN failed: %s\n%s", e, _tb.format_exc())
            logger.warning("[MainScreen] falling back to external player")
            self.play_with_external_player(path)

    def play_with_external_player(self, path):
        """Play with an external player as fallback.
        round-8 fix pack: the old version ran this in a background thread
        and touched GUI dialogs from there, which can crash Enigma2.
        Popen does not block, so no thread is needed at all."""
        import subprocess

        players = [
            ['gst-launch-1.0', 'playbin', 'uri=file://' + path],
            ['ffplay', '-autoexit', '-nodisp', path],
            ['mplayer', '-quiet', path]
        ]

        for player_cmd in players:
            try:
                subprocess.Popen(player_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.dialogs.show_message(
                    f"Playing with external player:\n{os.path.basename(path)}",
                    type="info",
                    timeout=3
                )
                return
            except FileNotFoundError:
                continue

        self.dialogs.show_message(
            "No media player available!\n\nInstall: opkg install gstreamer1.0",
            type="error"
        )

    # Hotkey settings
    def open_hotkey_settings(self):
        """Open hotkey settings directly from HELP button"""
        try:
            from ..ui.hotkey_setup import HotkeySetupScreen
            logger.debug("[MainScreen] Opening hotkey settings")
            self.session.open(HotkeySetupScreen)
        except ImportError as e:
            logger.error(f"[MainScreen] Hotkey settings not available: {e}")
            self.dialogs.show_message(
                f"Hotkey settings not available!\n\nError: {e}\n"
                "Access via: MENU → Tools → Hotkey Settings",
                type="error",
                timeout=3
            )
        except Exception as e:
            logger.error(f"[MainScreen] Error opening hotkey settings: {e}")
            self.show_error("Hotkey settings", e)

    def show_error(self, context, error):
        """Show user-friendly error message with logging"""
        error_msg = str(error)
        logger.error(f"[MainScreen] Error in {context}: {error_msg}")
        
        if "Permission denied" in error_msg:
            user_msg = f"{context}: Permission denied. Check file permissions."
        elif "No space left" in error_msg:
            user_msg = f"{context}: Disk full. Free up space and try again."
        elif "No such file" in error_msg:
            user_msg = f"{context}: File not found. It may have been moved or deleted."
        elif "Device or resource busy" in error_msg:
            user_msg = f"{context}: Device busy. Try again later."
        else:
            user_msg = f"{context}: {error_msg[:100]}"
        
        self.dialogs.show_message(user_msg, type="error")

    def cleanup(self):
        """Clean up resources"""
        try:
            logger.debug("[MainScreen] Cleaning up resources")
            
            if self.operation_timer.isActive():
                self.operation_timer.stop()
            
            # Clear clipboard to free memory
            self.clipboard.clear()
            self.marked_files.clear()
            
            # Cancel any pending operations
            with self.operation_lock:
                self.operation_in_progress = False
            
            logger.info("[MainScreen] Cleanup completed")
        except Exception as e:
            logger.error(f"[MainScreen] Cleanup error: {e}")

    def close(self):
        """Handle exit and save paths if configured - SINGLE UNIFIED CLOSE METHOD"""
        try:
            logger.info("[MainScreen] Closing WGFileManager")
            
            # Clean up resources
            self.cleanup()
            
            from Components.config import config
            p = config.plugins.wgfilemanager
            
            # Save current paths if enabled
            if p.save_left_on_exit.value == "yes":
                if hasattr(self, 'left_pane'):
                    current_left = self["left_pane"].getCurrentDirectory()
                    if current_left:
                        p.left_path.value = current_left
                        p.left_path.save()
                        logger.debug(f"[MainScreen] Saved left path: {current_left}")
            
            if p.save_right_on_exit.value == "yes":
                if hasattr(self, 'right_pane'):
                    current_right = self["right_pane"].getCurrentDirectory()
                    if current_right:
                        p.right_path.value = current_right
                        p.right_path.save()
                        logger.debug(f"[MainScreen] Saved right path: {current_right}")
            
            # Commit to /etc/enigma2/settings
            configfile.save()
            
            logger.info("[MainScreen] WGFileManager: Paths saved on exit.")
            
        except Exception as e:
            logger.error(f"[MainScreen] Error during shutdown: {e}")
        
        # IMPORTANT: Always call parent Screen.close() at the end
        Screen.close(self)

    def exit(self):
        """Handle exit request - redirects to close()"""
        logger.debug("[MainScreen] Exit requested")
        self.close()

    def close_plugin(self):
        """Plugin shutdown - redirects to close()"""
        logger.debug("[MainScreen] Plugin shutdown requested")
        if self.operation_in_progress:
            self.dialogs.show_message("Operation in progress!\n\nPlease wait...", type="warning")
            return
        self.close()

    def createSummary(self):
        """Create summary screen to avoid skin errors"""
        return None
    
    def getSummaryText(self):
        """Return summary text to avoid skin errors"""
        return "WGFileManager File Manager"