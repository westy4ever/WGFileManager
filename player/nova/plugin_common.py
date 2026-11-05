# -*- coding: utf-8 -*-
"""WGFileManager / Nova player -- logging (stands in for NovaPlay's plugin_common)."""
try:
    from ...utils.logging_config import get_logger
    _logger = get_logger("WGFM.nova")
except Exception:                                   # tests / outside the plugin
    import logging
    _logger = logging.getLogger("WGFM.nova")

_PLAY_ID = [""]


def set_play_id(pid):
    _PLAY_ID[0] = pid or ""


def my_log(msg):
    try:
        _logger.info(("[%s] " % _PLAY_ID[0] if _PLAY_ID[0] else "") + str(msg))
    except Exception:
        pass
