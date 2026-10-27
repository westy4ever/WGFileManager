"""
Hotkey Manager for WGFileManager
Handles hotkey configuration, mapping, and execution
Location: core/hotkey_manager.py

Round-88 fixes:
  - best-effort bridge to the settings screen's config namespace
    (_read_player_config) for profile + long-press delay.
  - handle_key_press/release: long-press wins on timeout; the deferred
    short action never fires after a long press, and no pending-short
    entry survives a failed timer start.
  - _execute_action: lazy getattr dispatch (one missing method no
    longer kills every action).
  - _resolve_subtitle_manager: finds the real ``subtitleHandler``.
  - SubtitleHotkeyManager: fallback map deduplicated (was defined
    three times); stub actions routed through the real dispatcher.
  - reset_to_defaults persists the reset.

Round-91 audit (player-method alignment):
  - _PLAYER_ACTIONS: every entry was snake_case and/or pointed at
    methods that never existed on CustomMediaPlayer - ZERO of its 8
    entries resolved, so every player-action dispatch failed with
    "Player does not implement". Now maps to the player's real
    camelCase methods (toggleSubtitles / showSubtitleMenu /
    showAudioMenu / _showChapters). Ghost actions
    (open_subtitle_settings, open_subtitle_quick_menu,
    download_subtitles) are dropped - a JSON profile still binding
    them now logs "Unknown action", which is honest.
  - _SUBTITLE_MANAGER_ACTIONS: all three entries were ghosts
    (SubtitleHandler has no open_* methods). Left EMPTY - the
    dispatcher falls through safely.
  - _execute_subtitle_action: everything routes through the generic
    dispatcher now. The old toggle special-case called the handler
    directly, bypassing the player's toggleSubtitles() wrapper, so
    the SUB indicator and status line never refreshed.
  - _FALLBACK_KEY_MAP: "long_subtitle"/"long_text" pointed at ghost
    actions; remapped to actions that exist.
"""

import os
import json
import time
from collections import defaultdict
from threading import Timer

try:
    from enigma import eTimer  # fires on the enigma2 main loop -> UI-safe
    _E_TIMER_AVAILABLE = True
except ImportError:
    _E_TIMER_AVAILABLE = False

try:
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


# FIX (r88): best-effort bridge to the settings screen. The plugin config
# lives under config.plugins.wgfilemanager when the settings screen has
# run; if we cannot import it we simply keep the previous defaults. This
# is optional so this module still works in isolation.
def _read_player_config(key, default=None):
    try:
        from Components.config import config
        section = getattr(config.plugins, "wgfilemanager", None)
        if section is None:
            return default
        val = getattr(section, key, None)
        if val is None:
            return default
        return getattr(val, "value", val)
    except Exception:
        return default


