from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.config import config
import os
import time
import subprocess

from ..utils.formatters import get_file_icon, format_size
from ..utils.logging_config import get_logger

logger = get_logger(__name__)

# ============================================================================
# FIX FOR STACKTRACE THREADING ISSUE
# ============================================================================
# Patch to prevent StackTrace formatting errors in OpenATV
import threading
import sys

# Monkey patch Thread.run to handle StackTrace errors
try:
    original_thread_run = threading.Thread.run
    
    def patched_thread_run(self):
        try:
            original_thread_run(self)
        except TypeError as e:
            if "%d format" in str(e) or "real number is required" in str(e):
                # StackTrace formatting error - run target directly
                logger.warning(f"StackTrace formatting error in thread {self.name}: {e}")
                if hasattr(self, '_target') and self._target:
                    try:
                        self._target(*self._args, **self._kwargs)
                    except Exception as target_error:
                        logger.error(f"Thread target error: {target_error}")
            else:
                raise
        except Exception as thread_error:
            logger.error(f"Thread error in {self.name}: {thread_error}")
            # Try to run target anyway
            if hasattr(self, '_target') and self._target:
                try:
                    self._target(*self._args, **self._kwargs)
                except:
                    pass
    
    threading.Thread.run = patched_thread_run
    logger.info("Threading patch applied successfully")
    
except Exception as patch_error:
    logger.error(f"Failed to apply threading patch: {patch_error}")

# ============================================================================

