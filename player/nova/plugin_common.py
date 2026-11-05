# -*- coding: utf-8 -*-
"""WGFileManager / Nova player -- logging (stands in for NovaPlay's plugin_common)."""
try:
    from ...utils.logging_config import get_logger
    _logger = get_logger("WGFM.nova")
except Exception:                                   # tests / outside the plugin
    import logging
    _logger = logging.getLogger("WGFM.nova")

_PLAY_ID = [""]


def route_studio_log():
    """[2026-11-05] the Subtitle Studio logs as "SubtitleStudio" (NovaPlay's
    name); send those lines to /tmp/wgfilemanager.log as well"""
    try:
        import logging
        main = logging.getLogger("WGFileManager")
        st = logging.getLogger("SubtitleStudio")
        st.setLevel(logging.DEBUG)
        for h in main.handlers:
            if h not in st.handlers:
                st.addHandler(h)
        if main.handlers:
            st.propagate = False
    except Exception:
        pass


route_studio_log()


def set_play_id(pid):
    _PLAY_ID[0] = pid or ""


def my_log(msg):
    try:
        _logger.info(("[%s] " % _PLAY_ID[0] if _PLAY_ID[0] else "") + str(msg))
    except Exception:
        pass
