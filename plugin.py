#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WG File Manager PRO v1.1 - Professional File Manager for Enigma2
Enhanced with Smart Context Menus, Remote Access & Subtitle Support
"""

import sys
import traceback
import os

# ===== ENIGMA2 IMPORTS =====
try:
    from Plugins.Plugin import PluginDescriptor  # <-- CRITICAL: This was missing!
    from Screens.MessageBox import MessageBox
except ImportError as e:
    print("[WGFileManager FATAL] Cannot import Enigma2 modules: %s" % str(e))
    print("[WGFileManager FATAL] This plugin only runs within Enigma2 environment")
    sys.exit(1)

# ===== FIX 1: Python 2 compatibility =====
PY2 = sys.version_info[0] == 2
if not PY2:
    print("[WGFileManager] WARNING: Enigma2 typically uses Python 2.7")

# ===== FIX 2: Safe translation setup =====
try:
    from Components.Language import language  # was: import language (no such top-level module)
    from Tools.Directories import resolveFilename, SCOPE_PLUGINS
    import gettext
    
    # Get language without overriding system env
    lang = language.getLanguage()[:2]
    
    # Setup translation properly
    domain = "enigma2"
    gettext.bindtextdomain(domain, resolveFilename(SCOPE_PLUGINS))
    gettext.textdomain(domain)
    
    # Create translation function
    def _(txt):
        if PY2:
            return gettext.gettext(txt).decode('utf-8')
        return gettext.gettext(txt)
        
except ImportError as e:
    print("[WGFileManager] Translation import error: %s" % str(e))
    # Fallback: no translation
    def _(txt):
        if PY2 and isinstance(txt, str):
            return txt.decode('utf-8', errors='ignore')
        return txt

# ===== FIX 3: Robust logging setup =====
try:
    # Try absolute import (installed mode)
    from Plugins.Extensions.WGFileManager.utils.logging_config import setup_logging, get_logger
    try:
        setup_logging()  # was imported but never called: no log file was ever created
    except Exception as _le:
        print("[WGFileManager] logging setup failed: %s" % _le)
    logger = get_logger(__name__)
    logger.debug("Using absolute import for logging")
    
except ImportError:
    try:
        # Try relative import (development mode)
        from .utils.logging_config import setup_logging, get_logger
        try:
            setup_logging()
        except Exception as _le:
            print("[WGFileManager] logging setup failed: %s" % _le)
        logger = get_logger(__name__)
        logger.debug("Using relative import for logging")
        
    except ImportError as e:
        # Ultimate fallback
        import logging
        logging.basicConfig(
            level=logging.WARNING,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            filename='/tmp/wgfilemanager_fallback.log'
        )
        logger = logging.getLogger(__name__)
        logger.error("Failed to setup proper logging: %s" % str(e))

# ===== FIX 4: player module (round-25: single AjPanel player) =====
try:
    from .player.custom_media_player import CustomMediaPlayer  # noqa: F401
    logger.info("Player module imported successfully")
except ImportError as e:
    logger.error((("Error importing player module: " + "{e}").format(e=(e))))
    CustomMediaPlayer = None

from Components.config import config, ConfigSubsection

def main(session, **kwargs):
    """Main entry point for the plugin"""
    logger.info("=" * 60)
    logger.info("Starting WG File Manager PRO v1.1 - Subtitle Edition")
    logger.info("Python %s on %s" % (sys.version, sys.platform))
    
    try:
        # Initialize config to ensure all settings are registered
        from Plugins.Extensions.WGFileManager.core.config import WGFileManagerConfig
        config_manager = WGFileManagerConfig()
        config_manager.setup_config()
        
        # Verify subtitle configuration exists
        _verify_subtitle_config()
        
        # Try to import main screen
        logger.info("Attempting to import WGFileManagerMain...")
        
        try:
            from Plugins.Extensions.WGFileManager.ui.main_screen import WGFileManagerMain
            logger.info("✓ Successfully imported WGFileManagerMain")
            
        except ImportError as ie:
            # Try relative import as fallback
            logger.warning("Absolute import failed, trying relative...")
            try:
                from .ui.main_screen import WGFileManagerMain
                logger.info("✓ Successfully imported WGFileManagerMain (relative)")
            except ImportError:
                logger.error("✗ ALL import attempts failed")
                logger.error("Import error details: %s" % str(ie))
                logger.error("Python path: %s" % str(sys.path))
                logger.error("Full traceback:\n%s" % traceback.format_exc())
                raise
        
        # Open the main screen
        logger.info("Opening WGFileManagerMain screen...")
        session.open(WGFileManagerMain)
        logger.info("✓ WGFileManager started successfully")
        logger.info("Subtitle features: ✓ Auto-load, ✓ SRT/SUB/ASS/VTT, ✓ Delay adjustment")
        
    except Exception as e:
        error_msg = "Failed to start WGFileManager: %s" % str(e)
        error_trace = traceback.format_exc()
        
        logger.error(error_msg)
        logger.error("Traceback:\n%s" % error_trace)
        
        # Show error to user
        try:
            session.open(
                MessageBox,
                _("Failed to start WGFileManager") + ":\n\n%s\n\n%s" % (
                    str(e)[:100], 
                    _("Check /tmp/wgfilemanager.log for details")
                ),
                MessageBox.TYPE_ERROR,
                timeout=10
            )
        except Exception as msg_error:
            logger.error("Could not show error message: %s" % str(msg_error))
        
        return None

def _verify_subtitle_config():
    """Verify the plugin's config subsection is registered.

    BUG-5 fix: the standalone CustomMediaPlayer no longer reads any
    subtitle_* config keys (subtitle_delay / subtitle_font_size /
    subtitle_font_color / subtitle_position / subtitle_encoding /
    subtitle_auto_load / subtitle_preferred_lang). They were leftovers
    from the vendored subtitle engine and were removed from
    core/config.py. So this function no longer audits those keys; it
    just ensures config.plugins.wgfilemanager exists so the player
    and the settings screen can register their own keys at import
    time. The misleading "subtitle config verified" log line is gone.
    """
    try:
        if not hasattr(config.plugins, 'wgfilemanager'):
            config.plugins.wgfilemanager = ConfigSubsection()
            logger.info("Created wgfilemanager config subsection")
        logger.info("Plugin config subsection registered")
    except Exception as e:
        logger.error((("Error verifying plugin config: " + "{e}").format(e=(e))))

def menu(menuid, **kwargs):
    """Plugin menu integration"""
    if menuid == "mainmenu":
        return [(_("WG File Manager PRO"), main, "wgfilemanager", 46)]
    return []

def Plugins(**kwargs):
    """Plugin descriptor with subtitle feature listing"""
    description = _("WG File Manager PRO - Advanced File Management with Subtitle Support")
    
    # Extended description with features
    extended_description = _("""
