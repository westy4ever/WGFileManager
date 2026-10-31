# -*- coding: utf-8 -*-
"""
WGFileManager — main-thread dispatcher (vendored from NovaPlay).
Self-contained: imports only enigma. Call from any thread.
"""

import threading

try:
    from enigma import eTimer
except Exception:
    eTimer = None

_MAIN_LOCK = threading.Lock()
_MAIN_QUEUE = []
_MAIN_TIMER = None


def _log_crash(exc):
    try:
        import traceback
        with open("/tmp/wgfilemanager.log", "a") as f:
            f.write("[subtitles.thread] callback crashed: {} {}\n".format(
                exc, traceback.format_exc()[-400:]))
    except Exception:
        pass


def _drain_main_queue():
    global _MAIN_TIMER
    with _MAIN_LOCK:
        items = list(_MAIN_QUEUE)
        del _MAIN_QUEUE[:]
    for _f, _a, _kw in items:
        try:
            _f(*_a, **_kw)
        except Exception as _e:
            _log_crash(_e)
    with _MAIN_LOCK:
        pending = bool(_MAIN_QUEUE)
    if pending and _MAIN_TIMER is not None:
        try:
            _MAIN_TIMER.start(50, True)
        except Exception:
            pass


def callInMainThread(func, *args, **kwargs):
    global _MAIN_TIMER
    if eTimer is None:
        try:
            func(*args, **kwargs)
        except Exception:
            pass
        return
    with _MAIN_LOCK:
        _MAIN_QUEUE.append((func, args, kwargs))
        need_timer = (_MAIN_TIMER is None)
        if need_timer:
            try:
                _MAIN_TIMER = eTimer()
                _MAIN_TIMER.callback.append(_drain_main_queue)
            except Exception:
                _MAIN_TIMER = None
                try:
                    from twisted.internet import reactor
                    reactor.callFromThread(_drain_main_queue)
                except Exception:
                    pass
    if _MAIN_TIMER is not None:
        try:
            _MAIN_TIMER.start(50, True)
        except Exception:
            try:
                from twisted.internet import reactor
                reactor.callFromThread(_drain_main_queue)
            except Exception:
                pass
    else:
        try:
            from twisted.internet import reactor
            reactor.callFromThread(_drain_main_queue)
        except Exception:
            pass
