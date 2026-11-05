# -*- coding: utf-8 -*-
"""Run screen work on Enigma2's main thread.

Enigma2's screens, widgets and timers are not thread-safe: touching them from a
worker thread (a scan, a copy, an install) can crash the receiver at random.
Workers hand such calls to the main thread here; Enigma2's reactor
(twisted, e2reactor) runs them there. On the main thread the call runs at once.

    call_on_main(fn, *args, **kwargs)
    @on_main                      -- a function / method that always runs there
    make_thread_safe(cls)         -- every public method of a class
"""
import functools
import threading


def _is_main():
    try:
        return threading.current_thread() is threading.main_thread()
    except Exception:
        return True


def call_on_main(fn, *args, **kwargs):
    """fn(*args) now on the main thread, or handed to it from a worker
    (the worker then gets None back)"""
    if _is_main():
        return fn(*args, **kwargs)
    try:
        from twisted.internet import reactor
        reactor.callFromThread(fn, *args, **kwargs)
        return None
    except Exception:
        return fn(*args, **kwargs)              # no reactor (tests): as before


def on_main(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return call_on_main(fn, *args, **kwargs)
    return wrapper


def make_thread_safe(cls):
    for name, val in list(vars(cls).items()):
        if not name.startswith("_") and callable(val) and not isinstance(val, (staticmethod, classmethod, type)):
            setattr(cls, name, on_main(val))
    return cls