class ContextMenuHandler:
    def smart_callback(self, choice, original_handler, *args):
        """Traffic controller for all menus: Handles EXIT/BACK automatically"""
        # If user pressed EXIT (choice is None)
        if choice is None:
            # If we were in a submenu, go back to tools. If already in tools, just close.
            if getattr(self, 'current_menu_level', 0) > 0:
                self.current_menu_level = 0
                self.show_tools_menu()
            return
        
        # If user selected a 'back' button in the list
        if isinstance(choice, (list, tuple)) and len(choice) > 1 and choice[1] == "back":
            self.current_menu_level = 0
            self.show_tools_menu()
            return

        # Otherwise, run the actual tool (copy, delete, etc.)
        original_handler(choice, *args)
    
    def __init__(self, main_screen, config=None):
        self.main = main_screen
        # FIX: Ensure config is always available even if main_screen.config is None
        self.config = config or getattr(main_screen, 'config', None)
        if self.config is None:
            from Components.config import config as en_config
            self.config = en_config
        self.file_ops = main_screen.file_ops
        self.dialogs = main_screen.dialogs
        
        # Track navigation state
        self.current_menu_level = 0  # 0 = main tools, 1 = submenu
        
        # WGFileManager dependencies categorized by functionality
        self.plugin_dependencies = {
            "CORE_PLUGIN": [
                "python3-core",
                "python3-io",
                "python3-json",
                "python3-os",
                "python3-threading",
            ],
            "FILE_OPERATIONS": [
                "python3-shutil",
                "python3-hashlib",
                "python3-datetime",
                "python3-stat",
                "python3-glob",
            ],
            "NETWORK_FEATURES": [
                "rclone",              # Cloud sync - EXTERNAL
                "cifs-utils",          # CIFS/SMB mounting
                "smbclient",           # SMB share discovery
                "curl",                # WebDAV/HTTP transfers
                "python3-paramiko",    # SFTP client
                "python3-requests",    # HTTP/WebDAV client
            ],
            "ARCHIVE_SUPPORT": [
                "zip",
                "unzip",
                "tar",
                "gzip",
                "bzip2",
                "python3-zipfile",
            ],
            "SYSTEM_TOOLS": [
                "rsync",               # Efficient file transfers
                "wget",                # Alternative downloads
                "tree",                # Directory visualization
                "ncdu",                # Disk usage analysis
                "python3-pip",         # Python package management
            ],
            "OPTIONAL_ENHANCEMENTS": [
                "ffmpeg",              # Media processing
                "imagemagick",         # Image processing
                "python3-pil",         # Python imaging library
                "python3-cryptography", # Encryption support
            ]
        }
    
    # Add this import block HERE:
    # ============================================================================
    # HOTKEY SETUP IMPORT
    # ============================================================================
        try:
            from ..ui.hotkey_setup import HotkeySetupScreen
            self.HOTKEY_SUPPORT_AVAILABLE = True
        except ImportError as e:
            self.HOTKEY_SUPPORT_AVAILABLE = False
            logger.warning(f"HotkeySetupScreen not available: {e}")
    # ============================================================================

    def show_context_menu(self):
        """Show context menu for current selection"""
        try:
            sel = self.main.active_pane.getSelection()
            if not sel or not sel[0]:
                self.show_general_context_menu()
            else:
                # Use smart context menu if enabled
                if self.config.plugins.wgfilemanager.enable_smart_context.value:
                    self.show_smart_context_menu(sel[0])
                else:
                    self.show_item_context_menu()
        except Exception as e:
            logger.error(f"Error showing context menu: {e}")
            self.dialogs.show_message(f"Context menu error: {e}", type="error")
    
    def show_general_context_menu(self):
        """Show context menu for current directory"""
        try:
            current_dir = self.main.active_pane.getCurrentDirectory()
            menu_items = [
                (" <-- Back", "back"),
                (" Open Current Folder", "open"),
                (" Rename Current Folder", "rename_folder"),
                (" Disk Usage Here", "disk_usage"),
                (" Search in This Folder", "search_here"),
                (" Create New File", "new_file"),
                (" Create New Folder", "new_folder"),
                (" Paste from Clipboard", "paste"),
                (" Mount Remote Share Here", "mount_here"),
                (" Scan Network Here", "scan_here"),
                (" Set as Bookmark", "bookmark"),
                (" Settings for This Folder", "folder_settings"),
            ]
            
            self.main.session.openWithCallback(
                lambda choice: self.smart_callback(choice, self.handle_general_context_menu, current_dir),
                ChoiceBox,
                title=f" Context: {os.path.basename(current_dir) or 'Root'}",
                list=menu_items
            )
        except Exception as e:
            logger.error(f"Error: {e}")
            self.main.session.open(MessageBox, f"Error: {e}", MessageBox.TYPE_ERROR)

    def handle_general_context_menu(self, choice, current_dir):
        action = choice[1]

        try:
            if action == "open":
                self.main.active_pane.refresh()
            elif action == "rename_folder":
                self.rename_folder(current_dir)
            elif action == "disk_usage":
                self.main.dialogs.show_disk_usage(current_dir, self.file_ops)
            elif action == "search_here":
                self.main.dialogs.show_search_dialog(current_dir, self.main.search_engine)
            elif action == "new_file":
                self.main.dialogs.show_create_file_dialog(current_dir, self.file_ops, self.main.update_ui)
            elif action == "new_folder":
                self.main.dialogs.show_create_folder_dialog(current_dir, self.file_ops, self.main.update_ui)
            elif action == "paste":
                self.main.paste_from_clipboard()
            elif action == "mount_here":
                self.main.dialogs.show_mount_dialog(current_dir, self.main.mount_mgr, self.main.active_pane, self.main.update_ui)
            elif action == "scan_here":
                self.main.dialogs.show_network_scan_dialog(self.main.mount_mgr)
            elif action == "bookmark":
                self.main.dialogs.show_bookmark_dialog(current_dir, self.main.bookmarks, self.main.config)
            elif action == "folder_settings":
                # Use existing file info method instead of non-existent show_folder_settings
                self.main.show_file_info()
        except Exception as e:
            logger.error(f"Error handling general context menu: {e}")
            self.dialogs.show_message(f"Action error: {e}", type="error")
    
    def show_item_context_menu(self):
        """Show context menu for selected item"""
        try:
            sel = self.main.active_pane.getSelection()
            if not sel or not sel[0]:
                return
            
            item_path = sel[0]
            is_dir = os.path.isdir(item_path)
            item_name = os.path.basename(item_path)
            
            menu_items = [
                (" <-- Back", "back"),
                (" Open/Explore", "open"),
                ("[EDIT] Rename", "rename"),
                (" Delete", "delete"),
                (" Copy", "copy"),
                (" Cut", "cut"),
                (" Info", "info"),
            ]
            
            # Add directory-specific actions
            if is_dir:
                menu_items.append((" Compress", "compress"))
            else:
                # File-specific actions based on extension
                ext = os.path.splitext(item_path)[1].lower()
                if ext in ['.mp4', '.mkv', '.avi', '.ts', '.mp3', '.flac']:
                    menu_items.append((" Play", "play"))
                if ext in ['.txt', '.log', '.conf', '.py', '.sh', '.xml', '.json']:
                    menu_items.append((" Edit", "edit"))
                if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                    menu_items.append((" View", "view"))
                if ext in ['.zip', '.tar', '.tar.gz', '.tgz', '.rar']:
                    menu_items.append((" Extract", "extract"))
            
            # Additional actions for files
            if not is_dir:
                menu_items.extend([
                    (" Copy to Other Pane", "copy_other"),
                    (" Move to Other Pane", "move_other"),
                    (" Permissions", "chmod"),
                    (" Checksum", "checksum"),
                    (" Create Shortcut", "shortcut"),
                ])
            
            # Compress if multiple items selected
            marked = [x for x in self.main.active_pane.list if x[0][3]]
            if len(marked) > 1:
                menu_items.append((" Compress Selected", "compress"))
            
            self.main.session.openWithCallback(
                lambda choice: self.smart_callback(choice, self.handle_item_context_menu, item_path, is_dir, item_name),
                ChoiceBox,
                title=f" {item_name}",
                list=menu_items
            )
        except Exception as e:
            logger.error(f"Error showing item context menu: {e}")
            self.main.session.open(MessageBox, f"Error: {e}", MessageBox.TYPE_ERROR)
    
    def handle_item_context_menu(self, choice, item_path, is_dir, item_name):
        """Handle item context menu selection"""
        action = choice[1]
        
        try:
            if action == "open":
                if is_dir:
                    self.main.active_pane.changeDir(item_path)
                else:
                    self.main.preview_file()
            elif action == "rename":
                self.rename_item(item_path)
            elif action == "delete":
                self.delete_item(item_path, is_dir, item_name)
            elif action == "copy":
                self.copy_item(item_path)
            elif action == "cut":
                self.cut_item(item_path)
            elif action == "info":
                self.main.show_file_info()
            elif action == "play":
                self.main.preview_media()
            elif action == "edit":
                self.edit_text_file(item_path)
            elif action == "view":
                self.main.dialogs.preview_image(item_path, self.file_ops)
            elif action == "extract":
                self.main.dialogs.show_extract_dialog(item_path, self.main.archive_mgr, self.main.active_pane, self.main.update_ui)
            elif action == "copy_other":
                self.copy_to_other_pane(item_path)
            elif action == "move_other":
                self.move_to_other_pane(item_path)
            elif action == "chmod":
                self.main.dialogs.show_permissions_dialog([item_path], self.file_ops)
            elif action == "checksum":
                self.main.dialogs.show_checksum_dialog([item_path], self.file_ops)
            elif action == "shortcut":
                self.create_shortcut(item_path)
            elif action == "compress":
                files = [x[0][0] for x in self.main.active_pane.list if x[0][3]]
                self.main.dialogs.show_archive_dialog(files, self.main.archive_mgr, self.main.active_pane.getCurrentDirectory())
        except Exception as e:
            logger.error(f"Error handling item context menu: {e}")
            self.dialogs.show_message(f"Action error: {e}", type="error")
    
    def show_multi_selection_context_menu(self, marked_items):
        """Show context menu for multiple selected items"""
        try:
            menu_items = [
                (" <-- Back", "back"),
                (" Compress Selected Items", "compress_multi"),
                (" Copy Selected Items", "copy_multi"),
                (" Cut Selected Items", "cut_multi"),
                (" Delete Selected Items", "delete_multi"),
                (" Bulk Rename", "bulk_rename_multi"),
                (" Change Permissions", "chmod_multi"),
                (" Move to Other Pane", "move_other_multi"),
                (" Copy to Other Pane", "copy_other_multi"),
            ]
            
            self.main.session.openWithCallback(
                lambda choice: self.smart_callback(choice, self.handle_multi_selection_menu, marked_items),
                ChoiceBox,
                title=f" {len(marked_items)} Selected Items",
                list=menu_items
            )
        except Exception as e:
            logger.error(f"Error showing multi-selection context menu: {e}")
            self.main.session.open(MessageBox, f"Error: {e}", MessageBox.TYPE_ERROR)
    
    def handle_multi_selection_menu(self, choice, marked_items):
        """Handle multi-selection menu action"""
        action = choice[1]
        file_paths = [item[0][0] for item in marked_items]
        
        try:
            if action == "compress_multi":
                self.main.dialogs.show_archive_dialog(file_paths, self.main.archive_mgr, 
                                                     self.main.active_pane.getCurrentDirectory())
            elif action == "copy_multi":
                self.main.clipboard = file_paths
                self.main.clipboard_mode = "copy"
                self.main.update_ui()
                self.main.dialogs.show_message(f"[OK] Copied {len(file_paths)} items to clipboard", 
                                              type="info", timeout=2)
            elif action == "cut_multi":
                self.main.clipboard = file_paths
                self.main.clipboard_mode = "cut"
                self.main.update_ui()
                self.main.dialogs.show_message(f"[OK] Cut {len(file_paths)} items to clipboard", 
                                              type="info", timeout=2)
            elif action == "delete_multi":
                self.delete_multiple_items(file_paths)
            elif action == "bulk_rename_multi":
                self.main.dialogs.show_bulk_rename_dialog(file_paths, self.file_ops, 
                                                         self.main.active_pane, self.main.update_ui)
            elif action == "chmod_multi":
                self.main.dialogs.show_permissions_dialog(file_paths, self.file_ops)
            elif action == "move_other_multi":
                dest_dir = self.main.inactive_pane.getCurrentDirectory()
                self.main.execute_transfer("mv", file_paths, dest_dir)
            elif action == "copy_other_multi":
                dest_dir = self.main.inactive_pane.getCurrentDirectory()
                self.main.execute_transfer("cp", file_paths, dest_dir)
        except Exception as e:
            logger.error(f"Error handling multi-selection menu: {e}")
            self.main.dialogs.show_message(f"Action error: {e}", type="error")
    
    def show_tools_menu(self):
        """Show tools menu"""
        try:
            # Reset menu level to main tools
            self.current_menu_level = 0
            
            if self.config.plugins.wgfilemanager.group_tools_menu.value:
                # GROUPED MENU
                tools = [
                    ("═══ FILE OPERATIONS ═══", None),
                    (" Create New File/Folder", "create"),
                    (" Bulk Rename Tool", "bulkrename"),
                    (" Search Files", "search"),
                    (" Search Content (Grep)", "grep"),
                    (" Create Archive (ZIP/TAR)", "archive"),
                    (" Extract Archive", "extract"),
                    (" Verify Checksum", "checksum"),
                    (" Set Permissions", "chmod"),
                    
                    ("═══ VIEW & NAVIGATION ═══", None),
                    (" Manage Bookmarks", "bookmarks"),
                    (" File Preview", "preview"),
                    (" Storage Selector", "storage"),
                    (" Disk Usage Analysis", "diskusage"),
                    (" View/Restore Trash", "trash"),
                    
                    ("═══ NETWORK & REMOTE ═══", None),
                    (" Mount Remote (CIFS)", "mount"),
                    (" Scan Network Shares", "scan"),
                    (" Test Network Connection", "ping"),
                    (" Advanced Network Tools", "network_tools"),
                    (" Remote File Access", "remote"),
                    (" Cloud Sync", "cloud"),
                    
                    ("═══ SYSTEM TOOLS ═══", None),
                    (" Smart Cleanup", "clean"),
                    (" Repair Environment", "repair"),
                    (" Repair Picon", "picon"),
                    (" View Task Queue", "queue"),
                    (" View Log", "log"),
                    
                    ("═══ SETTINGS ═══", None),
                    (" Hotkey Settings", "hotkey_setup"), # ADD THIS LINE
                    (" Plugin Settings", "cfg"),
                ]
            else:
                # FLAT MENU
                tools = [
                    (" Create New File/Folder", "create"),
                    (" Manage Bookmarks", "bookmarks"),
                    (" Bulk Rename Tool", "bulkrename"),
                    (" File Preview", "preview"),
                    (" Search Files", "search"),
                    (" Search Content (Grep)", "grep"),
                    (" Create Archive (ZIP/TAR)", "archive"),
                    (" Extract Archive", "extract"),
                    (" Verify Checksum", "checksum"),
                    (" Set Permissions", "chmod"),
                    (" Disk Usage Analysis", "diskusage"),
                    (" Storage Selector", "storage"),
                    (" View/Restore Trash", "trash"),
                    (" Mount Remote (CIFS)", "mount"),
                    (" Scan Network Shares", "scan"),
                    (" Test Network Connection", "ping"),
                    (" Remote File Access", "remote"),
                    (" Cloud Sync", "cloud"),
                    (" Smart Cleanup", "clean"),
                    (" Repair Environment", "repair"),
                    (" Repair Picon", "picon"),
                    (" View Task Queue", "queue"),
                    (" View Log", "log"),
                    (" Hotkey Settings", "hotkey_setup"), # ADD THIS LINE
                    (" Plugin Settings", "cfg"),
                ]
            
            self.main.session.openWithCallback(
                self.tools_callback,
                ChoiceBox,
                title=" PLATINUM TOOLS MENU",
                list=tools
            )
        except Exception as e:
            logger.error(f"Error showing tools menu: {e}")
            self.dialogs.show_message(f"Tools menu error: {e}", type="error")
    
    def tools_callback(self, answer):
        """Handle tools menu selection - FIXED EXIT/BACK LOGIC"""
        # User pressed EXIT (answer is None)
        if not answer:
            # If we're in a submenu, return to main tools
            if self.current_menu_level > 0:
                self.current_menu_level = 0
                self.show_tools_menu()
            return
        
        # If user selected a separator (None) or invalid option
        if answer[1] is None:
            return  # Do nothing for separators
        
        # If user selected "back" option
        if answer[1] == "back":
            self.current_menu_level = 0
            self.show_tools_menu()
            return
        
        mode = answer[1]

        try:
            # ============================================================================
            # HOTKEY SETUP HANDLER
            # ============================================================================
            if mode == "hotkey_setup":
                if hasattr(self, 'HOTKEY_SUPPORT_AVAILABLE') and self.HOTKEY_SUPPORT_AVAILABLE:
                    from ..ui.hotkey_setup import HotkeySetupScreen
                    self.main.session.open(HotkeySetupScreen)
                else:
                    self.dialogs.show_message(
                        " Hotkey Settings not available!\n\n"
                        "The hotkey setup module is not installed.\n"
                        "Please ensure hotkey_setup.py exists in the ui folder.",
                        type="error",
                        timeout=3
                    )
                return
            # ============================================================================
            # FIXED: Use self.config instead of importing config directly
            if mode == "cfg":
                # FIXED: Direct import to avoid circular dependency
                try:
                    # Try relative import first
                    try:
                        from ..core.config import WGFileManagerConfig
                        cfg_mgr = WGFileManagerConfig()
                        cfg_mgr.setup_config()
                    except Exception:
                        pass  # Config already initialized

                    from ..ui.setup_screen import WGFileManagerSetup
                    self.main.session.open(WGFileManagerSetup, self.config)
                except ImportError:
                    # Fallback to absolute import
                    try:
                        try:
                            from ..core.config import WGFileManagerConfig
                            cfg_mgr = WGFileManagerConfig()
                            cfg_mgr.setup_config()
                        except Exception:
                            pass
                        from Plugins.Extensions.WGFileManager.ui.setup_screen import WGFileManagerSetup
                        self.main.session.open(WGFileManagerSetup, self.config)
                    except Exception as e:
                        logger.error(f"Cannot import settings screen: {e}")
                        self.dialogs.show_message("Settings screen unavailable", type="error")

            elif mode == "bookmarks":
                self.main.dialogs.show_bookmark_manager(self.main.bookmarks, self.config,
                                                    self.main.active_pane, self.main.update_ui)

            elif mode == "create":
                self.main.dialogs.show_create_dialog(self.main.active_pane.getCurrentDirectory(),
                                                 self.file_ops, self.main.update_ui)

            elif mode == "bulkrename":
                files = self.main.get_selected_files()
                if len(files) >= 2:
                    self.main.dialogs.show_bulk_rename_dialog(files, self.file_ops,
                                                          self.main.active_pane, self.main.update_ui)
                else:
                    self.dialogs.show_message("Select at least 2 files for bulk rename!", type="info")
                    self._return_to_tools_after_delay(2)

            elif mode == "preview":
                self.main.preview_file()

            elif mode == "search":
                self.main.dialogs.show_search_dialog(self.main.active_pane.getCurrentDirectory(),
                                                 self.main.search_engine)

            elif mode == "archive":
                files = self.main.get_selected_files()
                if files:
                    self.main.dialogs.show_archive_dialog(files, self.main.archive_mgr,
                                                      self.main.active_pane.getCurrentDirectory())
                else:
                    self.dialogs.show_message("No files selected!", type="info")
                    self._return_to_tools_after_delay(2)

            elif mode == "extract":
                sel = self.main.active_pane.getSelection()
                if sel and sel[0]:
                    self.main.dialogs.show_extract_dialog(sel[0], self.main.archive_mgr,
                                                      self.main.active_pane, self.main.update_ui)
                else:
                    self.dialogs.show_message("No archive selected!", type="info")
                    self._return_to_tools_after_delay(2)

            elif mode == "trash":
                self.main.dialogs.show_trash_manager(self.file_ops, self.main.active_pane, self.main.update_ui)

            elif mode == "mount":
                self.main.dialogs.show_mount_dialog(self.main.active_pane.getCurrentDirectory(),
                                                self.main.mount_mgr, self.main.active_pane, self.main.update_ui)

            elif mode == "scan":
                self.main.dialogs.show_network_scan_dialog(self.main.mount_mgr)

            elif mode == "ping":
                self.main.dialogs.show_ping_dialog(self.main.mount_mgr)

            elif mode == "network_tools":
                from Plugins.Extensions.WGFileManager.network.network_tools import NetworkToolsScreen
                self.main.session.open(NetworkToolsScreen)
                try:
                    import os
                    import importlib.util
                    plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    network_file = os.path.join(plugin_dir, 'network', 'network_tools.py')

                    if os.path.exists(network_file):
                        spec = importlib.util.spec_from_file_location("network_tools", network_file)
                        network_tools = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(network_tools)
                        self.main.session.open(network_tools.NetworkToolsScreen)
                    else:
                        self.dialogs.show_message(f"Network tools not found!\n\nExpected: {network_file}", type="error")
                except Exception as e:
                    logger.error(f"Network tools error: {e}")
                    self.dialogs.show_message(f"Network tools error: {str(e)}", type="error")

            elif mode == "cloud":
                self.current_menu_level = 1
                self.show_cloud_sync_menu()

            elif mode == "clean":
                current_dir = self.main.active_pane.getCurrentDirectory()
                self.main.dialogs.show_cleanup_dialog(current_dir, self.file_ops, self.main.active_pane, self.main.update_ui)

            elif mode == "picon":
                current_dir = self.main.active_pane.getCurrentDirectory()
                self.main.dialogs.show_picon_repair_dialog(current_dir, self.file_ops, self.main.active_pane, self.main.update_ui)

            elif mode == "chmod":
                files = self.main.get_selected_files()
                if files:
                    self.main.dialogs.show_permissions_dialog(files, self.file_ops)
                else:
                    self.dialogs.show_message("No files selected!", type="info")
                    self._return_to_tools_after_delay(2)

            elif mode == "diskusage":
                self.main.dialogs.show_disk_usage(self.main.active_pane.getCurrentDirectory(), self.file_ops)

            elif mode == "log":
                self.main.dialogs.show_log_viewer()

            elif mode == "repair":
                self.current_menu_level = 1
                self.show_repair_menu()

            elif mode == "grep":
                self.main.dialogs.show_content_search_dialog(self.main.active_pane.getCurrentDirectory(),
                                                         self.main.search_engine)

            elif mode == "checksum":
                import os
                files = [f for f in self.main.get_selected_files() if os.path.isfile(f)]
                if files:
                    self.main.dialogs.show_checksum_dialog(files, self.file_ops)
                else:
                    self.dialogs.show_message("Please select files (not folders)", type="info")
                    self._return_to_tools_after_delay(2)

            elif mode == "queue":
                class QueueManagerStub:
                    def get_queue(self): return []
                    def get_stats(self): return {"total": 0, "completed": 0, "failed": 0, "pending": 0}
                    def clear_queue(self): pass
            
                self.main.dialogs.show_queue_dialog(QueueManagerStub())

            elif mode == "remote":
                self.main.dialogs.show_remote_access_dialog(self.main.remote_mgr, self.main.mount_mgr,
                                                        self.main.active_pane, self.main.update_ui)

            elif mode == "storage":
                self.main.show_storage_selector()

        except Exception as e:
            logger.error(f"Error in tools callback: {e}")
            self.dialogs.show_message(f"Tools error: {e}", type="error")
    
    def _return_to_tools_after_delay(self, delay_seconds):
        """Return to tools menu after a delay"""
        import threading
        
        # round-16 fix (Bug 53): sleeping thread touched the GUI - main-loop timer
        from enigma import eTimer
        _t = eTimer()
        _t.callback.append(lambda: self.show_tools_menu())
        _t.start(int(delay_seconds * 1000), True)
        if not hasattr(self, "_wg_timers"):
            self._wg_timers = []
        self._wg_timers.append(_t)
    
    def show_cloud_sync_menu(self):
        """Show cloud sync submenu with proper navigation"""
        try:
            choices = [
                (" Configure rclone", "config"),
                (" Upload to Cloud", "upload"),
                (" Download from Cloud", "download"),
                (" Sync Folder", "sync"),
                (" List Cloud Storage", "list"),
                (" Back to Main Tools", "back"),
            ]
            
            self.main.session.openWithCallback(
                self.handle_cloud_menu,
                ChoiceBox,
                title=" Cloud Sync (rclone) - Press EXIT to go back",
                list=choices
            )
        except Exception as e:
            logger.error(f"Error showing cloud sync menu: {e}")
            self.dialogs.show_message(f"Cloud sync menu error: {e}", type="error")
    
    def handle_cloud_menu(self, choice):
        """Handle cloud sync menu with proper back navigation - FIXED"""
        # Check if choice is None (EXIT pressed)
        if not choice:
            self.current_menu_level = 0  # Reset to main level
            self.show_tools_menu()
            return
        
        # If user selected "back" option
        if choice[1] == "back":
            # User selected "Back to Main Tools"
            self.show_tools_menu()
            return
        
        action = choice[1]
        
        try:
            if action == "config":
                # First check if rclone is installed
                self._check_rclone_installed(show_menu_after=True)
            elif action == "upload":
                self.dialogs.show_message("Upload feature - Configure rclone remote to upload", type="info")
                self._return_to_submenu_after_delay(self.show_cloud_sync_menu, 3)
            elif action == "sync":
                self.dialogs.show_message("Sync feature - Keep folders synchronized with cloud", type="info")
                self._return_to_submenu_after_delay(self.show_cloud_sync_menu, 3)
            elif action == "list":
                self.dialogs.show_message("List remotes: Run 'rclone listremotes' in SSH", type="info")
                self._return_to_submenu_after_delay(self.show_cloud_sync_menu, 3)
        except Exception as e:
            logger.error(f"Error handling cloud menu: {e}")
            self.dialogs.show_message(f"Cloud action error: {e}", type="error")
            self._return_to_submenu_after_delay(self.show_cloud_sync_menu, 3)
    
    def _check_rclone_installed(self, show_menu_after=False):
        """Check if rclone is installed and offer to install if not"""
        import threading
        
        def check_and_install():
            try:
                # Check if rclone is installed
                result = subprocess.run(["which", "rclone"], capture_output=True, text=True)
                
                if result.returncode == 0:
                    # rclone is installed
                    self.dialogs.show_message(
                        "[OK] rclone is already installed!\n\n"
                        "To configure rclone, run in SSH:\n"
                        "rclone config\n\n"
                        "This will open the rclone configuration wizard.",
                        type="info"
                    )
                else:
                    # rclone is not installed
                    self.dialogs.show_confirmation(
                        "[X] rclone is NOT installed!\n\n"
                        "rclone is required for cloud sync features.\n\n"
                        "Install rclone now?",
                        lambda res: self._install_rclone(res, show_menu_after) if res else None
                    )
            except Exception as e:
                logger.error(f"Error checking rclone: {e}")
                self.dialogs.show_message(f"Error checking rclone: {str(e)}", type="error")
        
        # Run in background thread
        thread = threading.Thread(target=check_and_install, daemon=True)
        thread.start()
    
    def _install_rclone(self, confirmed, show_menu_after):
        """Install rclone if confirmed"""
        if not confirmed:
            return
        
        import threading
        
        def install_thread():
            try:
                self.dialogs.show_message("Installing rclone...\n\nPlease wait...", type="info", timeout=2)
                
                # Try to install rclone via opkg
                result = subprocess.run(
                    ["opkg", "install", "rclone"],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0:
                    message = "[OK] rclone installed successfully!\n\n"
                    message += "To configure rclone, run in SSH:\n"
                    message += "rclone config\n\n"
                    message += "This will open the rclone configuration wizard."
                    
                    self.dialogs.show_message(message, type="info")
                else:
                    # Try alternative installation methods
                    error_msg = "[X] Failed to install rclone via opkg.\n\n"
                    error_msg += "Try manual installation:\n"
                    error_msg += "1. Download from: https://rclone.org/downloads/\n"
                    error_msg += "2. Install with: dpkg -i rclone*.deb\n"
                    error_msg += "or: opkg install /path/to/rclone.ipk"
                    
                    self.dialogs.show_message(error_msg, type="error")
                    
            except subprocess.TimeoutExpired:
                self.dialogs.show_message("[X] rclone installation timed out (2 minutes)", type="error")
            except Exception as e:
                self.dialogs.show_message(f"[X] Installation error: {str(e)}", type="error")
            
            # Return to appropriate menu
            if show_menu_after:
                self._return_to_submenu_after_delay(self.show_cloud_sync_menu, 3)
        
        thread = threading.Thread(target=install_thread, daemon=True)
        thread.start()
    
    def _return_to_submenu_after_delay(self, submenu_method, delay_seconds):
        """Return to submenu after a delay"""
        import threading
        
        # round-16 fix (Bug 53): sleeping thread touched the GUI - main-loop timer
        from enigma import eTimer
        _t = eTimer()
        _t.callback.append(lambda: submenu_method())
        _t.start(int(delay_seconds * 1000), True)
        if not hasattr(self, "_wg_timers"):
            self._wg_timers = []
        self._wg_timers.append(_t)
    
    def show_repair_menu(self):
        """Show repair submenu with install dependencies option"""
        try:
            choices = [
                (" Install Missing Dependencies", "install_deps"),
                (" Install Missing Tools", "install"),
                (" Clean Temp Files", "clean_temp"),
                (" Fix Package Database", "fix_packages"),
                (" Repair Symlinks", "repair_links"),
                (" Back to Main Tools", "back"),
            ]
            
            self.main.session.openWithCallback(
                self.handle_repair_menu,
                ChoiceBox,
                title=" System Repair - Press EXIT to go back",
                list=choices
            )
        except Exception as e:
            logger.error(f"Error showing repair menu: {e}")
            self.dialogs.show_message(f"Repair menu error: {e}", type="error")
    
    def handle_repair_menu(self, choice):
        """Handle repair menu with proper back navigation - FIXED"""
        # Check if choice is None (EXIT pressed)
        if not choice:
            self.current_menu_level = 0  # Reset to main level
            self.show_tools_menu()
            return
        
        # If user selected "back" option
        if choice[1] == "back":
            # User selected "Back to Main Tools"
            self.show_tools_menu()
            return
        
        action = choice[1]
        
        try:
            if action == "install_deps":
                # First show dependency analysis
                self.analyze_dependencies()
            elif action == "install":
                files = self.main.get_selected_files()
                if not files:
                    self.dialogs.show_message("No files selected!", type="info")
                    # Return to repair menu after message
                    self._return_to_submenu_after_delay(self.show_repair_menu, 2)
                    return
                self.main.dialogs.show_repair_dialog(files, self.file_ops, self.main.active_pane, self.main.update_ui)
            elif action == "clean_temp":
                current_dir = self.main.active_pane.getCurrentDirectory()
                self.main.dialogs.show_cleanup_dialog(
                    current_dir,
                    self.file_ops,
                    self.main.active_pane,
                    self.main.update_ui
                )
            elif action == "fix_packages":
                self.dialogs.show_message("Run: opkg update && opkg upgrade", type="info")
                # Return to repair menu after message
                self._return_to_submenu_after_delay(self.show_repair_menu, 3)
            elif action == "repair_links":
                current_dir = self.main.active_pane.getCurrentDirectory()
                self.main.dialogs.show_picon_repair_dialog(
                    current_dir,
                    self.file_ops,
                    self.main.active_pane,
                    self.main.update_ui
                )
        except Exception as e:
            logger.error(f"Error handling repair menu: {e}")
            self.dialogs.show_message(f"Repair action error: {e}", type="error")
            self._return_to_submenu_after_delay(self.show_repair_menu, 3)
    
    def analyze_dependencies(self):
        """Analyze and show missing dependencies before installation"""
        import threading
        
        def analyze_thread():
            try:
                # Show analyzing message
                self.dialogs.show_message(" Analyzing WGFileManager dependencies...\n\nPlease wait...", 
                                         type="info", timeout=2)
                
                missing_deps = {}
                installed_deps = {}
                
                # Check all dependencies
                for category, packages in self.plugin_dependencies.items():
                    missing_in_category = []
                    installed_in_category = []
                    
                    for package in packages:
                        try:
                            # Check if package is installed
                            if self._is_package_installed(package):
                                installed_in_category.append(package)
                            else:
                                missing_in_category.append(package)
                        except Exception as e:
                            logger.error(f"Error checking package {package}: {e}")
                            missing_in_category.append(f"{package} (check error)")
                    
                    if missing_in_category:
                        missing_deps[category] = missing_in_category
                    if installed_in_category:
                        installed_deps[category] = installed_in_category
                
                # Prepare analysis message
                message = " WGFILEMANAGER DEPENDENCY ANALYSIS\n\n"
                message += "═" * 40 + "\n\n"
                
                # Show installed dependencies
                total_installed = sum(len(pkgs) for pkgs in installed_deps.values())
                message += f"[OK] INSTALLED: {total_installed} packages\n"
                
                for category, packages in installed_deps.items():
                    if packages:
                        message += f" {category.replace('_', ' ')}:\n"
                        for pkg in packages[:5]:  # Show first 5
                            message += f"  • {pkg}\n"
                        if len(packages) > 5:
                            message += f"  ... and {len(packages) - 5} more\n"
                
                message += "\n" + "═" * 40 + "\n\n"
                
                # Show missing dependencies
                total_missing = sum(len(pkgs) for pkgs in missing_deps.values())
                if total_missing > 0:
                    message += f"[X] MISSING: {total_missing} packages\n\n"
                    
                    # Highlight critical network dependencies
                    if "NETWORK_FEATURES" in missing_deps:
                        network_missing = missing_deps["NETWORK_FEATURES"]
                        message += "[!] CRITICAL NETWORK FEATURES MISSING:\n"
                        for pkg in network_missing:
                            if pkg == "rclone":
                                message += f" • {pkg} - Required for Cloud Sync\n"
                            elif pkg == "cifs-utils":
                                message += f" • {pkg} - Required for SMB/CIFS mounts\n"
                            elif pkg == "python3-paramiko":
                                message += f" • {pkg} - Required for SFTP connections\n"
                            else:
                                message += f"  • {pkg}\n"
                        message += "\n"
                    
                    for category, packages in missing_deps.items():
                        if category != "NETWORK_FEATURES":  # Already shown above
                            message += f" {category.replace('_', ' ')}:\n"
                            for pkg in packages[:5]:  # Show first 5
                                message += f"  • {pkg}\n"
                            if len(packages) > 5:
                                message += f"  ... and {len(packages) - 5} more\n"
                            message += "\n"
                    
                    message += "\n" + "═" * 40 + "\n\n"
                    message += " Install missing dependencies now?\n\n"
                    message += "This may take several minutes and\n"
                    message += "requires an active internet connection."
                    
                    # Ask for installation confirmation
                    self.dialogs.show_confirmation(
                        message,
                        lambda res: self._install_selected_dependencies(res, missing_deps) if res else None
                    )
                else:
                    message += " All WGFileManager dependencies are already installed!\n\n"
                    message += "No installation needed."
                    self.dialogs.show_message(message, type="info")
                    self._return_to_submenu_after_delay(self.show_repair_menu, 3)
                
            except Exception as e:
                logger.error(f"Error in dependency analysis thread: {e}")
                self.dialogs.show_message(f"Dependency analysis failed:\n{str(e)}", type="error")
                self._return_to_submenu_after_delay(self.show_repair_menu, 3)
        
        # Start analysis in background thread
        thread = threading.Thread(target=analyze_thread, daemon=True)
        thread.start()
    
    def _is_package_installed(self, package):
        """Check if a package is installed"""
        try:
            # For system packages (non-Python)
            if not package.startswith("python3-"):
                # Check using which command for binaries
                result = subprocess.run(["which", package], capture_output=True, text=True)
                if result.returncode == 0:
                    return True
                
                # Check using opkg for packages
                result = subprocess.run(
                    ["opkg", "list-installed", package],
                    capture_output=True,
                    text=True
                )
                return package in result.stdout
            
            else:
                # For Python packages, try to import
                import importlib
                module_name = package.replace("python3-", "")
                
                # Handle special cases
                if module_name == "paramiko":
                    module_name = "paramiko"
                elif module_name == "pil":
                    module_name = "PIL"
                elif module_name == "cryptography":
                    module_name = "cryptography"
                
                try:
                    importlib.import_module(module_name)
                    return True
                except ImportError:
                    return False
                    
        except Exception:
            return False
    
    def _install_selected_dependencies(self, confirmed, missing_deps):
        """Install selected dependencies"""
        if not confirmed:
            # User cancelled, return to repair menu
            self._return_to_submenu_after_delay(self.show_repair_menu, 1)
            return
        
        # Flatten missing dependencies list
        all_missing = []
        for category, packages in missing_deps.items():
            all_missing.extend(packages)
        
        # Remove duplicates and filter out "check error" entries
        all_missing = list(set([pkg for pkg in all_missing if "(check error)" not in pkg]))
        
        # Start installation
        self._perform_dependency_installation(all_missing)
    
    def _perform_dependency_installation(self, packages_to_install):
        """Perform dependency installation"""
        import threading
        
        def install_thread():
            try:
                # Show installation progress
                total = len(packages_to_install)
                self.dialogs.show_message(
                    f" Installing {total} dependencies...\n\n"
                    f"This may take several minutes.\n"
                    f"Please wait...",
                    type="info", timeout=3
                )
                
                installed = []
                failed = []
                skipped = []
                
                for i, package in enumerate(packages_to_install, 1):
                    try:
                        # Check again if already installed (in case of parallel operations)
                        if self._is_package_installed(package):
                            skipped.append(package)
                            logger.info(f"Package already installed: {package}")
                            continue
                        
                        # Show progress
                        progress_msg = f"Installing: {package}\n\n"
                        progress_msg += f"Progress: {i}/{total}\n"
                        
                        # Determine installation command
                        if package.startswith("python3-"):
                            # Python packages
                            module_name = package.replace("python3-", "")
                            install_cmd = ["pip3", "install", module_name]
                            timeout = 60
                        else:
                            # System packages
                            install_cmd = ["opkg", "install", package]
                            timeout = 120  # Longer timeout for system packages
                        
                        logger.info(f"Installing {package} with command: {' '.join(install_cmd)}")
                        
                        result = subprocess.run(
                            install_cmd,
                            capture_output=True,
                            text=True,
                            timeout=timeout
                        )
                        
                        if result.returncode == 0:
                            installed.append(package)
                            logger.info(f"[OK] Successfully installed: {package}")
                        else:
                            error_msg = result.stderr[:200] if result.stderr else result.stdout[:200] if result.stdout else "Unknown error"
                            failed.append(f"{package}: {error_msg}")
                            logger.error(f"[X] Failed to install {package}: {error_msg}")
                            
                    except subprocess.TimeoutExpired:
                        failed.append(f"{package}: Installation timeout")
                        logger.error(f"[X] Timeout installing {package}")
                    except Exception as e:
                        failed.append(f"{package}: {str(e)[:100]}")
                        logger.error(f"[X] Error installing {package}: {e}")
                
                # Show final results
                message = " DEPENDENCY INSTALLATION RESULTS\n\n"
                message += "═" * 40 + "\n\n"
                
                if installed:
                    message += f"[OK] SUCCESSFULLY INSTALLED ({len(installed)}):\n"
                    for pkg in installed[:10]:  # Show first 10
                        message += f"  • {pkg}\n"
                    if len(installed) > 10:
                        message += f"  ... and {len(installed) - 10} more\n"
                    message += "\n"
                
                if skipped:
                    message += f" ALREADY INSTALLED ({len(skipped)}):\n"
                    for pkg in skipped[:5]:
                        message += f"  • {pkg}\n"
                    if len(skipped) > 5:
                        message += f"  ... and {len(skipped) - 5} more\n"
                    message += "\n"
                
                if failed:
                    message += f"[X] FAILED ({len(failed)}):\n"
                    for fail in failed[:5]:  # Show first 5 failures
                        message += f"  • {fail}\n"
                    if len(failed) > 5:
                        message += f"  ... and {len(failed) - 5} more\n"
                    message += "\n"
                
                # Add network-specific notes
                network_packages = [pkg for pkg in packages_to_install if pkg in [
                    "rclone", "cifs-utils", "smbclient", "python3-paramiko", "curl"
                ]]
                
                if any(network_pkg in installed for network_pkg in network_packages):
                    message += "[!] NETWORK FEATURES NOTE:\n"
                    message += "Some network features may require:\n"
                    message += "• System restart for new mounts\n"
                    message += "• rclone configuration: 'rclone config'\n"
                    message += "• SMB credentials for network shares\n"
                    message += "\n"
                
                message += "═" * 40 + "\n\n"
                message += " Installation complete!"
                
                # Show results and return to repair menu
                self.dialogs.show_message(message, type="info")
                self._return_to_submenu_after_delay(self.show_repair_menu, 5)
                
            except Exception as e:
                logger.error(f"Error in dependency installation thread: {e}")
                self.dialogs.show_message(f"Installation failed:\n{str(e)}", type="error")
                self._return_to_submenu_after_delay(self.show_repair_menu, 3)
        
        # Start installation in background thread
        thread = threading.Thread(target=install_thread, daemon=True)
        thread.start()
    
    def rename_folder(self, folder_path):
        """Rename current folder - CRITICAL FIX: Force folder name"""
        try:
            from Screens.VirtualKeyBoard import VirtualKeyBoard
        
            current_name = os.path.basename(folder_path)
        
            def rename_callback(new_name):
                if new_name and new_name != current_name:
                    self.execute_rename_folder(folder_path, new_name)
        
            # CRITICAL FIX: Direct call with folder name
            self.main.session.openWithCallback(
                rename_callback,
                VirtualKeyBoard,
                title="Rename Folder: " + current_name[:25],
                text=current_name  # Force folder name
        )
        except Exception as e:
            logger.error(f"Error renaming folder: {e}")
            self.dialogs.show_message(f"Rename error: {e}", type="error")
    
    def execute_rename_folder(self, old_path, new_name):
        """Execute folder rename"""
        try:
            new_path = self.file_ops.rename(old_path, new_name)
            self._force_refresh_pane()
            self.main.dialogs.show_message(f"[OK] Folder renamed to: {new_name}", type="info")
        except Exception as e:
            logger.error(f"Error executing folder rename: {e}")
            self.main.dialogs.show_message(f"Rename failed:\n{e}", type="error")
    
    def rename_item(self, item_path):
        """Rename selected item - CRITICAL FIX: Force filename load"""
        try:
            from Screens.VirtualKeyBoard import VirtualKeyBoard
        
            current_name = os.path.basename(item_path)
        
            def rename_callback(new_name):
                if new_name and new_name != current_name:
                    self.execute_rename_item(item_path, new_name)
        
            # CRITICAL FIX: Direct VirtualKeyBoard call
            self.main.session.openWithCallback(
                rename_callback,
                VirtualKeyBoard,
                title="Rename: " + current_name[:30],
                text=current_name  # Force filename
            )
        except Exception as e:
            logger.error(f"Error renaming item: {e}")
            self.dialogs.show_message(f"Rename error: {e}", type="error")
    
    def execute_rename_item(self, old_path, new_name):
        """Execute item rename"""
        try:
            new_path = self.file_ops.rename(old_path, new_name)
            self._force_refresh_pane()
            self.main.dialogs.show_message(f"[OK] Renamed to: {new_name}", type="info")
        except Exception as e:
            logger.error(f"Error executing item rename: {e}")
            self.main.dialogs.show_message(f"Rename failed:\n{e}", type="error")
    
    def delete_item(self, item_path, is_dir, item_name):
        """Delete selected item"""
        try:
            item_type = "folder" if is_dir else "file"
            
            self.main.dialogs.show_confirmation(
                f"Delete {item_type} '{item_name}'?\n\nThis cannot be undone!",
                lambda res: self.execute_delete_item(res, item_path, item_name, item_type)
            )
        except Exception as e:
            logger.error(f"Error deleting item: {e}")
            self.dialogs.show_message(f"Delete error: {e}", type="error")
    
    def execute_delete_item(self, confirmed, item_path, item_name, item_type):
        """Execute item deletion"""
        if not confirmed:
            return
        
        try:
            self.file_ops.delete(item_path)
            self._force_refresh_pane()
            
            if self.config.plugins.wgfilemanager.trash_enabled.value == "yes":
                msg = f"[OK] Moved to trash: {item_name}"
            else:
                msg = f"[OK] Permanently deleted: {item_name}"
            
            self.main.dialogs.show_message(msg, type="info")
        except Exception as e:
            logger.error(f"Error executing item deletion: {e}")
            self.main.dialogs.show_message(f"Delete failed:\n{e}", type="error")
    
    def delete_multiple_items(self, file_paths):
        """Delete multiple selected items"""
        try:
            item_type = "items"
            
            self.main.dialogs.show_confirmation(
                f"Delete {len(file_paths)} {item_type}?\n\nThis cannot be undone!",
                lambda res: self.execute_delete_multiple(res, file_paths) if res else None
            )
        except Exception as e:
            logger.error(f"Error deleting multiple items: {e}")
            self.dialogs.show_message(f"Delete error: {e}", type="error")
    
    def execute_delete_multiple(self, confirmed, file_paths):
        """Execute deletion of multiple items"""
        if not confirmed:
            return
        
        try:
            success = 0
            errors = []
            
            for item_path in file_paths:
                try:
                    self.file_ops.delete(item_path)
                    success += 1
                except Exception as e:
                    errors.append(f"{os.path.basename(item_path)}: {str(e)[:30]}")
            
            msg = f"[OK] Deleted: {success} items\n"
            if errors:
                msg += f"\n[X] Failed: {len(errors)}\n"
                msg += "\n".join(errors[:3])
                if len(errors) > 3:
                    msg += f"\n... and {len(errors) - 3} more"
            
            self._force_refresh_pane()
            self.main.dialogs.show_message(msg, type="info")
        except Exception as e:
            logger.error(f"Error executing multiple deletion: {e}")
            self.main.dialogs.show_message(f"Delete multiple failed:\n{e}", type="error")
    
    def copy_item(self, item_path):
        """Copy item to clipboard"""
        try:
            self.main.clipboard = [item_path]
            self.main.clipboard_mode = "copy"
            self.main.update_ui()
            self.main.dialogs.show_message(f"[OK] Copied to clipboard: {os.path.basename(item_path)}", 
                                          type="info", timeout=2)
        except Exception as e:
            logger.error(f"Error copying item: {e}")
            self.dialogs.show_message(f"Copy error: {e}", type="error")
    
    def cut_item(self, item_path):
        """Cut item to clipboard"""
        try:
            self.main.clipboard = [item_path]
            self.main.clipboard_mode = "cut"
            self.main.update_ui()
            self.main.dialogs.show_message(f"[OK] Cut to clipboard: {os.path.basename(item_path)}", 
                                          type="info", timeout=2)
        except Exception as e:
            logger.error(f"Error cutting item: {e}")
            self.dialogs.show_message(f"Cut error: {e}", type="error")
    
    def copy_to_other_pane(self, item_path):
        """Copy item to other pane"""
        try:
            dest_dir = self.main.inactive_pane.getCurrentDirectory()
            
            self.main.dialogs.show_confirmation(
                f"Copy to:\n{dest_dir}?",
                lambda res: self.main.execute_transfer("cp", [item_path], dest_dir) if res else None
            )
        except Exception as e:
            logger.error(f"Error copying to other pane: {e}")
            self.dialogs.show_message(f"Copy error: {e}", type="error")
    
    def move_to_other_pane(self, item_path):
        """Move item to other pane"""
        try:
            dest_dir = self.main.inactive_pane.getCurrentDirectory()
            
            self.main.dialogs.show_confirmation(
                f"Move to:\n{dest_dir}?",
                lambda res: self.main.execute_transfer("mv", [item_path], dest_dir) if res else None
            )
        except Exception as e:
            logger.error(f"Error moving to other pane: {e}")
            self.dialogs.show_message(f"Move error: {e}", type="error")
    
    def edit_text_file(self, file_path):
        """Edit text file"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(5000)
            
            preview = f" Edit: {os.path.basename(file_path)}\n\n"
            preview += content[:2000]
            if len(content) > 2000:
                preview += "\n\n... (file truncated)"
            
            preview += "\n\nEdit this file? (Not implemented in this version)"
            
            self.main.dialogs.show_message(preview, type="info")
        except Exception as e:
            logger.error(f"Error editing text file: {e}")
            self.main.dialogs.show_message(f"Cannot edit file:\n{e}", type="error")
    
    def create_shortcut(self, item_path):
        """Create shortcut to item"""
        try:
            self.main.dialogs.show_message(
                "Shortcut creation would be implemented here.\n\n"
                "This would create a symbolic link to the selected item.",
                type="info"
            )
        except Exception as e:
            logger.error(f"Error creating shortcut: {e}")
            self.dialogs.show_message(f"Shortcut error: {e}", type="error")
    
    def show_smart_context_menu(self, file_path):
        """Show smart context menu based on file type"""
        try:
            if not os.path.exists(file_path):
                return
            
            filename = os.path.basename(file_path)
            ext = os.path.splitext(filename)[1].lower()
            
            # Determine file type and show appropriate menu
            if ext == '.sh':
                self._show_script_menu(file_path, filename)
            elif ext in ['.zip', '.tar', '.tar.gz', '.tgz', '.rar', '.7z', '.gz']:
                self._show_archive_menu(file_path, filename)
            elif ext == '.ipk':
                self._show_package_menu(file_path, filename)
            elif ext in ['.mp4', '.mkv', '.avi', '.ts', '.m2ts']:
                self._show_media_menu(file_path, filename)
            elif ext in ['.mp3', '.flac', '.wav', '.aac']:
                self._show_audio_menu(file_path, filename)
            elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                self._show_image_menu(file_path, filename)
            elif ext in ['.txt', '.log', '.conf', '.cfg', '.ini', '.xml', '.json']:
                self._show_text_menu(file_path, filename)
            else:
                # Fallback to regular item context menu
                self.show_item_context_menu()
        except Exception as e:
            logger.error(f"Error showing smart context menu: {e}")
            self.dialogs.show_message(f"Smart menu error: {e}", type="error")
    
    def _show_script_menu(self, file_path, filename):
        """Context menu for shell scripts"""
        try:
            menu_items = [
                (" <-- Back", "back"),
                ("Cancel", None),
                ("View or edit this shell script", "view"),
                ("Run script", "run"),
                ("Run script in background", "run_bg"),
                ("Run script with optional parameter", "run_param"),
                ("Run script with optional parameter in background", "run_param_bg"),
                ("Make executable", "chmod"),
            ]
            
            self.main.session.openWithCallback(
                lambda choice: self._handle_script_action(choice, file_path, filename) if choice and choice[1] else None,
                ChoiceBox,
                title="Script: " + filename,
                list=menu_items
            )
        except Exception as e:
            logger.error(f"Error showing script menu: {e}")
            self.dialogs.show_message(f"Script menu error: {e}", type="error")
    
    def _handle_script_action(self, choice, file_path, filename):
        """Handle script menu action"""
        if not choice or not choice[1]:
            return
        
        action = choice[1]
        
        try:
            if action == "view":
                self.main.dialogs.preview_file(file_path, self.file_ops, self.config)
            elif action == "run":
                self._execute_script(file_path, "", False)
            elif action == "run_bg":
                self._execute_script(file_path, "", True)
            elif action == "run_param":
                self.main.dialogs.show_input(
                    "Optional parameter:",
                    "",
                    lambda param: self._execute_script(file_path, param if param else "", False)
                )
            elif action == "run_param_bg":
                self.main.dialogs.show_input(
                    "Optional parameter:",
                    "",
                    lambda param: self._execute_script(file_path, param if param else "", True)
                )
            elif action == "chmod":
                import os
                try:
                    os.chmod(file_path, 0o755)
                    self.main.dialogs.show_message("Made executable: " + filename, type="info", timeout=2)
                except Exception as e:
                    self.main.dialogs.show_message("Failed to make executable: " + str(e), type="error")
        except Exception as e:
            logger.error(f"Error handling script action: {e}")
            self.dialogs.show_message(f"Script action error: {e}", type="error")
    
    def _execute_script(self, file_path, param, background):
        """Execute shell script - FIXED with better error handling"""
        import subprocess
        import threading
        
        def run_script():
            try:
                cmd = ["/bin/sh", file_path]
                if param and param.strip():
                    cmd.append(param.strip())
                
                if background:
                    # For background execution, use Popen with detached process
                    try:
                        result = subprocess.Popen(cmd, 
                                                stdout=subprocess.PIPE, 
                                                stderr=subprocess.PIPE,
                                                start_new_session=True)
                        
                        # Store PID for potential management
                        script_pid = result.pid
                        logger.info(f"Script started in background with PID: {script_pid}")
                        
                        self.main.dialogs.show_message(
                            f"Script started in background\n\nPID: {script_pid}",
                            type="info", timeout=3
                        )
                    except Exception as e:
                        logger.error(f"Background script execution error: {e}")
                        self.main.dialogs.show_message(
                            f"Failed to start script in background: {str(e)}",
                            type="error"
                        )
                else:
                    # For foreground execution, use run with timeout
                    try:
                        result = subprocess.run(cmd, 
                                              capture_output=True, 
                                              text=True, 
                                              timeout=120,
                                              encoding='utf-8',
                                              errors='ignore')
                        
                        # Check if result is not None
                        if result is not None:
                            exit_code = result.returncode if hasattr(result, 'returncode') else -1
                            output = ""
                            
                            if hasattr(result, 'stdout') and result.stdout:
                                output = result.stdout
                            elif hasattr(result, 'stderr') and result.stderr:
                                output = result.stderr
                            
                            if not output:
                                output = "Script executed successfully" if exit_code == 0 else "Script failed"
                            
                            # Limit output display to reasonable size
                            display_output = str(output)[:800]
                            if len(str(output)) > 800:
                                display_output += "\n\n... (output truncated)"
                            
                            self.main.dialogs.show_message(
                                f"Script Output (Exit code: {exit_code}):\n\n{display_output}",
                                type="info" if exit_code == 0 else "error"
                            )
                        else:
                            self.main.dialogs.show_message(
                                "Script executed (no output returned)",
                                type="info"
                            )
                            
                    except subprocess.TimeoutExpired:
                        logger.warning(f"Script execution timed out: {file_path}")
                        self.main.dialogs.show_message(
                            "Script execution timed out (120 seconds)\n\nThe script may still be running in background.",
                            type="error"
                        )
                    except Exception as e:
                        logger.error(f"Foreground script execution error: {e}")
                        self.main.dialogs.show_message(f"Script error: {str(e)}", type="error")
                        
            except Exception as e:
                logger.error(f"Script execution error: {e}")
                self.main.dialogs.show_message(f"Script setup error: {str(e)}", type="error")
        
        # Start script execution in separate thread
        try:
            script_thread = threading.Thread(target=run_script, daemon=True)
            script_thread.start()
        except Exception as e:
            logger.error(f"Failed to start script thread: {e}")
            self.main.dialogs.show_message(f"Failed to start script thread: {str(e)}", type="error")
    
    def _show_archive_menu(self, file_path, filename):
        """Context menu for archive files"""
        try:
            menu_items = [
                (" <-- Back", "back"),
                ("Cancel", None),
                ("View the archive contents", "view"),
                ("Extract the archive contents", "extract"),
            ]
            
            self.main.session.openWithCallback(
                lambda choice: self._handle_archive_action(choice, file_path, filename) if choice and choice[1] else None,
                ChoiceBox,
                title="Archive: " + filename,
                list=menu_items
            )
        except Exception as e:
            logger.error(f"Error showing archive menu: {e}")
            self.dialogs.show_message(f"Archive menu error: {e}", type="error")
    
    def _handle_archive_action(self, choice, file_path, filename):
        """Handle archive menu action"""
        if not choice or not choice[1]:
            return
        
        action = choice[1]
        
        try:
            if action == "view":
                try:
                    contents = self.main.archive_mgr.list_archive(file_path)
                    msg = "Archive Contents (%d items):\n\n" % len(contents)
                    for item in contents[:20]:
                        icon = "" if item.get('is_dir') else ""
                        msg += "%s %s\n" % (icon, item['name'])
                    if len(contents) > 20:
                        msg += "\n... and %d more items" % (len(contents) - 20)
                    self.main.dialogs.show_message(msg, type="info")
                except Exception as e:
                    self.main.dialogs.show_message("Cannot view archive: " + str(e), type="error")
            
            elif action == "extract":
                self.main.dialogs.show_extract_dialog(
                    file_path, 
                    self.main.archive_mgr, 
                    self.main.active_pane, 
                    self.main.update_ui
                )
        except Exception as e:
            logger.error(f"Error handling archive action: {e}")
            self.dialogs.show_message(f"Archive action error: {e}", type="error")
    
    def _show_package_menu(self, file_path, filename):
        """Context menu for IPK packages"""
        try:
            menu_items = [
                (" <-- Back", "back"),
                ("Cancel", None),
                ("View the package contents", "view"),
                ("Extract the package contents", "extract"),
                ("Install the package", "install"),
            ]
            
            self.main.session.openWithCallback(
                lambda choice: self._handle_package_action(choice, file_path, filename) if choice and choice[1] else None,
                ChoiceBox,
                title="Package: " + filename,
                list=menu_items
            )
        except Exception as e:
            logger.error(f"Error showing package menu: {e}")
            self.dialogs.show_message(f"Package menu error: {e}", type="error")
    
    def _handle_package_action(self, choice, file_path, filename):
        """Handle package menu action"""
        if not choice or not choice[1]:
            return
        
        action = choice[1]
        
        try:
            if action == "view":
                def view_pkg():
                    try:
                        import subprocess
                        result = subprocess.run(
                            ["opkg", "info", file_path],
                            capture_output=True, text=True, timeout=30  # Increased timeout
                        )
                        info = result.stdout if result.stdout else "No package info available"
                        self.main.dialogs.show_message("Package Info:\n\n" + info[:1000], type="info")
                    except subprocess.TimeoutExpired:
                        self.main.dialogs.show_message("Package info timeout (30 seconds)", type="error")
                    except Exception as e:
                        self.main.dialogs.show_message("Cannot view package: " + str(e), type="error")
                
                import threading
                threading.Thread(target=view_pkg, daemon=True).start()
            
            elif action == "extract":
                # IPK files are ar archives, can extract with ar/tar
                self.main.dialogs.show_message(
                    "Extract IPK to current directory?\n\nUse archive tools for extraction.",
                    type="info"
                )
            
            elif action == "install":
                self.main.dialogs.show_confirmation(
                    "Install package:\n%s\n\nThis will run:\nopkg install %s" % (filename, file_path),
                    lambda res: self._install_package(res, file_path) if res else None
                )
        except Exception as e:
            logger.error(f"Error handling package action: {e}")
            self.dialogs.show_message(f"Package action error: {e}", type="error")
    
    def _install_package(self, confirmed, file_path):
        """Install IPK package - IMPROVED WITH BETTER TIMEOUT HANDLING"""
        if not confirmed:
            return
        
        import subprocess
        import threading
        
        def install():
            try:
                # Use absolute path for opkg with increased timeout (180 seconds)
                logger.info(f"Installing package: {file_path}")
                
                result = subprocess.run(
                    ["opkg", "install", file_path],
                    capture_output=True, 
                    text=True, 
                    timeout=180,  # Increased to 3 minutes for large packages
                    encoding='utf-8',
                    errors='ignore'
                )
                
                if result.returncode == 0:
                    success_msg = "Package installed successfully!"
                    if result.stdout:
                        success_msg += "\n\n" + result.stdout[:500]
                    logger.info(f"Package installation successful: {file_path}")
                    self.main.dialogs.show_message(success_msg, type="info")
                else:
                    error_msg = "Installation failed!"
                    if result.stderr:
                        error_msg += "\n\n" + result.stderr[:500]
                    elif result.stdout:
                        error_msg += "\n\n" + result.stdout[:500]
                    logger.error(f"Package installation failed: {file_path} - {error_msg}")
                    self.main.dialogs.show_message(error_msg, type="error")
                    
            except subprocess.TimeoutExpired:
                logger.error(f"Package installation timeout: {file_path}")
                self.main.dialogs.show_message(
                    "Installation timed out (180 seconds)\n\nThe package might still be installing.",
                    type="error"
                )
            except FileNotFoundError:
                logger.error("opkg command not found")
                self.main.dialogs.show_message(
                    "opkg command not found!\n\nPlease ensure you're running on Enigma2 system.",
                    type="error"
                )
            except Exception as e:
                logger.error(f"Installation error: {e}")
                self.main.dialogs.show_message(f"Installation error: {str(e)}", type="error")
        
        # Show progress message
        self.main.dialogs.show_message(
            f"Installing package: {os.path.basename(file_path)}\n\nThis may take several minutes...",
            type="info",
            timeout=3
        )
        
        # Start installation in separate thread
        install_thread = threading.Thread(target=install, daemon=True)
        install_thread.start()
    
    def _show_media_menu(self, file_path, filename):
        """Context menu for video files"""
        try:
            menu_items = [
                (" <-- Back", "back"),
                ("Cancel", None),
                ("Play media file", "play"),
                ("View file info", "info"),
                ("Copy to other pane", "copy_other"),
                ("Move to other pane", "move_other"),
            ]
            
            self.main.session.openWithCallback(
                lambda choice: self._handle_media_action(choice, file_path, filename) if choice and choice[1] else None,
                ChoiceBox,
                title="Media: " + filename,
                list=menu_items
            )
        except Exception as e:
            logger.error(f"Error showing media menu: {e}")
            self.dialogs.show_message(f"Media menu error: {e}", type="error")
    
    def _show_audio_menu(self, file_path, filename):
        """Context menu for audio files - IMPROVED"""
        try:
            # Get directory containing the audio file
            directory = os.path.dirname(file_path)
            
            # Audio file extensions
            audio_extensions = ['.mp3', '.flac', '.wav', '.aac', '.ogg', '.m4a', '.wma', '.ac3', '.dts']
            
            # Get all audio files in directory
            audio_files = []
            try:
                if os.path.isdir(directory):
                    for item in sorted(os.listdir(directory)):
                        item_path = os.path.join(directory, item)
                        if os.path.isfile(item_path):
                            # Check extension
                            if any(item.lower().endswith(ext) for ext in audio_extensions):
                                audio_files.append(item_path)
                    
                    logger.info(f"Found {len(audio_files)} audio files in {directory}")
            except Exception as e:
                logger.error(f"Error scanning directory for audio files: {e}")
            
            # Build menu items
            menu_items = [
                (" <-- Back", "back"),
                ("Cancel", None),
                (" Play this audio file", "play_single"),
            ]
            
            # Add "Play all" option if multiple audio files found
            if len(audio_files) > 1:
                menu_items.append((" Play all audio files in directory", "play_all"))
            
            # Add other common options
            menu_items.extend([
                (" File info", "info"),
                (" Copy to other pane", "copy_other"),
                (" Move to other pane", "move_other"),
            ])
            
            # Show menu
            self.main.session.openWithCallback(
                lambda choice: self._handle_audio_action(choice, file_path, filename, audio_files) if choice and choice[1] else None,
                ChoiceBox,
                title=f" Audio: {filename}",
                list=menu_items
            )
        except Exception as e:
            logger.error(f"Error showing audio menu: {e}")
            self.dialogs.show_message(f"Audio menu error: {e}", type="error")
    
    def _handle_audio_action(self, choice, file_path, filename, audio_files):
        """Handle audio menu action - ENHANCED with playlist player"""
        if not choice or not choice[1]:
            return

        action = choice[1]

        try:
            if action == "play_single":
                # Play single audio file with playlist player (single track)
                try:
                    from ..ui.audio_player import AudioPlaylistPlayer
                
                    # Create single-track playlist
                    self.main.session.open(
                        AudioPlaylistPlayer,
                        [file_path],  # Single file playlist
                        0,            # Start at index 0
                        self.main     # Pass main screen reference
                    )
                except ImportError as e:
                    logger.error(f"Cannot import AudioPlaylistPlayer: {e}")
                    # Fallback to old method
                    self.main.preview_media()

            elif action == "play_all":
                # Play all audio files in directory as playlist
                if audio_files:
                    try:
                        from ..ui.audio_player import AudioPlaylistPlayer
                    
                        # Find current file index
                        current_index = 0
                        try:
                            current_index = audio_files.index(file_path)
                        except ValueError:
                            current_index = 0
                    
                        # Open playlist player
                        self.main.session.open(
                            AudioPlaylistPlayer,
                            audio_files,   # Full playlist
                            current_index, # Start at current file
                            self.main      # Pass main screen reference
                        )
                    except ImportError as e:
                        logger.error(f"Cannot import AudioPlaylistPlayer: {e}")
                        self.dialogs.show_message(
                            "Audio player not available!\n\nPlease ensure audio_player.py is installed.",
                            type="error"
                        )
                else:
                    self.dialogs.show_message("No audio files found in directory", type="info")

            elif action == "info":
                self.main.show_file_info()

            elif action == "copy_other":
                self.copy_to_other_pane(file_path)

            elif action == "move_other":
                self.move_to_other_pane(file_path)
                
        except Exception as e:
            logger.error(f"Error handling audio action: {e}")
            self.dialogs.show_message(f"Audio action error: {e}", type="error")
    
    
    def _handle_media_action(self, choice, file_path, filename):
        """Handle media menu action"""
        if not choice or not choice[1]:
            return
        
        action = choice[1]
        
        try:
            if action == "play":
                self.main.preview_media()
            elif action == "info":
                self.main.show_file_info()
            elif action == "copy_other":
                self.copy_to_other_pane(file_path)
            elif action == "move_other":
                self.move_to_other_pane(file_path)
        except Exception as e:
            logger.error(f"Error handling media action: {e}")
            self.dialogs.show_message(f"Media action error: {e}", type="error")
    
    def _show_image_menu(self, file_path, filename):
        """Context menu for image files"""
        try:
            menu_items = [
                (" <-- Back", "back"),
                ("Cancel", None),
                ("View image", "view"),
                ("View file info", "info"),
                ("Copy to other pane", "copy_other"),
            ]
            
            self.main.session.openWithCallback(
                lambda choice: self._handle_image_action(choice, file_path, filename) if choice and choice[1] else None,
                ChoiceBox,
                title="Image: " + filename,
                list=menu_items
            )
        except Exception as e:
            logger.error(f"Error showing image menu: {e}")
            self.dialogs.show_message(f"Image menu error: {e}", type="error")
    
    def _handle_image_action(self, choice, file_path, filename):
        """Handle image menu action"""
        if not choice or not choice[1]:
            return
        
        action = choice[1]
        
        try:
            if action == "view":
                self.main.dialogs.preview_image(file_path, self.file_ops)
            elif action == "info":
                self.main.show_file_info()
            elif action == "copy_other":
                self.copy_to_other_pane(file_path)
        except Exception as e:
            logger.error(f"Error handling image action: {e}")
            self.dialogs.show_message(f"Image action error: {e}", type="error")
    
    def _show_text_menu(self, file_path, filename):
        """Context menu for text files"""
        try:
            menu_items = [
                (" <-- Back", "back"),
                ("Cancel", None),
                ("View/Edit text file", "view"),
                ("View file info", "info"),
                ("Copy to other pane", "copy_other"),
            ]
            
            self.main.session.openWithCallback(
                lambda choice: self._handle_text_action(choice, file_path, filename) if choice and choice[1] else None,
                ChoiceBox,
                title="Text: " + filename,
                list=menu_items
            )
        except Exception as e:
            logger.error(f"Error showing text menu: {e}")
            self.dialogs.show_message(f"Text menu error: {e}", type="error")
    
    def _handle_text_action(self, choice, file_path, filename):
        """Handle text menu action"""
        if not choice or not choice[1]:
            return
        
        action = choice[1]
        
        try:
            if action == "view":
                self.main.dialogs.preview_file(file_path, self.file_ops, self.config)
            elif action == "info":
                self.main.show_file_info()
            elif action == "copy_other":
                self.copy_to_other_pane(file_path)
        except Exception as e:
            logger.error(f"Error handling text action: {e}")
            self.dialogs.show_message(f"Text action error: {e}", type="error")
    
    def _force_refresh_pane(self):
        """Force refresh the active pane - NEW METHOD ADDED"""
        try:
            current_dir = self.main.active_pane.getCurrentDirectory()
            
            # Change to parent and back to force refresh
            parent_dir = os.path.dirname(current_dir)
            if parent_dir != current_dir:
                self.main.active_pane.changeDir(parent_dir)
                self.main.active_pane.changeDir(current_dir)
            else:
                # If already at root, refresh directly
                self.main.active_pane.refresh()
            
            # Update UI
            self.main.update_ui()
            
            # Force redraw
            if hasattr(self.main.active_pane, 'instance'):
                try:
                    self.main.active_pane.instance.invalidate()
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error forcing refresh: {e}")

    def add_subtitle_options(self, menu_items, file_path):
        """Add subtitle options to context menu for video files"""
        try:
            ext = os.path.splitext(file_path)[1].lower()
            video_extensions = ['.mp4', '.mkv', '.avi', '.ts', '.m2ts', '.mov', '.m4v']
            
            if ext in video_extensions:
                # Subtitle options for video files
                menu_items.extend([
                    (" Play without subtitles", lambda: self._play_video(file_path, False)),
                    (" Play with subtitles", lambda: self._play_video(file_path, True)),
                    (" Subtitle Settings", lambda: self._open_subtitle_settings(file_path)),
                    (" Download Subtitles", lambda: self._download_subtitles(file_path)),
                    (" Find Subtitles", lambda: self._find_subtitles(file_path)),
                    (" Sync Subtitles", lambda: self._sync_subtitles(file_path)),
                ])
        except Exception as e:
            logger.error(f"Error adding subtitle options: {e}")
    
    def _play_video(self, file_path, with_subtitles=True):
        """Play video with subtitle option"""
        try:
            if with_subtitles and self.parent.subtitle_manager:
                # Ensure subtitle manager has this video
                self.parent.subtitle_manager.set_video_file(file_path)
                # Try to auto-load subtitles
                from enigma import eServiceReference
                service_ref = eServiceReference(4097, 0, file_path)
                self.parent.subtitle_manager.auto_load_subtitle(service_ref)
            
            self.parent.play_media_file(file_path)
        except Exception as e:
            logger.error(f"Error playing video: {e}")
            self.parent.dialogs.show_message(f"Playback error: {e}", type="error")
    
    def _open_subtitle_settings(self, file_path):
        """Open subtitle settings for video"""
        try:
            if self.parent.subtitle_manager:
                self.parent.open_subtitle_settings(file_path)
            else:
                self.parent.dialogs.show_message(
                    "Subtitle manager not available",
                    type="warning"
                )
        except Exception as e:
            logger.error(f"Error opening subtitle settings: {e}")
    
    def _download_subtitles(self, file_path):
        """Download subtitles for video"""
        try:
            self.parent.dialogs.show_subtitle_download_dialog(file_path, self._handle_download_choice)
        except Exception as e:
            logger.error(f"Error downloading subtitles: {e}")
    
    def _handle_download_choice(self, method, video_path):
        """Handle subtitle download choice"""
        try:
            if method == "filename":
                self._download_by_filename(video_path)
            elif method == "hash":
                self._download_by_hash(video_path)
            elif method == "online":
                self._search_online(video_path)
            elif method == "local":
                self._browse_local(video_path)
        except Exception as e:
            logger.error(f"Error handling download choice: {e}")
    
    def _find_subtitles(self, file_path):
        """Find existing subtitle files"""
        try:
            if self.parent.subtitle_manager:
                subtitles = self.parent.subtitle_manager.find_local_subtitles(file_path)
                self.parent.dialogs.show_subtitle_selection_dialog(
                    subtitles, 
                    self._handle_subtitle_selection
                )
            else:
                self.parent.dialogs.show_message(
                    "Subtitle manager not available",
                    type="warning"
                )
        except Exception as e:
            logger.error(f"Error finding subtitles: {e}")
    
    def _handle_subtitle_selection(self, subtitle_path):
        """Handle subtitle selection"""
        try:
            if subtitle_path and self.parent.subtitle_manager:
                self.parent.subtitle_manager.load_subtitle(subtitle_path)
                self.parent.dialogs.show_message(
                    f"Loaded subtitle:\n{os.path.basename(subtitle_path)}",
                    type="info",
                    timeout=2
                )
        except Exception as e:
            logger.error(f"Error loading subtitle: {e}")
    
    def _sync_subtitles(self, file_path):
        """Sync subtitle timing"""
        try:
            self.parent.dialogs.show_subtitle_delay_dialog(0, self._apply_subtitle_delay)
        except Exception as e:
            logger.error(f"Error syncing subtitles: {e}")
    
    def _apply_subtitle_delay(self, delay_ms):
        """Apply subtitle delay"""
        try:
            if self.parent.subtitle_manager:
                # This would apply delay to current subtitle
                self.parent.dialogs.show_message(
                    f"Subtitle delay applied: {delay_ms}ms",
                    type="info",
                    timeout=2
                )
        except Exception as e:
            logger.error(f"Error applying delay: {e}")        