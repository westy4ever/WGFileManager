# WG-File-Manager-PRO-aj-style

## Video player: Nova (NovaPlay's player, local edition)

Videos play in the **Nova player** (`player/nova/`), the player from NovaPlay
adapted for files on disk; the old AjPanel-style player is gone.

- **Panel:** seek bar with time bubble, resume / watched marks, clock, "Ends hh:mm".
- **Keys:** OK pause · ◀▶ seek (hold to speed up) · 0-9 jump to 0-90 % ·
  **GREEN** Smart GREEN (skip intro / chapters / next episode) ·
  **RED** previous file · **YELLOW** subtitles on/off · **BLUE** subtitles & settings ·
  **AUDIO** audio track · **EPG** episode list · **MENU** picture / sleep / chapters / help.
- **Folder = series:** the other videos in the same folder (natural order, E2 before E10)
  are the episodes: EPG lists them, the next one is offered at the end with a countdown.
- **Resume:** asks "Resume from 12:34?"; positions and settings are kept in
  `/etc/enigma2/wgfilemanager_nova.json`.
- **Subtitles:** NovaPlay's subtitle system (embedded tracks, .srt next to the video,
  online search, Sync Studio).

Checks before pushing: `python3 tests/run_nova_checks.py`


**Built-in subtitles:** BLUE › Subtitles lists the video's own tracks ("Built-in: Arabic · SRT").
Picking one copies it out once (needs ffmpeg: `opkg install ffmpeg`), then sync and styling work on it.
Picture subtitles (PGS / DVD / DVB) can't be used.

**Log:** `/tmp/wgfilemanager.log` (cleared on reboot) has the player and the Subtitle Studio lines.
After a problem: `tail -n 80 /tmp/wgfilemanager.log`. A subtitle line there says who draws it:
`-> Studio, N lines` (sync and styling work) or `-> Enigma2 draws it` (the file couldn't be read).
