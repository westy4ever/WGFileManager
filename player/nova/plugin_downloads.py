# -*- coding: utf-8 -*-
"""Nova player (local files): nothing to download or record -- the file is
already on disk. download_dir() is where online subtitles are saved."""
import os

DownloadTask = None
download_manager = None


def download_dir():
    for d in ("/media/hdd/subtitles", "/media/usb/subtitles", "/tmp/subtitles"):
        try:
            if not os.path.isdir(d):
                os.makedirs(d)
            return d
        except Exception:
            continue
    return "/tmp"
