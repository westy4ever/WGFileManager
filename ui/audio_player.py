from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.ProgressBar import ProgressBar
from Components.Pixmap import Pixmap
from enigma import getDesktop, eServiceReference, eTimer, iPlayableService
import os

from ..utils.logging_config import get_logger
from ..utils.formatters import format_size

logger = get_logger(__name__)

class AudioPlaylistPlayer(Screen):
    """Audio playlist player with full controls"""
    
    def __init__(self, session, playlist, current_index=0, main_screen_ref=None):
        Screen.__init__(self, session)
        
        # Get screen dimensions
        w, h = getDesktop(0).size().width(), getDesktop(0).size().height()
        
        # Initialize
        self.playlist = playlist
        self.current_index = current_index
        self.main_screen_ref = main_screen_ref
        self.is_playing = False
        self.is_paused = False
        
        # Create skin
        self.skin = f"""
        <screen name="AudioPlaylistPlayer" position="0,0" size="{w},{h}" backgroundColor="#0d1117" flags="wfNoBorder">
            <eLabel position="0,0" size="{w},100" backgroundColor="#161b22" />
            <eLabel position="0,88" size="{w},2" backgroundColor="#1976d2" />
            
            <eLabel text=" Audio Player" position="0,20" size="{w},60" font="Regular;48" halign="center" valign="center" transparent="1" foregroundColor="#58a6ff" shadowColor="#000000" shadowOffset="-2,-2" />
            
            <widget name="track_info" position="50,150" size="{w-100},50" font="Regular;32" halign="center" foregroundColor="#00ff00" transparent="1" />
            <widget name="track_number" position="50,210" size="{w-100},40" font="Regular;26" halign="center" foregroundColor="#ffaa00" transparent="1" />
            
            <widget name="album_art" position="{(w-400)//2},280" size="400,400" alphatest="on" />
            
            <widget name="time_current" position="100,720" size="200,40" font="Regular;28" halign="left" foregroundColor="#ffffff" transparent="1" />
            <widget name="progress_bar" position="320,730" size="{w-640},20" backgroundColor="#333333" foregroundColor="#00aaff" borderWidth="2" borderColor="#aaaaaa" />
            <widget name="time_total" position="{w-300},720" size="200,40" font="Regular;28" halign="right" foregroundColor="#ffffff" transparent="1" />
            
            <widget name="status" position="50,780" size="{w-100},40" font="Regular;28" halign="center" foregroundColor="#ffff00" transparent="1" />
            
            <eLabel position="0,{h-150}" size="{w},2" backgroundColor="#30363d" />
            <eLabel position="0,{h-148}" size="{w},150" backgroundColor="#010409" />
            
            <widget name="controls_help" position="50,{h-130}" size="{w-100},40" font="Regular;24" halign="center" foregroundColor="#aaaaaa" transparent="1" />
            
            <eLabel position="100,{h-80}" size="180,50" backgroundColor="#7d1818" />
            <eLabel position="330,{h-80}" size="180,50" backgroundColor="#1e5128" />
            <eLabel position="560,{h-80}" size="180,50" backgroundColor="#1976d2" />
            <eLabel position="790,{h-80}" size="180,50" backgroundColor="#9e6a03" />
            
            <eLabel text="Exit" position="110,{h-75}" size="160,40" zPosition="1" font="Regular;26" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
            <eLabel text="Prev" position="340,{h-75}" size="160,40" zPosition="1" font="Regular;26" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
            <eLabel text="Play/Pause" position="570,{h-75}" size="160,40" zPosition="1" font="Regular;26" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
            <eLabel text="Next" position="800,{h-75}" size="160,40" zPosition="1" font="Regular;26" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" />
        </screen>"""
        
        # Create widgets
        self["track_info"] = Label("")
        self["track_number"] = Label("")
        self["album_art"] = Pixmap()
        self["time_current"] = Label("00:00")
        self["time_total"] = Label("00:00")
        self["progress_bar"] = ProgressBar()
        self["status"] = Label("")
        self["controls_help"] = Label(" CH- Previous | ▶ OK Play/Pause | CH+ Next | STOP Stop")
        
        # Setup actions
        self["actions"] = ActionMap([
            "OkCancelActions", "ColorActions", "DirectionActions", 
            "MediaPlayerActions", "MoviePlayerActions", "ChannelSelectBaseActions"
        ], {
            "ok": self.toggle_play_pause,
            "cancel": self.ask_exit,
            "exit": self.ask_exit,
            "red": self.ask_exit,
            "green": self.previous_track,
            "blue": self.toggle_play_pause,
            "yellow": self.next_track,
            "play": self.toggle_play_pause,
            "playpause": self.toggle_play_pause,
            "pause": self.toggle_play_pause,
            "stop": self.stop_playback,
            "left": self.seek_backward,
            "right": self.seek_forward,
            "up": self.volume_up,
            "down": self.volume_down,
            "nextBouquet": self.next_track,
            "prevBouquet": self.previous_track,
            "channelUp": self.next_track,
            "channelDown": self.previous_track,
        }, -1)
        
        # Timer for position updates
        self.position_timer = eTimer()
        self.position_timer.callback.append(self.update_position)
        
        # Start playback
        self.onLayoutFinish.append(self.start_playback)
    
    def start_playback(self):
        """Start playing current track"""
        try:
            if not self.playlist or self.current_index >= len(self.playlist):
                self.session.open(MessageBox, "No tracks to play!", MessageBox.TYPE_ERROR)
                self.close()
                return
            
            # Get current track
            current_track = self.playlist[self.current_index]
            
            # Update display
            track_name = os.path.basename(current_track)
            self["track_info"].setText(track_name)
            self["track_number"].setText(f"Track {self.current_index + 1} of {len(self.playlist)}")
            
            # Create service reference
            ref = eServiceReference(4097, 0, current_track)
            ref.setName(track_name)
            
            # Start playback
            self.session.nav.playService(ref)
            self.is_playing = True
            self.is_paused = False
            self["status"].setText("▶ Playing")
            
            # Start position timer
            self.position_timer.start(1000)  # Update every second
            
            # Get total duration
            self.update_position()
            
            logger.info(f"Playing track {self.current_index + 1}/{len(self.playlist)}: {track_name}")
            
        except Exception as e:
            logger.error(f"Error starting playback: {e}")
            self.session.open(MessageBox, f"Playback error:\n{e}", MessageBox.TYPE_ERROR)
    
    def update_position(self):
        """Update playback position"""
        try:
            service = self.session.nav.getCurrentService()
            if not service:
                return
            
            seek = service.seek()
            if not seek:
                return
            
            # Get current position
            position = seek.getPlayPosition()
            if position and position[1] > 0:
                current_seconds = position[1] / 90000  # Convert from 90kHz ticks
                
                # Get total length
                length = seek.getLength()
                if length and length[1] > 0:
                    total_seconds = length[1] / 90000
                    
                    # Update labels
                    self["time_current"].setText(self.format_time(current_seconds))
                    self["time_total"].setText(self.format_time(total_seconds))
                    
                    # Update progress bar
                    if total_seconds > 0:
                        progress = int((current_seconds / total_seconds) * 100)
                        self["progress_bar"].setValue(progress)
                    
                    # Check if track finished
                    if current_seconds >= total_seconds - 1:
                        self.track_finished()
            
        except Exception as e:
            logger.debug(f"Position update error: {e}")
    
    def format_time(self, seconds):
        """Format seconds to MM:SS"""
        try:
            minutes = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{minutes:02d}:{secs:02d}"
        except:
            return "00:00"
    
    def track_finished(self):
        """Handle track finishing - auto play next"""
        logger.info("Track finished, playing next")
        self.next_track()
    
    def next_track(self):
        """Play next track in playlist"""
        try:
            if self.current_index < len(self.playlist) - 1:
                self.current_index += 1
                self.start_playback()
            else:
                # Reached end of playlist - loop to start
                self.current_index = 0
                self.start_playback()
                self["status"].setText("▶ Looped to start")
        except Exception as e:
            logger.error(f"Error playing next track: {e}")
    
    def previous_track(self):
        """Play previous track in playlist"""
        try:
            if self.current_index > 0:
                self.current_index -= 1
                self.start_playback()
            else:
                # At start - loop to end
                self.current_index = len(self.playlist) - 1
                self.start_playback()
                self["status"].setText("▶ Looped to end")
        except Exception as e:
            logger.error(f"Error playing previous track: {e}")
    
    def toggle_play_pause(self):
        """Toggle play/pause"""
        try:
            service = self.session.nav.getCurrentService()
            if not service:
                return
            
            pause = service.pause()
            if pause:
                if self.is_paused:
                    # Resume
                    pause.unpause()
                    self.is_paused = False
                    self["status"].setText("▶ Playing")
                    self.position_timer.start(1000)
                else:
                    # Pause
                    pause.pause()
                    self.is_paused = True
                    self["status"].setText(" Paused")
                    self.position_timer.stop()
        except Exception as e:
            logger.error(f"Error toggling play/pause: {e}")
    
    def stop_playback(self):
        """Stop playback"""
        try:
            self.session.nav.stopService()
            self.is_playing = False
            self.is_paused = False
            self["status"].setText(" Stopped")
            self.position_timer.stop()
        except Exception as e:
            logger.error(f"Error stopping playback: {e}")
    
    def seek_forward(self):
        """Seek forward 10 seconds"""
        try:
            service = self.session.nav.getCurrentService()
            if service:
                seek = service.seek()
                if seek:
                    position = seek.getPlayPosition()
                    if position and position[1] > 0:
                        # Seek forward 10 seconds
                        new_position = position[1] + (10 * 90000)
                        seek.seekTo(new_position)
                        self["status"].setText(" +10s")
        except Exception as e:
            logger.error(f"Seek forward error: {e}")
    
    def seek_backward(self):
        """Seek backward 10 seconds"""
        try:
            service = self.session.nav.getCurrentService()
            if service:
                seek = service.seek()
                if seek:
                    position = seek.getPlayPosition()
                    if position and position[1] > 0:
                        # Seek backward 10 seconds
                        new_position = max(0, position[1] - (10 * 90000))
                        seek.seekTo(new_position)
                        self["status"].setText(" -10s")
        except Exception as e:
            logger.error(f"Seek backward error: {e}")
    
    def volume_up(self):
        """Increase volume"""
        from Components.VolumeControl import VolumeControl
        VolumeControl.instance.volUp()
        self["status"].setText(" Volume Up")
    
    def volume_down(self):
        """Decrease volume"""
        from Components.VolumeControl import VolumeControl
        VolumeControl.instance.volDown()
        self["status"].setText(" Volume Down")
    
    def ask_exit(self):
        """Ask before exiting"""
        self.session.openWithCallback(
            self.exit_confirmed,
            MessageBox,
            "Exit audio player?\n\n(Playback will stop)",
            MessageBox.TYPE_YESNO
        )
    
    def exit_confirmed(self, confirmed):
        """Handle exit confirmation"""
        if confirmed:
            try:
                # Stop playback
                self.position_timer.stop()
                self.session.nav.stopService()
                
                # Save resume point if available
                if self.main_screen_ref:
                    current_track = self.playlist[self.current_index]
                    service = self.session.nav.getCurrentService()
                    if service:
                        seek = service.seek()
                        if seek:
                            position = seek.getPlayPosition()
                            if position and position[1] > 0:
                                current_pos = position[1] / 90000
                                self.main_screen_ref.save_resume_point(current_track, current_pos)
                
                self.close()
            except Exception as e:
                logger.error(f"Exit error: {e}")
                self.close()