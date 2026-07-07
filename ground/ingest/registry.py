"""In-process observer registry — fans decoded packets out to consumers.

One process owns the radio (D4); everything else (logger, OLED, dashboard feed)
registers here and consumes decoded packets, never the radio or the log. A single
consumer raising must not break the radio loop or the other consumers.
"""


class ObserverRegistry:
    def __init__(self):
        self._observers = []

    def register(self, fn):
        """Register a callable observer; returns it (usable as a decorator)."""
        self._observers.append(fn)
        return fn

    def dispatch(self, item):
        for fn in list(self._observers):
            try:
                fn(item)
            except Exception:
                # A consumer's failure is isolated — never propagate to the radio loop.
                pass