class HotkeyManager:
    """Central hotkey management system"""

    def __init__(self, session):
        self.session = session
        self.config = None
        self.current_profile = "default"
        self.hotkey_map = {}
        self.long_press_timers = {}
        # FIX (r88): read the delay and profile from the settings screen's
        # config namespace if it's available; fall back to the old
        # hardcoded defaults otherwise.
        delay_ms = _read_player_config("hotkey_long_press_delay", "500")
        try:
            self.long_press_delay = max(0.05, int(delay_ms) / 1000.0)
        except (TypeError, ValueError):
            self.long_press_delay = 0.5
        profile = _read_player_config("hotkey_profile", "default")
        if isinstance(profile, str) and profile:
            self.current_profile = profile
        self._pending_short = {}  # key -> (action_config, player_instance)

        # Load configuration
        self._load_config()

        # Initialize hotkey map
        self._build_hotkey_map()

    def _load_config(self):
        """Load hotkey configuration from files"""
        try:
            # Default configuration path
            default_config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "default_hotkeys.json"
            )

            # User configuration path
            user_config_path = "/etc/enigma2/wgfilemanager_hotkeys.json"

            # Try to load user config first
            if os.path.exists(user_config_path):
                with open(user_config_path, 'r') as f:
                    self.config = json.load(f)
                logger.info(f"Loaded user hotkey config from {user_config_path}")
            elif os.path.exists(default_config_path):
                # Fallback to default config
                with open(default_config_path, 'r') as f:
                    self.config = json.load(f)
                logger.info(f"Loaded default hotkey config from {default_config_path}")
            else:
                # Create minimal config
                self.config = self._create_minimal_config()
                logger.warning("Created minimal hotkey config")

        except Exception as e:
            logger.error(f"Error loading hotkey config: {e}")
            self.config = self._create_minimal_config()

    def _create_minimal_config(self):
        """Create minimal configuration if files don't exist"""
        return {
            "version": "1.0",
            "hotkey_profiles": {
                "default": {
                    "name": "Default",
                    "hotkeys": {
                        "subtitle_toggle": {
                            "key": "subtitle",
                            "action": "toggle_subtitle",
                            "label": "Toggle Subtitles"
                        }
                    }
                }
            }
        }

    def _build_hotkey_map(self):
        """Build hotkey to action mapping"""
        self.hotkey_map = defaultdict(list)

        try:
            profile = self.config.get("hotkey_profiles", {}).get(self.current_profile, {})
            hotkeys = profile.get("hotkeys", {})

            for action_id, action_config in hotkeys.items():
                key = action_config.get("key")
                if key:
                    self.hotkey_map[key].append({
                        "action_id": action_id,
                        "action": action_config.get("action"),
                        "label": action_config.get("label", action_id),
                        "description": action_config.get("description", "")
                    })

            logger.info(f"Built hotkey map with {len(hotkeys)} actions")

        except Exception as e:
            logger.error(f"Error building hotkey map: {e}")

    def set_profile(self, profile_name):
        """Switch to a different hotkey profile"""
        try:
            if profile_name in self.config.get("hotkey_profiles", {}):
                self.current_profile = profile_name
                self._build_hotkey_map()
                logger.info(f"Switched to hotkey profile: {profile_name}")
                return True
            else:
                logger.error(f"Hotkey profile not found: {profile_name}")
                return False
        except Exception as e:
            logger.error(f"Error setting profile: {e}")
            return False

    def get_available_profiles(self):
        """Get list of available hotkey profiles"""
        try:
            profiles = self.config.get("hotkey_profiles", {})
            return [
                {
                    "id": profile_id,
                    "name": data.get("name", profile_id),
                    "description": data.get("description", ""),
                    "hotkey_count": len(data.get("hotkeys", {}))
                }
                for profile_id, data in profiles.items()
            ]
        except Exception as e:
            logger.error(f"Error getting profiles: {e}")
            return []

    def get_profile_info(self, profile_id=None):
        """Get information about a specific profile"""
        if profile_id is None:
            profile_id = self.current_profile

        try:
            profile = self.config.get("hotkey_profiles", {}).get(profile_id, {})
            return {
                "id": profile_id,
                "name": profile.get("name", profile_id),
                "description": profile.get("description", ""),
                "hotkeys": profile.get("hotkeys", {}),
                "hotkey_count": len(profile.get("hotkeys", {}))
            }
        except Exception as e:
            logger.error(f"Error getting profile info: {e}")
            return {}

    def get_hotkey_for_action(self, action):
        """Get hotkey assigned to a specific action"""
        try:
            profile = self.config.get("hotkey_profiles", {}).get(self.current_profile, {})
            hotkeys = profile.get("hotkeys", {})

            for action_id, config in hotkeys.items():
                if config.get("action") == action:
                    return {
                        "key": config.get("key"),
                        "label": config.get("label", action_id),
                        "description": config.get("description", "")
                    }

            return None

        except Exception as e:
            logger.error(f"Error getting hotkey for action: {e}")
            return None

    def handle_key_press(self, key, player_instance=None):
        """Handle a key press event"""
        try:
            self._cancel_long_press_timer(key)
            self._pending_short.pop(key, None)  # clear any stale state

            has_long = bool(self.hotkey_map.get(f"long_{key}"))
            actions = self.hotkey_map.get(key, [])

            if has_long:
                # Key has a long-press binding: arm the timer and defer the
                # short action until release (long press wins on timeout).
                if actions:
                    self._pending_short[key] = (actions[0], player_instance)
                try:
                    self._start_long_press_timer(key, player_instance)
                except Exception:
                    # FIX (r88): never leave a pending-short entry behind if
                    # the timer failed to start - it would fire on the next
                    # unrelated release.
                    self._pending_short.pop(key, None)
                    raise
                return True

            if actions:
                return self._execute_action(actions[0], player_instance)

            return False

        except Exception as e:
            logger.error(f"Error handling key press: {e}")
            return False

    def handle_key_release(self, key, player_instance=None):
        """Handle key release event"""
        try:
            timer_was_armed = self._cancel_long_press_timer(key)
            pending = self._pending_short.pop(key, None)

            # Timer still armed => press was shorter than long_press_delay,
            # so the deferred short action fires now.
            if timer_was_armed and pending:
                action_config, instance = pending
                return self._execute_action(action_config, instance)

            return True

        except Exception as e:
            logger.error(f"Error handling key release: {e}")
            return False

    def _start_long_press_timer(self, key, player_instance):
        """Start timer for long press detection"""
        try:
            self._cancel_long_press_timer(key)

            long_key = f"long_{key}"
            if not self.hotkey_map.get(long_key):
                return

            if _E_TIMER_AVAILABLE:
                # eTimer fires on the main loop -> safe to touch UI/player
                timer = eTimer()
                cb = lambda k=key, p=player_instance: self._handle_long_press(f"long_{k}", p)
                # FIX (r88): attach via exactly ONE of the two APIs -
                # trying both unconditionally double-fires on builds
                # where both exist.
                attached = False
                try:
                    timer.callback.append(cb)
                    attached = True
                except Exception:
                    pass
                if not attached:
                    try:
                        timer.timeout.connect(cb)
                        attached = True
                    except Exception:
                        pass
                if not attached:
                    raise RuntimeError("eTimer has no callback/timeout API")
                timer.start(int(self.long_press_delay * 1000), True)  # single shot
                self.long_press_timers[key] = timer  # keep a reference (prevent GC)
            else:
                # Fallback only -- WARNING: background thread, UI-unsafe
                timer = Timer(self.long_press_delay, self._handle_long_press,
                              [long_key, player_instance])
                timer.daemon = True
                self.long_press_timers[key] = timer
                timer.start()

        except Exception as e:
            logger.error(f"Error starting long press timer: {e}")

    def _cancel_long_press_timer(self, key):
        """Cancel long press timer. Returns True if a pending timer was cancelled."""
        try:
            timer = self.long_press_timers.pop(key, None)
            if timer:
                if hasattr(timer, "stop"):   # enigma.eTimer
                    timer.stop()
                else:                        # threading.Timer
                    timer.cancel()
                logger.debug(f"Cancelled long press timer for {key}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error cancelling long press timer: {e}")
            return False

    def _handle_long_press(self, long_key, player_instance):
        """Handle long press action (runs on the main loop via eTimer)"""
        try:
            key = long_key[5:] if long_key.startswith("long_") else long_key
            # Long press wins: clear timer slot and drop the deferred short action
            self.long_press_timers.pop(key, None)
            self._pending_short.pop(key, None)

            actions = self.hotkey_map.get(long_key, [])
            if actions:
                action_config = actions[0]
                logger.info(f"Long press detected: {long_key} -> {action_config['action']}")
                self._execute_action(action_config, player_instance)
        except Exception as e:
            logger.error(f"Error handling long press: {e}")

    # action -> attribute name on the player instance (resolved lazily)
    # FIX (r91-audit): names now match the round-88/91 player's actual
    # camelCase methods. The old map was snake_case plus ghost methods -
    # ZERO of its 8 entries resolved, so every player-action dispatch
    # failed with "Player does not implement". Ghost actions
    # (open_subtitle_settings / open_subtitle_quick_menu /
    # download_subtitles) are dropped; a JSON profile still binding them
    # now logs "Unknown action", which is honest.
    _PLAYER_ACTIONS = {
        "toggle_subtitle": "toggleSubtitles",
        "open_subtitle_menu": "showSubtitleMenu",
        "open_audio_menu": "showAudioMenu",
        "open_chapter_menu": "_showChapters",
        "open_jump_menu": "_showChapters",   # alias
    }

    # action -> attribute name on the player's subtitle manager
    # FIX (r91-audit): every original entry was a ghost - SubtitleHandler
    # has no open_delay_settings / open_style_settings /
    # open_embedded_subtitle_tools (its real API is toggleSubtitles /
    # selectSubtitle / adjustDelay(ms) / resetDelay, and the delay ones
    # need arguments, so they cannot live in a zero-argument dispatch
    # map). Left EMPTY: the dispatcher falls through safely. Only add
    # entries for real ZERO-ARGUMENT methods on the handler.
    _SUBTITLE_MANAGER_ACTIONS = {}

    # action -> seconds to seek (positive = forward)
    _SEEK_ACTIONS = {
        "jump_back_30": -30,
        "jump_forward_30": 30,
        "jump_back_10": -10,
        "jump_forward_10": 10,
    }

    @staticmethod
    def _resolve_subtitle_manager(player_instance):
        """
        FIX (r88): the real player stores its subtitle handler as
        ``subtitleHandler``. Older/other shapes may expose
        ``subtitle_manager`` directly, or via a ``player_ref``. Try all.

        NOTE (r91-audit): with _SUBTITLE_MANAGER_ACTIONS empty this is
        only reachable if that map is ever populated - kept as the
        documented extension point.
        """
        if player_instance is None:
            return None
        for attr in ("subtitleHandler", "subtitle_manager"):
            mgr = getattr(player_instance, attr, None)
            if mgr is not None:
                return mgr
        ref = getattr(player_instance, "player_ref", None)
        if ref is not None:
            for attr in ("subtitleHandler", "subtitle_manager"):
                mgr = getattr(ref, attr, None)
                if mgr is not None:
                    return mgr
        return None

    def _execute_action(self, action_config, player_instance):
        """Execute a hotkey action.

        Dispatch is lazy (getattr at call time). The old version built a dict
        of bound methods up front, so ONE missing method on the player raised
        AttributeError during dict construction and killed EVERY action -
        including the ones that actually exist.
        """
        try:
            action = action_config.get("action")
            action_id = action_config.get("action_id")

            logger.info(f"Executing hotkey action: {action_id} -> {action}")

            if not player_instance:
                logger.warning("No player instance for hotkey execution")
                return False

            # 1) Direct player methods
            attr = self._PLAYER_ACTIONS.get(action)
            if attr:
                method = getattr(player_instance, attr, None)
                if callable(method):
                    method()
                    return True
                logger.warning(f"Player does not implement '{attr}' (action '{action}')")
                return False

            # 2) Methods on the player's subtitle manager
            #    (dormant while _SUBTITLE_MANAGER_ACTIONS is empty - see
            #    its comment; falls through safely.)
            attr = self._SUBTITLE_MANAGER_ACTIONS.get(action)
            if attr:
                # FIX (r88): resolve the handler the way the real player
                # actually stores it.
                manager = self._resolve_subtitle_manager(player_instance)
                method = getattr(manager, attr, None) if manager else None
                if callable(method):
                    method()
                    return True
                logger.warning(f"Subtitle manager does not implement '{attr}' (action '{action}')")
                return False

            # 3) Seeking
            if action in self._SEEK_ACTIONS:
                # FIX (r88): include the player's real ``seek`` method last,
                # so more specific names still win when present.
                seeker = (getattr(player_instance, "_jump_by_seconds", None)
                          or getattr(player_instance, "seek_relative", None)
                          or getattr(player_instance, "doSeekRelative", None)
                          or getattr(player_instance, "seek", None))
                if callable(seeker):
                    seeker(self._SEEK_ACTIONS[action])
                    return True
                logger.warning(f"Player has no seek method (action '{action}')")
                return False

            # 4) mark_position needs a point_type argument the old code never
            #    passed -> keep out of the map until the API is confirmed.
            if action == "mark_position":
                logger.warning("Action 'mark_position' needs a point_type argument - not wired")
                return False

            logger.error(f"Unknown action: {action}")
            return False

        except Exception as e:
            logger.error(f"Error executing action {action_config}: {e}")
            return False

    def save_config(self, config_path=None):
        """Save current configuration to file"""
        try:
            if config_path is None:
                config_path = "/etc/enigma2/wgfilemanager_hotkeys.json"

            # Ensure directory exists (guard: dirname("") would raise)
            parent = os.path.dirname(config_path)
            if parent:
                os.makedirs(parent, exist_ok=True)

            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=2)

            logger.info(f"Saved hotkey config to {config_path}")
            return True

        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False

    def reset_to_defaults(self):
        """Reset configuration to defaults"""
        try:
            default_config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "default_hotkeys.json"
            )

            if os.path.exists(default_config_path):
                with open(default_config_path, 'r') as f:
                    self.config = json.load(f)
                self._build_hotkey_map()
                # FIX (r88): persist the reset, otherwise the user config on
                # disk will silently override it on the next process start.
                try:
                    self.save_config()
                except Exception as se:
                    logger.warning(f"Reset loaded but not persisted: {se}")
                logger.info("Reset hotkey config to defaults")
                return True
            else:
                logger.error("Default config file not found")
                return False

        except Exception as e:
            logger.error(f"Error resetting to defaults: {e}")
            return False


