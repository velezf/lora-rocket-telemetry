"""Guess-the-apogee (Epic 8.4) — pure game logic, time injected.

KID-TWEAKABLE KNOBS (Epic 8.5 — change these, restart the service):
    PLAYERS      who gets a guess, in dialing order (names show on the OLED —
                 keep them ~7 chars so they fit the 128 px screen)
    RULE         "closest" = smallest |guess - actual| wins (over or under);
                 "no-over" = Price-Is-Right: closest WITHOUT going over —
                 everyone busts, nobody wins (the rocket wins)
    STEP_FT      how many feet one button press adds/removes
    START_FT     where the dial starts
    DEBOUNCE_S   ignore button bounces closer together than this

Phases: "rules" (startup: pick the game — dial toggles Closest/NoOver,
lock confirms; the RULE knob is the preselection) -> "entry" (on the pad, dialing) -> "watching" (flight; betting window
closed at liftoff or when every seat is taken) -> "reveal" (apogee: the
actual peak and whose guess came closest — ties go to the earlier kid).
Locking is a TWO-press affair: #12 shows "<name> <guess> OK?" and only a
second #12 banks it — dialing during the OK? cancels back to adjusting.
(Field feedback 2026-08-31: one-press lock was guaranteed kid-fumble.)
A dialed-but-never-locked guess banks automatically at liftoff: a kid who
dialed 350 and got distracted by the countdown still played.
"""
from __future__ import annotations

PLAYERS = ("Bacon", "HnyBsct", "Dragon")
RULE = "closest"
STEP_FT = 25
START_FT = 300
DEBOUNCE_S = 0.15


class GuessGame:
    def __init__(self, step_ft: int = STEP_FT, start_ft: int = START_FT,
                 players: tuple[str, ...] = PLAYERS, rule: str = RULE,
                 debounce_s: float = DEBOUNCE_S):
        assert rule in ("closest", "no-over"), rule
        self.rule = rule
        self._step = step_ft
        self.players = tuple(players)
        self._debounce_s = debounce_s
        self._last_press: float | None = None

        self.phase = "rules"                 # rules | entry | watching | reveal
        self.current_guess = start_ft
        self.guesses: list[int] = []         # locked, in PLAYERS order
        self.winner: tuple[str, int] | None = None   # (player name, guess)
        self.peak_ft: int | None = None
        self.confirming = False
        self._dial_touched = False
        self._seen_flight = False

    @property
    def entering_name(self) -> str:
        return self.players[len(self.guesses)]

    @property
    def armed(self) -> bool:
        """All guesses banked, rocket still on the pad — awaiting launch."""
        return self.phase == "watching" and not self._seen_flight

    def reset(self) -> None:
        """Start over (the #5+#6 chord, or the sled's next-flight St cycle)."""
        self.__init__(step_ft=self._step, players=self.players,
                      rule=self.rule, debounce_s=self._debounce_s)

    # -- buttons ------------------------------------------------------------
    def _debounced(self, mono: float) -> bool:
        if self._last_press is not None and mono - self._last_press < self._debounce_s:
            return True
        self._last_press = mono
        return False

    def _toggle_rule(self) -> None:
        self.rule = "no-over" if self.rule == "closest" else "closest"

    def press_up(self, mono: float) -> None:
        if self.phase not in ("rules", "entry") or self._debounced(mono):
            return
        if self.phase == "rules":
            self._toggle_rule()
            return
        self.confirming = False              # dialing cancels the OK?
        self.current_guess += self._step
        self._dial_touched = True

    def press_down(self, mono: float) -> None:
        if self.phase not in ("rules", "entry") or self._debounced(mono):
            return
        if self.phase == "rules":
            self._toggle_rule()
            return
        self.confirming = False              # dialing cancels the OK?
        self.current_guess = max(0, self.current_guess - self._step)
        self._dial_touched = True

    def press_lock(self, mono: float) -> None:
        if self.phase not in ("rules", "entry") or self._debounced(mono):
            return
        if self.phase == "rules":            # rule confirmed: guessing begins
            self.phase = "entry"
            return
        if not self.confirming:              # first press only ASKS
            self.confirming = True
            return
        self.confirming = False              # second press BANKS
        self.guesses.append(self.current_guess)
        self._dial_touched = False
        if len(self.guesses) >= len(self.players):
            self.phase = "watching"

    # -- flight-driven transitions ------------------------------------------
    def on_view(self, view) -> None:
        if view.st is not None and view.st != 0:
            self._seen_flight = True
        # St RETURNED to 0 after a flight = next launch: fresh round. The
        # transition matters: plain pad frames must NOT reset a locked-in
        # game awaiting launch (family bench 2026-08-31 — it bounced kids
        # back to the menu the moment they finished locking in).
        if (self.phase in ("watching", "reveal") and view.st == 0
                and self._seen_flight):
            self.reset()
            return
        if self.phase == "rules" and view.st is not None and view.st != 0:
            self.phase = "watching"          # it flew mid-menu: no game this round
        if self.phase == "entry" and view.st is not None and view.st != 0:
            if self._dial_touched and len(self.guesses) < len(self.players):
                self.guesses.append(self.current_guess)   # a dialed kid still played
                self._dial_touched = False
            self.confirming = False
            self.phase = "watching"
        if (self.phase in ("entry", "watching") and view.apogee_reveal
                and view.peak_ft is not None):
            self.peak_ft = view.peak_ft
            peak = view.peak_ft
            eligible = range(len(self.guesses))
            if self.rule == "no-over":
                eligible = [i for i in eligible if self.guesses[i] <= peak]
            if self.guesses and eligible:
                # min() is stable: equal distances resolve to the earlier kid
                i = min(eligible, key=lambda i: abs(self.guesses[i] - peak))
                self.winner = (self.players[i], self.guesses[i])
            self.phase = "reveal"
