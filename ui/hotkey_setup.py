"""
Hotkey Setup Screen for WGFileManager with Subtitle Support
Location: ui/hotkey_setup.py
"""
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.ScrollLabel import ScrollLabel
from Components.config import config, ConfigSubsection, ConfigSelection, ConfigYesNo, ConfigText, ConfigInteger
from enigma import getDesktop, eTimer
import os
import json
import shutil

try:
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


class HotkeySetupScreen(Screen):
    """Hotkey Configuration Screen with Subtitle Support"""
    
    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        
        # Initialize subtitle-specific configuration
        self._init_subtitle_config()
        
        # Try to import hotkey manager
        try:
            from ..core.hotkey_manager import HotkeyManager
            self.hotkey_manager = HotkeyManager(session)
        except ImportError as e:
            logger.error(f"Cannot import HotkeyManager: {e}")
            self.hotkey_manager = None
        
        self.current_profile = "default"
        self.editing_key = None
        self.editing_action = None
        
        # Subtitle-specific hotkey categories
        self.subtitle_categories = {
            'basic': 'Basic Subtitle Controls',
            'delay': 'Delay Adjustment',
            'style': 'Style & Appearance',
            'advanced': 'Advanced Features',
            'tools': 'Subtitle Tools',
        }
        
        # Setup UI
        self._setup_ui()
        self._setup_actions()
        
        # Initialize
        self.onLayoutFinish.append(self.startup)
    
    def _init_subtitle_config(self):
        """Initialize subtitle-specific configuration"""
        try:
            if not hasattr(config.plugins, 'wgfilemanager'):
                config.plugins.wgfilemanager = ConfigSubsection()
            
            p = config.plugins.wgfilemanager
            
            # Subtitle hotkey enable/disable
            if not hasattr(p, 'subtitle_hotkeys_enabled'):
                p.subtitle_hotkeys_enabled = ConfigYesNo(default=True)
            
            # Quick delay adjustment keys
            if not hasattr(p, 'subtitle_delay_up_key'):
                p.subtitle_delay_up_key = ConfigSelection(default="8", choices=[
                    ("8", "8 Key"),
                    ("channelup", "CHANNEL UP"),
                    ("right", "RIGHT Arrow"),
                    ("fastforward", "FAST FORWARD"),
                ])
            
            if not hasattr(p, 'subtitle_delay_down_key'):
                p.subtitle_delay_down_key = ConfigSelection(default="2", choices=[
                    ("2", "2 Key"),
                    ("channeldown", "CHANNEL DOWN"),
                    ("left", "LEFT Arrow"),
                    ("rewind", "REWIND"),
                ])
            
            # Subtitle toggle key
            if not hasattr(p, 'subtitle_toggle_key'):
                p.subtitle_toggle_key = ConfigSelection(default="subtitle", choices=[
                    ("subtitle", "SUBTITLE Button"),
                    ("text", "TEXT Button"),
                    ("yellow", "YELLOW Button"),
                    ("blue", "BLUE Button"),
                ])
            
            # Subtitle menu key
            if not hasattr(p, 'subtitle_menu_key'):
                p.subtitle_menu_key = ConfigSelection(default="text", choices=[
                    ("text", "TEXT Button"),
                    ("menu", "MENU Button"),
                    ("green", "GREEN Button"),
                    ("long_subtitle", "Long SUBTITLE"),
                ])
            
            # Long press delay
            if not hasattr(p, 'subtitle_long_press_delay'):
                p.subtitle_long_press_delay = ConfigSelection(default="500", choices=[
                    ("300", "300 ms"),
                    ("500", "500 ms"),
                    ("700", "700 ms"),
                    ("1000", "1 second"),
                ])
            
            logger.info("Subtitle hotkey configuration initialized")
            
        except Exception as e:
            logger.error(f"Error initializing subtitle config: {e}")
    
    def _setup_ui(self):
        """Setup user interface with subtitle sections"""
        w, h = getDesktop(0).size().width(), getDesktop(0).size().height()
        
        self.skin = """
        <screen name="HotkeySetupScreen" position="0,0" size="%d,%d" backgroundColor="#1a1a1a" flags="wfNoBorder">
            <!-- Header -->
            <eLabel position="0,0" size="%d,80" backgroundColor="#0055aa" />
            <eLabel text=" HOTKEY SETTINGS" position="20,10" size="800,60" font="Regular;40" halign="left" valign="center" transparent="1" foregroundColor="#ffffff" />
            <eLabel text=" Subtitle Edition" position="%d,15" size="400,50" font="Regular;24" halign="right" transparent="1" foregroundColor="#00ffff" />
            
            <!-- Profile Selection -->
            <eLabel position="20,100" size="%d,60" backgroundColor="#333333" />
            <eLabel text="PROFILE:" position="30,110" size="200,40" font="Regular;24" halign="left" transparent="1" foregroundColor="#ffff00" />
            <widget name="profile_label" position="250,110" size="400,40" font="Regular;28" halign="left" transparent="1" foregroundColor="#00ff00" />
            
            <!-- Category Tabs -->
            <eLabel position="20,180" size="%d,50" backgroundColor="#222222" />
            <widget name="category_label" position="30,185" size="400,40" font="Regular;24" halign="left" transparent="1" foregroundColor="#ffff00" />
            
            <!-- Hotkey List -->
            <eLabel position="20,250" size="%d,400" backgroundColor="#222222" />
            <widget name="hotkey_list" position="30,260" size="%d,380" itemHeight="45" scrollbarMode="showOnDemand" backgroundColor="#222222" foregroundColor="#ffffff" selectionBackground="#0055aa" />
            
            <!-- Action Info -->
            <eLabel position="20,670" size="%d,150" backgroundColor="#2a2a2a" />
            <eLabel text="SELECTED ACTION" position="30,680" size="400,30" font="Regular;22" halign="left" transparent="1" foregroundColor="#ffff00" />
            <widget name="action_info" position="30,720" size="%d,80" font="Regular;20" transparent="1" foregroundColor="#aaaaaa" />
            
            <!-- Button Bar -->
            <eLabel position="0,%d" size="%d,80" backgroundColor="#000000" />
            
            <!-- Button Icons -->
            <ePixmap pixmap="buttons/red.png" position="30,%d" size="30,30" alphatest="on" />
            <ePixmap pixmap="buttons/green.png" position="180,%d" size="30,30" alphatest="on" />
            <ePixmap pixmap="buttons/yellow.png" position="330,%d" size="30,30" alphatest="on" />
            <ePixmap pixmap="buttons/blue.png" position="480,%d" size="30,30" alphatest="on" />
            <ePixmap pixmap="buttons/info.png" position="630,%d" size="30,30" alphatest="on" />
            
            <!-- Button Labels -->
            <eLabel text="Change" position="70,%d" size="100,30" font="Regular;20" transparent="1" foregroundColor="#ffffff" />
            <eLabel text="Save" position="220,%d" size="100,30" font="Regular;20" transparent="1" foregroundColor="#ffffff" />
            <eLabel text="Category" position="370,%d" size="120,30" font="Regular;20" transparent="1" foregroundColor="#ffffff" />
            <eLabel text="Profile" position="520,%d" size="100,30" font="Regular;20" transparent="1" foregroundColor="#ffffff" />
            <eLabel text="Subtitle" position="670,%d" size="100,30" font="Regular;20" transparent="1" foregroundColor="#00ffff" />
            
            <!-- Help Text -->
            <widget name="help_text" position="50,%d" size="%d,20" font="Regular;16" halign="center" transparent="1" foregroundColor="#aaaaaa" />
        </screen>""" % (
            w, h,  # screen size
            w,  # header width
            w-450,  # subtitle edition position
            w-40,  # profile area width
            w-40,  # category area width
            w-40,  # hotkey area width
            w-60,  # hotkey list width
            w-40,  # info area width
            w-60,  # action info width
            h-80, w,  # button bar
            h-60,  # red button
            h-60,  # green button
            h-60,  # yellow button
            h-60,  # blue button
            h-60,  # info button
            h-55,  # red label
            h-55,  # green label
            h-55,  # yellow label
            h-55,  # blue label
            h-55,  # info label
            h-25, w-100  # help text
        )
        
        # Widgets
        self["profile_label"] = Label("Default")
        self["category_label"] = Label("All Hotkeys")
        self["hotkey_list"] = MenuList([])
        self["action_info"] = Label("Select a hotkey to view details")
        self["help_text"] = Label("OK:Select  RED:Change  GREEN:Save  YELLOW:Category  BLUE:Profile  INFO:Subtitle  EXIT:Back")
    
    def _setup_actions(self):
        """Setup action map with subtitle controls"""
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
            "ok": self.select_hotkey,
            "cancel": self.exit_screen,
            "red": self.change_key,
            "green": self.save_config,
            "yellow": self.change_category,
            "blue": self.change_profile,
            "info": self.subtitle_special,
            "left": self.prev_category,
            "right": self.next_category,
            "up": self.key_up,
            "down": self.key_down,
        }, -1)
    
    def startup(self):
        """Initialize screen"""
        if self.hotkey_manager:
            self.update_profile_display()
            self.current_category = 'all'
            self.update_hotkey_list()
        else:
            self["profile_label"].setText("ERROR")
            self["hotkey_list"].setList([("Hotkey manager not available", None)])
            self["action_info"].setText("Cannot load hotkey configuration")
        
        # Update subtitle-specific display
        self.update_subtitle_status()
    
    def update_subtitle_status(self):
        """Update subtitle-specific status display"""
        try:
            p = config.plugins.wgfilemanager
            
            if hasattr(p, 'subtitle_hotkeys_enabled'):
                enabled = p.subtitle_hotkeys_enabled.value
                status = "ENABLED" if enabled else "DISABLED"
                color = "#00ff00" if enabled else "#ff0000"
                
                # Update info label with subtitle status
                current_info = self["action_info"].text
                if "Subtitle hotkeys:" not in current_info:
                    status_text = f"Subtitle hotkeys: {status}"
                    self["action_info"].setText(status_text)
            
        except Exception as e:
            logger.debug(f"Error updating subtitle status: {e}")
    
    def update_profile_display(self):
        """Update profile information display"""
        if not self.hotkey_manager:
            return
        
        profile_info = self.hotkey_manager.get_profile_info()
        profile_text = f"{profile_info.get('name', 'Unknown')} ({profile_info.get('hotkey_count', 0)} hotkeys)"
        self["profile_label"].setText(profile_text)
    
    def update_hotkey_list(self, category='all'):
        """Update hotkey list display with category filtering"""
        if not self.hotkey_manager:
            return
        
        try:
            profile_info = self.hotkey_manager.get_profile_info()
            hotkeys = profile_info.get("hotkeys", {})
            
            # Define subtitle-related actions
            subtitle_actions = [
                'toggle_subtitle', 'open_subtitle_menu', 'open_subtitle_settings',
                'subtitle_delay_up', 'subtitle_delay_down', 'subtitle_reset_delay',
                'subtitle_style_menu', 'subtitle_download', 'subtitle_convert',
                'cycle_subtitle_track', 'toggle_subtitle_position',
            ]
            
            hotkey_items = []
            for action_id, config in hotkeys.items():
                key = config.get("key", "None")
                label = config.get("label", action_id)
                action = config.get("action", "")
                
                # Check if this is a subtitle action
                is_subtitle = any(sub_action in action_id.lower() or sub_action in action.lower() 
                                 for sub_action in ['subtitle', 'delay', 'style', 'track'])
                
                # Apply category filtering
                if category == 'subtitle' and not is_subtitle:
                    continue
                elif category == 'basic' and not is_subtitle:
                    continue
                elif category == 'delay' and 'delay' not in action_id.lower():
                    continue
                elif category == 'style' and 'style' not in action_id.lower():
                    continue
                
                # Format display with icon for subtitle actions
                display_key = key.upper().replace("_", " ")
                if is_subtitle:
                    display_text = f" {display_key:15} → {label}"
                else:
                    display_text = f"  {display_key:15} → {label}"
                
                hotkey_items.append((display_text, {
                    "action_id": action_id,
                    "key": key,
                    "label": label,
                    "action": action,
                    "description": config.get("description", ""),
                    "is_subtitle": is_subtitle
                }))
            
            # Sort by key
            hotkey_items.sort(key=lambda x: x[1]["key"])
            
            self["hotkey_list"].setList(hotkey_items)
            
            # Update category label
            category_names = {
                'all': 'All Hotkeys',
                'subtitle': 'Subtitle Hotkeys',
                'basic': 'Basic Subtitle',
                'delay': 'Delay Adjustment',
                'style': 'Style Controls',
                'playback': 'Playback Controls',
            }
            self["category_label"].setText(category_names.get(category, 'All Hotkeys'))
            
        except Exception as e:
            logger.error(f"Error updating hotkey list: {e}")
            self["hotkey_list"].setList([("Error loading hotkeys", None)])
    
    def change_category(self):
        """Change hotkey category filter"""
        categories = [
            (" All Hotkeys", "all"),
            (" Subtitle Hotkeys", "subtitle"),
            (" Delay Adjustment", "delay"),
            (" Style Controls", "style"),
            ("▶ Playback Controls", "playback"),
            (" Audio Controls", "audio"),
            (" System Controls", "system"),
        ]
        
        self.session.openWithCallback(
            self._category_selected,
            ChoiceBox,
            title="Select Category",
            list=categories
        )
    
    def _category_selected(self, choice):
        """Handle category selection"""
        if not choice:
            return
        
        self.current_category = choice[1]
        self.update_hotkey_list(self.current_category)
    
    def prev_category(self):
        """Go to previous category"""
        categories = ['all', 'subtitle', 'delay', 'style', 'playback', 'audio', 'system']
        if self.current_category in categories:
            current_index = categories.index(self.current_category)
            new_index = (current_index - 1) % len(categories)
            self.current_category = categories[new_index]
            self.update_hotkey_list(self.current_category)
    
    def next_category(self):
        """Go to next category"""
        categories = ['all', 'subtitle', 'delay', 'style', 'playback', 'audio', 'system']
        if self.current_category in categories:
            current_index = categories.index(self.current_category)
            new_index = (current_index + 1) % len(categories)
            self.current_category = categories[new_index]
            self.update_hotkey_list(self.current_category)
    
    def key_up(self):
        """Handle up key"""
        self["hotkey_list"].up()
        self._update_selected_info()
    
    def key_down(self):
        """Handle down key"""
        self["hotkey_list"].down()
        self._update_selected_info()
    
    def _update_selected_info(self):
        """Update info for currently selected hotkey"""
        current = self["hotkey_list"].getCurrent()
        if not current or not current[1]:
            return
        
        hotkey_info = current[1]
        
        # Update info display
        info_text = f"Action: {hotkey_info['label']}\n"
        info_text += f"Key: {hotkey_info['key']}\n"
        info_text += f"ID: {hotkey_info['action']}\n"
        
        if hotkey_info.get("description"):
            info_text += f"\n{hotkey_info['description']}"
        
        # Add subtitle-specific info
        if hotkey_info.get("is_subtitle"):
            info_text += "\n\n Subtitle Control"
        
        self["action_info"].setText(info_text)
    
    def select_hotkey(self):
        """Select a hotkey for editing"""
        current = self["hotkey_list"].getCurrent()
        if not current or not current[1]:
            return
        
        hotkey_info = current[1]
        self.editing_action = hotkey_info["action_id"]
        
        # Update info display
        self._update_selected_info()
        
        # Offer to change key
        self.session.openWithCallback(
            self._confirm_change_key,
            MessageBox,
            f"Change key for '{hotkey_info['label']}'?\n\nCurrent key: {hotkey_info['key']}",
            MessageBox.TYPE_YESNO
        )
    
    def _confirm_change_key(self, confirmed):
        """Confirm key change"""
        if confirmed and self.editing_action:
            self.show_key_selection()
    
    def change_key(self):
        """Change key for selected hotkey"""
        current = self["hotkey_list"].getCurrent()
        if not current or not current[1]:
            self.session.open(
                MessageBox,
                "Please select a hotkey first",
                MessageBox.TYPE_WARNING,
                timeout=2
            )
            return
        
        self.select_hotkey()
    
    def show_key_selection(self):
        """Show key selection dialog with subtitle-specific options"""
        if not self.editing_action:
            return
        
        # Available keys for mapping
        available_keys = [
            # Subtitle-specific keys
            (" Subtitle", "subtitle"),
            (" Text", "text"),
            (" Audio", "audio"),
            ("ℹ Info", "info"),
            
            # Color buttons
            (" Red", "red"),
            (" Green", "green"),
            (" Yellow", "yellow"),
            (" Blue", "blue"),
            
            # Number keys (for quick delay)
            ("1⃣ 1", "1"),
            ("2⃣ 2", "2"),
            ("3⃣ 3", "3"),
            ("4⃣ 4", "4"),
            ("5⃣ 5", "5"),
            ("6⃣ 6", "6"),
            ("7⃣ 7", "7"),
            ("8⃣ 8", "8"),
            ("9⃣ 9", "9"),
            ("0⃣ 0", "0"),
            
            # Navigation keys
            (" Up", "up"),
            (" Down", "down"),
            (" Left", "left"),
            (" Right", "right"),
            ("[OK] OK", "ok"),
            ("[X] Exit", "exit"),
            
            # Special function keys
            (" EPG", "epg"),
            (" Radio", "radio"),
            (" TV", "tv"),
            (" Video", "video"),
            (" Menu", "menu"),
            (" Help", "help"),
            (" Screenshot", "screenshot"),
            (" Record", "record"),
            
            # Long press variants
            ("Long Subtitle", "long_subtitle"),
            ("Long Text", "long_text"),
            ("Long Audio", "long_audio"),
            ("Long Info", "long_info"),
        ]
        
        self.session.openWithCallback(
            self._key_selected,
            ChoiceBox,
            title="Select New Key",
            list=available_keys
        )
    
    def _key_selected(self, choice):
        """Handle key selection"""
        if not choice or not self.editing_action:
            return
        
        new_key = choice[1]
        
        # Update configuration
        if self.hotkey_manager and self.hotkey_manager.config:
            profile = self.hotkey_manager.config.get("hotkey_profiles", {}).get(self.current_profile, {})
            hotkeys = profile.get("hotkeys", {})
            
            if self.editing_action in hotkeys:
                hotkeys[self.editing_action]["key"] = new_key
                
                # Rebuild hotkey map
                self.hotkey_manager._build_hotkey_map()
                
                # Update display
                self.update_hotkey_list(self.current_category)
                self._update_selected_info()
                
                self.session.open(
                    MessageBox,
                    f"[OK] Key changed to: {new_key.upper()}",
                    MessageBox.TYPE_INFO,
                    timeout=2
                )
        
        self.editing_action = None
    
    def subtitle_special(self):
        """Subtitle-specific hotkey configuration"""
        options = [
            (" Subtitle Hotkey Settings", "subtitle_settings"),
            (" Quick Delay Keys", "delay_keys"),
            (" Style Control Keys", "style_keys"),
            (" Reset Subtitle Keys", "reset_subtitle"),
            (" Advanced Options", "advanced"),
            (" Subtitle Key Cheat Sheet", "cheat_sheet"),
        ]
        
        self.session.openWithCallback(
            self._subtitle_option_selected,
            ChoiceBox,
            title="Subtitle Hotkey Options",
            list=options
        )
    
    def _subtitle_option_selected(self, choice):
        """Handle subtitle option selection"""
        if not choice:
            return
        
        option = choice[1]
        
        if option == "subtitle_settings":
            self.configure_subtitle_settings()
        elif option == "delay_keys":
            self.configure_delay_keys()
        elif option == "style_keys":
            self.configure_style_keys()
        elif option == "reset_subtitle":
            self.reset_subtitle_keys()
        elif option == "advanced":
            self.advanced_subtitle_options()
        elif option == "cheat_sheet":
            self.show_subtitle_cheat_sheet()
    
    def configure_subtitle_settings(self):
        """Configure subtitle-specific settings"""
        try:
            p = config.plugins.wgfilemanager
            
            options = [
                ("Enable Subtitle Hotkeys", p.subtitle_hotkeys_enabled),
                ("Subtitle Toggle Key", p.subtitle_toggle_key),
                ("Subtitle Menu Key", p.subtitle_menu_key),
                ("Long Press Delay", p.subtitle_long_press_delay),
            ]
            
            # Show configuration dialog
            from Components.ConfigList import ConfigListScreen
            from Components.config import getConfigListEntry
            
            config_list = []
            for label, config_item in options:
                config_list.append(getConfigListEntry(label, config_item))
            
            class SubtitleConfigScreen(ConfigListScreen, Screen):
                def __init__(self, session, config_list):
                    Screen.__init__(self, session)
                    self.config_list = config_list
                    
                    self.skin = """
                    <screen position="center,center" size="600,400" title="Subtitle Hotkey Settings">
                        <widget name="config" position="10,10" size="580,300" />
                        <eLabel position="0,320" size="600,80" backgroundColor="#000000" />
                        <widget name="red" position="10,330" size="140,30" font="Regular;20" halign="center" backgroundColor="#9f1313" />
                        <widget name="green" position="160,330" size="140,30" font="Regular;20" halign="center" backgroundColor="#1f771f" />
                    </screen>"""
                    
                    self["config"] = ConfigList(self.config_list)
                    self["red"] = Label("Cancel")
                    self["green"] = Label("Save")
                    
                    self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
                        "cancel": self.cancel,
                        "save": self.save,
                        "red": self.cancel,
                        "green": self.save,
                    })
                
                def cancel(self):
                    self.close()
                
                def save(self):
                    from Components.config import configfile
                    configfile.save()
                    self.session.open(
                        MessageBox,
                        "[OK] Subtitle settings saved!",
                        MessageBox.TYPE_INFO,
                        timeout=2
                    )
                    self.close()
            
            self.session.open(SubtitleConfigScreen, config_list)
            
        except Exception as e:
            logger.error(f"Error configuring subtitle settings: {e}")
            self.session.open(
                MessageBox,
                f"Error: {e}",
                MessageBox.TYPE_ERROR
            )
    
    def configure_delay_keys(self):
        """Configure subtitle delay adjustment keys"""
        options = [
            ("Increase Delay (+1s)", "Configure key to INCREASE subtitle delay"),
            ("Decrease Delay (-1s)", "Configure key to DECREASE subtitle delay"),
            ("Quick Adjustment Set", "Configure 1,2,3,7,8,9 keys for quick delay"),
            ("Reset Delay Key", "Configure key to reset delay to zero"),
        ]
        
        self.session.openWithCallback(
            self._delay_option_selected,
            ChoiceBox,
            title="Configure Delay Keys",
            list=[(opt[0], idx) for idx, opt in enumerate(options)]
        )
    
    def _delay_option_selected(self, choice):
        """Handle delay option selection"""
        if not choice:
            return
        
        option_idx = choice[1]
        option_text = [
            "Increase Delay (+1s)",
            "Decrease Delay (-1s)", 
            "Quick Adjustment Set",
            "Reset Delay Key"
        ][option_idx]
        
        if option_idx == 0:  # Increase delay
            keys = [("8 Key", "8"), ("RIGHT Arrow", "right"), ("CHANNEL UP", "channelup")]
            self._configure_single_key("subtitle_delay_up", keys, "Increase Delay")
        elif option_idx == 1:  # Decrease delay
            keys = [("2 Key", "2"), ("LEFT Arrow", "left"), ("CHANNEL DOWN", "channeldown")]
            self._configure_single_key("subtitle_delay_down", keys, "Decrease Delay")
        elif option_idx == 2:  # Quick adjustment set
            self.configure_quick_delay_set()
        elif option_idx == 3:  # Reset delay
            keys = [("5 Key", "5"), ("0 Key", "0"), ("OK Button", "ok")]
            self._configure_single_key("subtitle_reset_key", keys, "Reset Delay")
    
    def _configure_single_key(self, config_name, key_options, description):
        """Configure a single key setting"""
        self.session.openWithCallback(
            lambda choice: self._save_single_key(config_name, choice, description),
            ChoiceBox,
            title=f"Select key for {description}",
            list=key_options
        )
    
    def _save_single_key(self, config_name, choice, description):
        """Save single key configuration"""
        if not choice:
            return
        
        try:
            p = config.plugins.wgfilemanager
            if not hasattr(p, config_name):
                # Create config entry if it doesn't exist
                setattr(p, config_name, ConfigSelection(default=choice[1], choices=[(k[1], k[0]) for k in [
                    ("8 Key", "8"), ("2 Key", "2"), ("5 Key", "5"),
                    ("RIGHT Arrow", "right"), ("LEFT Arrow", "left"),
                    ("CHANNEL UP", "channelup"), ("CHANNEL DOWN", "channeldown"),
                ]]))
            
            getattr(p, config_name).value = choice[1]
            
            from Components.config import configfile
            configfile.save()
            
            self.session.open(
                MessageBox,
                f"[OK] {description} key set to: {choice[0]}",
                MessageBox.TYPE_INFO,
                timeout=2
            )
            
        except Exception as e:
            logger.error(f"Error saving key config: {e}")
            self.session.open(
                MessageBox,
                f"Error: {e}",
                MessageBox.TYPE_ERROR
            )
    
    def configure_quick_delay_set(self):
        """Configure quick delay adjustment keys (1,2,3,7,8,9)"""
        config_options = [
            ("1 Key (-5s)", "subtitle_key_1", "-5 seconds"),
            ("2 Key (-1s)", "subtitle_key_2", "-1 second"),
            ("3 Key (-0.1s)", "subtitle_key_3", "-0.1 second"),
            ("7 Key (+0.1s)", "subtitle_key_7", "+0.1 second"),
            ("8 Key (+1s)", "subtitle_key_8", "+1 second"),
            ("9 Key (+5s)", "subtitle_key_9", "+5 seconds"),
        ]
        
        options_list = [(opt[0], idx) for idx, opt in enumerate(config_options)]
        
        self.session.openWithCallback(
            lambda choice: self._configure_quick_delay_key(choice, config_options),
            ChoiceBox,
            title="Configure Quick Delay Key",
            list=options_list
        )
    
    def _configure_quick_delay_key(self, choice, config_options):
        """Configure individual quick delay key"""
        if not choice:
            return
        
        idx = choice[1]
        config_name, description = config_options[idx][1], config_options[idx][2]
        
        action_options = [
            (f"Delay {description}", f"delay_{description.replace(' ', '_').replace('.', '')}"),
            ("Toggle Subtitles", "toggle_subtitle"),
            ("Subtitle Menu", "subtitle_menu"),
            ("Cycle Subtitles", "cycle_subtitle"),
            ("No Action", "none"),
        ]
        
        self.session.openWithCallback(
            lambda action_choice: self._save_quick_delay_key(config_name, action_choice, description),
            ChoiceBox,
            title=f"Set action for {config_options[idx][0]}",
            list=action_options
        )
    
    def _save_quick_delay_key(self, config_name, choice, description):
        """Save quick delay key configuration"""
        if not choice:
            return
        
        # This would update the hotkey configuration
        # For now, show a message
        self.session.open(
            MessageBox,
            f"[OK] {description} action set\n\nNote: Update hotkey manager to implement",
            MessageBox.TYPE_INFO,
            timeout=3
        )
    
    def configure_style_keys(self):
        """Configure subtitle style control keys"""
        options = [
            ("Cycle Font Size", "Configure key to cycle through font sizes"),
            ("Cycle Font Color", "Configure key to cycle through colors"),
            ("Toggle Background", "Configure key to toggle subtitle background"),
            ("Change Position", "Configure key to change subtitle position"),
        ]
        
        self.session.openWithCallback(
            lambda choice: self._show_style_key_options(choice),
            ChoiceBox,
            title="Configure Style Keys",
            list=[(opt[0], idx) for idx, opt in enumerate(options)]
        )
    
    def _show_style_key_options(self, choice):
        """Show options for style key configuration"""
        if not choice:
            return
        
        # This would implement style key configuration
        # For now, show placeholder
        self.session.open(
            MessageBox,
            "Style key configuration will be implemented in next version",
            MessageBox.TYPE_INFO,
            timeout=2
        )
    
    def reset_subtitle_keys(self):
        """Reset all subtitle keys to defaults"""
        self.session.openWithCallback(
            self._confirm_reset_subtitle,
            MessageBox,
            "Reset ALL subtitle hotkeys to defaults?\n\nThis will erase all custom subtitle key mappings!",
            MessageBox.TYPE_YESNO
        )
    
    def _confirm_reset_subtitle(self, confirmed):
        """Confirm subtitle key reset"""
        if not confirmed:
            return
        
        try:
            # Reset subtitle-specific configs
            p = config.plugins.wgfilemanager
            
            if hasattr(p, 'subtitle_toggle_key'):
                p.subtitle_toggle_key.value = "subtitle"
            if hasattr(p, 'subtitle_menu_key'):
                p.subtitle_menu_key.value = "text"
            if hasattr(p, 'subtitle_delay_up_key'):
                p.subtitle_delay_up_key.value = "8"
            if hasattr(p, 'subtitle_delay_down_key'):
                p.subtitle_delay_down_key.value = "2"
            
            # Save config
            from Components.config import configfile
            configfile.save()
            
            # Reset hotkey manager subtitle keys
            if self.hotkey_manager:
                self.hotkey_manager.reset_subtitle_keys()
                self.update_hotkey_list(self.current_category)
            
            self.session.open(
                MessageBox,
                "[OK] All subtitle hotkeys reset to defaults!",
                MessageBox.TYPE_INFO,
                timeout=2
            )
            
        except Exception as e:
            logger.error(f"Error resetting subtitle keys: {e}")
            self.session.open(
                MessageBox,
                f"Error: {e}",
                MessageBox.TYPE_ERROR
            )
    
    def advanced_subtitle_options(self):
        """Show advanced subtitle options"""
        options = [
            ("Import Subtitle Profile", "import_profile"),
            ("Export Subtitle Profile", "export_profile"),
            ("Create Subtitle Profile", "create_profile"),
            ("Test Subtitle Hotkeys", "test_hotkeys"),
            ("Subtitle Key Statistics", "statistics"),
        ]
        
        self.session.openWithCallback(
            self._advanced_option_selected,
            ChoiceBox,
            title="Advanced Subtitle Options",
            list=options
        )
    
    def _advanced_option_selected(self, choice):
        """Handle advanced option selection"""
        if not choice:
            return
        
        option = choice[1]
        
        if option == "import_profile":
            self.import_subtitle_profile()
        elif option == "export_profile":
            self.export_subtitle_profile()
        elif option == "create_profile":
            self.create_subtitle_profile()
        elif option == "test_hotkeys":
            self.test_subtitle_hotkeys()
        elif option == "statistics":
            self.show_subtitle_statistics()
    
    def import_subtitle_profile(self):
        """Import subtitle-specific profile"""
        self.session.open(
            MessageBox,
            "Subtitle profile import will be available in next version",
            MessageBox.TYPE_INFO,
            timeout=2
        )
    
    def export_subtitle_profile(self):
        """Export subtitle-specific profile"""
        self.session.open(
            MessageBox,
            "Subtitle profile export will be available in next version",
            MessageBox.TYPE_INFO,
            timeout=2
        )
    
    def create_subtitle_profile(self):
        """Create subtitle-specific profile"""
        self.session.open(
            MessageBox,
            "Subtitle profile creation will be available in next version",
            MessageBox.TYPE_INFO,
            timeout=2
        )
    
    def test_subtitle_hotkeys(self):
        """Test subtitle hotkeys"""
        test_instructions = """
         SUBTITLE HOTKEY TEST MODE
        
        Press these keys to test:
        
        BASIC CONTROLS:
        • SUBTITLE: Toggle subtitles on/off
        • TEXT: Open subtitle menu
        • AUDIO: Open audio menu
        
        QUICK DELAY (if configured):
        • 1: -5 seconds
        • 2: -1 second  
        • 3: -0.1 second
        • 7: +0.1 second
        • 8: +1 second
        • 9: +5 seconds
        
        STYLE CONTROLS:
        • INFO: Cycle font size
        • EPG: Cycle font color
        • TV: Toggle background
        • RADIO: Change position
        
        Press OK to exit test mode.
        """
        
        from Screens.ScrollLabel import ScrollLabel
        
        class TestScreen(ScrollLabel):
            def __init__(self, session, text):
                ScrollLabel.__init__(self, session, text)
                self["actions"] = ActionMap(["OkCancelActions"], {
                    "ok": self.close,
                    "cancel": self.close
                }, -1)
        
        self.session.open(TestScreen, test_instructions)
    
    def show_subtitle_statistics(self):
        """Show subtitle key statistics"""
        if not self.hotkey_manager:
            return
        
        profile_info = self.hotkey_manager.get_profile_info()
        hotkeys = profile_info.get("hotkeys", {})
        
        # Count subtitle hotkeys
        subtitle_count = 0
        delay_count = 0
        style_count = 0
        
        for action_id, config in hotkeys.items():
            action = config.get("action", "").lower()
            label = config.get("label", "").lower()
            
            if any(word in action or word in label for word in ['subtitle', 'sub', 'caption']):
                subtitle_count += 1
            
            if 'delay' in action or 'delay' in label:
                delay_count += 1
            
            if any(word in action or word in label for word in ['style', 'font', 'color', 'position']):
                style_count += 1
        
        total_hotkeys = len(hotkeys)
        
        stats_text = f"""
         SUBTITLE HOTKEY STATISTICS
        
        Profile: {profile_info.get('name', 'Unknown')}
        Total Hotkeys: {total_hotkeys}
        
        Subtitle Hotkeys: {subtitle_count} ({subtitle_count/total_hotkeys*100:.0f}%)
        • Delay Controls: {delay_count}
        • Style Controls: {style_count}
        • Basic Controls: {subtitle_count - delay_count - style_count}
        
        Most Common Keys:
        • SUBTITLE: Toggle on/off
        • TEXT: Open menu  
        • 1-3,7-9: Quick delay
        • INFO: Style cycling
        
        Configuration File:
        /etc/enigma2/wgfilemanager_hotkeys.json
        """
        
        from Screens.ScrollLabel import ScrollLabel
        
        class StatsScreen(ScrollLabel):
            def __init__(self, session, text):
                ScrollLabel.__init__(self, session, text)
                self["actions"] = ActionMap(["OkCancelActions"], {
                    "ok": self.close,
                    "cancel": self.close
                }, -1)
        
        self.session.open(StatsScreen, stats_text)
    
    def show_subtitle_cheat_sheet(self):
        """Show subtitle hotkey cheat sheet"""
        cheat_sheet = """
         SUBTITLE HOTKEY CHEAT SHEET
        
        ===== BASIC CONTROLS =====
        SUBTITLE      Toggle subtitles on/off
        TEXT          Open subtitle menu
        AUDIO         Open audio track menu
        INFO          Show signal info
        
        ===== QUICK DELAY ADJUSTMENT =====
        1             -5 seconds
        2             -1 second
        3             -0.1 second (100ms)
        7             +0.1 second (100ms)
        8             +1 second
        9             +5 seconds
        5             Reset delay to 0
        
        ===== STYLE CONTROLS =====
        Long INFO     Cycle font size
        Long EPG      Cycle font color
        Long TV       Toggle background
        Long RADIO    Change position
        
        ===== ADVANCED CONTROLS =====
        Long SUBTITLE Advanced subtitle menu
        Long TEXT     Subtitle tools
        Long AUDIO    Jump back 30s
        Long INFO     Extended info
        
        ===== COLOR BUTTONS =====
        RED           Signal monitor / Mark IN
        GREEN         Catchup / Mark OUT
        YELLOW        Refresh service
        BLUE          Jump menu / Chapters
        
        ===== LONG PRESS VARIANTS =====
        Add 'long_' prefix to any key for alternate function
        
        TIPS:
        • Customize keys in Hotkey Settings
        • Create profiles for different needs
        • Export your configuration
        • Test keys in player first
        """
        
        from Screens.ScrollLabel import ScrollLabel
        
        class CheatSheetScreen(ScrollLabel):
            def __init__(self, session, text):
                ScrollLabel.__init__(self, session, text)
                self["actions"] = ActionMap(["OkCancelActions"], {
                    "ok": self.close,
                    "cancel": self.close
                }, -1)
        
        self.session.open(CheatSheetScreen, cheat_sheet)
    
    # Keep existing methods for profile management, saving, etc.
    # ... (rest of your existing methods remain the same, just add the new ones above)
    
    def change_profile(self):
        """Change hotkey profile"""
        if not self.hotkey_manager:
            self.session.open(
                MessageBox,
                "Hotkey manager not available",
                MessageBox.TYPE_ERROR,
                timeout=2
            )
            return
        
        profiles = self.hotkey_manager.get_available_profiles()
        
        if not profiles:
            self.session.open(
                MessageBox,
                "No profiles available",
                MessageBox.TYPE_WARNING,
                timeout=2
            )
            return
        
        profile_items = []
        for profile in profiles:
            # Count subtitle hotkeys in this profile
            subtitle_count = 0
            hotkeys = profile.get("hotkeys", {})
            for action_id, config in hotkeys.items():
                if any(word in action_id.lower() or word in config.get("action", "").lower() 
                      for word in ['subtitle', 'delay', 'style']):
                    subtitle_count += 1
            
            display = f"{profile['name']} ({len(hotkeys)} keys, {subtitle_count} subtitle)"
            profile_items.append((display, profile["id"]))
        
        self.session.openWithCallback(
            self._profile_selected,
            ChoiceBox,
            title="Select Profile",
            list=profile_items
        )
    
    def _profile_selected(self, choice):
        """Handle profile selection"""
        if not choice:
            return
        
        profile_id = choice[1]
        
        if self.hotkey_manager.set_profile(profile_id):
            self.current_profile = profile_id
            self.update_profile_display()
            self.update_hotkey_list(self.current_category)
            
            self.session.open(
                MessageBox,
                f"Switched to profile: {choice[0]}",
                MessageBox.TYPE_INFO,
                timeout=2
            )
    
    def save_config(self):
        """Save hotkey configuration"""
        if not self.hotkey_manager:
            self.session.open(
                MessageBox,
                "Cannot save: Hotkey manager not available",
                MessageBox.TYPE_ERROR,
                timeout=2
            )
            return
        
        # Save subtitle-specific configs first
        try:
            from Components.config import configfile
            configfile.save()
            logger.info("Subtitle hotkey configuration saved")
        except Exception as e:
            logger.error(f"Error saving subtitle config: {e}")
        
        # Save main hotkey configuration
        if self.hotkey_manager.save_config():
            self.session.open(
                MessageBox,
                "[OK] Hotkey configuration saved!\n\nSubtitle keys are ready to use.",
                MessageBox.TYPE_INFO,
                timeout=3
            )
        else:
            self.session.open(
                MessageBox,
                "Failed to save configuration",
                MessageBox.TYPE_ERROR,
                timeout=2
            )
    
    def exit_screen(self):
        """Exit the setup screen"""
        # Check for unsaved changes
        self.session.openWithCallback(
            self._confirm_exit,
            MessageBox,
            "Exit hotkey setup?\n\nAny unsaved changes will be lost!",
            MessageBox.TYPE_YESNO
        )
    
    def _confirm_exit(self, confirmed):
        """Confirm exit"""
        if confirmed:
            self.close()