class SubtitleHotkeyManager(HotkeyManager):
    """Specialized hotkey manager for subtitle actions"""

    def __init__(self, session, player_ref):
        super().__init__(session)
        self.player_ref = player_ref

    # FIX (r88): the map was previously defined THREE times in a row.
    # Kept a single authoritative copy.
    # FIX (r91-audit): "long_subtitle" and "long_text" pointed at ghost
    # actions (open_subtitle_settings / open_subtitle_quick_menu).
    # Remapped to actions that actually exist on the player.
    _FALLBACK_KEY_MAP = {
        "subtitle": "toggle_subtitle",
        "subtitles": "toggle_subtitle",      # legacy spelling
        "text": "open_subtitle_menu",
        "long_subtitle": "open_subtitle_menu",   # was ghost 'open_subtitle_settings'
        "long_text": "toggle_subtitle",          # was ghost 'open_subtitle_quick_menu'
        "audio": "open_audio_menu",
        "long_audio": "jump_back_30",
    }

    def handle_hotkey(self, key):
        """Handle subtitle-specific hotkey"""
        try:
            # 1) The JSON profile already contains "long_*" keys verbatim
            #    (hotkey_map is keyed by the raw "key" value).
            actions = self.hotkey_map.get(key)
            if actions:
                return self._execute_action(actions[0], self.player_ref)

            # 2) Hardcoded fallback for keys not bound in the profile
            action = self._FALLBACK_KEY_MAP.get(key)
            if action:
                return self._execute_subtitle_action(action)

            return False

        except Exception as e:
            logger.error(f"Error handling subtitle hotkey: {e}")
            return False

    def _execute_subtitle_action(self, action):
        """Execute subtitle-specific action.

        FIX (r91-audit): everything now routes through the generic
        dispatcher, which resolves the player's real camelCase methods.
        The old toggle special-case called SubtitleHandler directly,
        bypassing the player's toggleSubtitles() wrapper - so the SUB
        indicator and the status line never refreshed. The old
        open_subtitle_menu special-case is likewise covered by
        _PLAYER_ACTIONS -> showSubtitleMenu.
        """
        try:
            ok = self._execute_action(
                {"action": action, "action_id": action}, self.player_ref)
            return "OK" if ok else f"Failed: {action}"
        except Exception as e:
            logger.error(f"Error executing subtitle action: {e}")
            return f"Error: {e}"