Advanced file manager with dual pane interface.
Features:
• File operations (copy, move, delete, rename)
• Media player with subtitle support (SRT, SUB, ASS, VTT)
• Network access (FTP, SFTP, WebDAV, SMB)
• Archive support (ZIP, TAR, RAR)
• Subtitle management with delay adjustment
• Auto-load subtitles for videos
• Hotkey configuration
""")
    
    # ===== FIX 5: Handle missing icon gracefully =====
    icon_path = None
    possible_icon_locations = [
        "/usr/lib/enigma2/python/Plugins/Extensions/WGFileManager/wgfilemanager.png",
        "/usr/share/enigma2/picon/wgfilemanager.png",
        "icons/blue.png",  # Use one of our icons as fallback
    ]
    
    for location in possible_icon_locations:
        try:
            if os.path.exists(location):
                icon_path = location
                logger.debug("Found icon at: %s" % location)
                break
        except:
            pass
    
    # Create plugin descriptors
    descriptors = []
    
    # Plugin menu entry
    descriptors.append(
        PluginDescriptor(
            name="WG File Manager PRO",
            description=description,
            where=PluginDescriptor.WHERE_PLUGINMENU,
            icon=icon_path,
            fnc=main
        )
    )
    
    # Main menu entry
    descriptors.append(
        PluginDescriptor(
            name="WG File Manager PRO",
            description=description,
            where=PluginDescriptor.WHERE_MENU,
            fnc=menu
        )
    )
    
    # Extended info in plugin browser (only on images that support it —
    # WHERE_PLUGINDB doesn't exist on Vu+/openATv and crashed the whole
    # plugin at startup, so now we ask first)
    if hasattr(PluginDescriptor, 'WHERE_PLUGINDB'):
        descriptors.append(
            PluginDescriptor(
                name="WG File Manager PRO",
                description=extended_description,
                where=PluginDescriptor.WHERE_PLUGINDB,
                icon=icon_path,
                fnc=main
            )
        )
    
    logger.info("Plugin descriptors created: %d entries" % len(descriptors))
    logger.info("Features advertised: Dual pane, Media player, Subtitle support, Network access")
    
    return descriptors

# ===== DEVELOPMENT & TESTING MODE =====
if __name__ == "__main__":
    # Test mode - only runs when executed directly
    print("=" * 60)
    print("WG File Manager PRO v1.1 - Test Mode")
    print("Subtitle Edition with full format support")
    print("=" * 60)
    print("Python version: %s" % sys.version)
    print("This plugin is designed to run within Enigma2.")
    print("Install path should be: /usr/lib/enigma2/python/Plugins/Extensions/WGFileManager/")
    print("=" * 60)
    
    # Test imports
    test_modules = [
        ("custom_media_player", "player.custom_media_player"),
        ("main_screen", "ui.main_screen"),
    ]
    
    print("\nTesting module imports:")
    print("-" * 40)
    
    all_imports_ok = True
    
    for module_name, import_path in test_modules:
        try:
            # Try absolute import
            exec((("import " + "{_a0}").format(_a0=(import_path.replace('/', '.')))))
            print((("✓ " + "{module_name:20}" + " - Import successful").format(module_name=(module_name))))
        except ImportError:
            try:
                # Try relative import
                exec((("from ." + "{import_path}" + " import *").format(import_path=(import_path))))
                print((("✓ " + "{module_name:20}" + " - Relative import successful").format(module_name=(module_name))))
            except ImportError as e:
                print((("✗ " + "{module_name:20}" + " - Import failed: " + "{e}").format(module_name=(module_name), e=(e))))
                all_imports_ok = False
    
    print("-" * 40)
    
    if all_imports_ok:
        print("✅ All critical modules import successfully!")
        print("\nKey Features Available:")
        print("  • Advanced Subtitle Menu UI")
        print("  • Auto-load subtitles for videos")
    else:
        print("⚠️  Some modules failed to import")
        print("Check that all files are in the correct location.")
    
    print("\nTo install:")
    print("1. Copy entire WGFileManager folder to:")
    print("   /usr/lib/enigma2/python/Plugins/Extensions/")
    print("2. Restart Enigma2 GUI")
    print("3. Access from Plugin Menu or Main Menu")
    
    print("\nSubtitle Usage:")
    print("• During playback: SUBTITLE button toggles subtitles")
    print("• During playback: TEXT button opens subtitle menu")
    print("• In file manager: 0 button on video files for options")
    print("• Quick delay: Use 1,2,3,7,8,9 keys during playback")
    
    print("=" * 60)
