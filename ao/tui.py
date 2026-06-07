"""TUI interactiva de ao basada en curses (solo librería estándar).

Disposición de dos paneles: a la izquierda los STREAMS (apps reproduciendo),
a la derecha las SALIDAS. Se selecciona una app y se la mueve a la salida
elegida con un par de teclas.
"""

from __future__ import annotations

import curses

from . import backend
from .backend import BackendError, Sink, Stream

HELP = "[↑↓/jk] mover  [Tab/←→] panel  [Enter] aplicar  [d] default  [m] mute  [r] refrescar  [q] salir"


class State:
    def __init__(self) -> None:
        self.streams: list[Stream] = []
        self.sinks: list[Sink] = []
        self.default: str = ""
        self.sel_stream = 0
        self.sel_sink = 0
        self.focus = 0  # 0 = panel streams, 1 = panel sinks
        self.message = ""
        self.refresh()

    def refresh(self) -> None:
        self.streams = backend.list_streams()
        self.sinks = backend.list_sinks()
        self.default = backend.default_sink_name()
        self.sel_stream = max(0, min(self.sel_stream, max(0, len(self.streams) - 1)))
        self.sel_sink = max(0, min(self.sel_sink, max(0, len(self.sinks) - 1)))

    def current_stream(self) -> Stream | None:
        return self.streams[self.sel_stream] if self.streams else None

    def current_sink(self) -> Sink | None:
        return self.sinks[self.sel_sink] if self.sinks else None

    def sink_by_index(self, idx: int) -> Sink | None:
        for s in self.sinks:
            if s.index == idx:
                return s
        return None


def _safe_addstr(win, y: int, x: int, text: str, attr=0) -> None:
    h, w = win.getmaxyx()
    if 0 <= y < h and 0 <= x < w:
        win.addstr(y, x, text[: max(0, w - x - 1)], attr)


def _draw(stdscr, st: State) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    mid = w // 2

    title = " ao · audio router "
    _safe_addstr(stdscr, 0, max(0, (w - len(title)) // 2), title, curses.A_BOLD | curses.A_REVERSE)

    # Cabeceras de panel
    left_hdr = "STREAMS (apps)"
    right_hdr = "SALIDAS (sinks)"
    _safe_addstr(stdscr, 2, 2, left_hdr,
                 curses.A_BOLD | (curses.A_UNDERLINE if st.focus == 0 else 0))
    _safe_addstr(stdscr, 2, mid + 2, right_hdr,
                 curses.A_BOLD | (curses.A_UNDERLINE if st.focus == 1 else 0))

    # Panel izquierdo: streams
    if not st.streams:
        _safe_addstr(stdscr, 4, 4, "(ninguna app reproduce audio)", curses.A_DIM)
    for i, sstream in enumerate(st.streams):
        y = 4 + i
        dest = st.sink_by_index(sstream.sink)
        dest_label = dest.short() if dest else f"sink {sstream.sink}"
        marker = "▶ " if (st.focus == 0 and i == st.sel_stream) else "  "
        line = f"{marker}{sstream.label():<16} → {dest_label}"
        attr = curses.A_REVERSE if (st.focus == 0 and i == st.sel_stream) else 0
        if sstream.corked:
            attr |= curses.A_DIM
        _safe_addstr(stdscr, y, 2, line[: mid - 3], attr)

    # Panel derecho: sinks
    for i, sink in enumerate(st.sinks):
        y = 4 + i
        is_def = sink.name == st.default
        marker = "▶ " if (st.focus == 1 and i == st.sel_sink) else "  "
        star = " ★" if is_def else ""
        mute = " (mute)" if sink.muted else ""
        line = f"{marker}{sink.icon} {sink.short()}  {sink.volume_percent}{mute}{star}"
        attr = curses.A_REVERSE if (st.focus == 1 and i == st.sel_sink) else 0
        if is_def:
            attr |= curses.A_BOLD
        _safe_addstr(stdscr, y, mid + 2, line, attr)

    # Mensaje de estado + ayuda
    if st.message:
        _safe_addstr(stdscr, h - 3, 2, st.message[: w - 4], curses.A_BOLD)
    _safe_addstr(stdscr, h - 2, 2, "─" * (w - 4), curses.A_DIM)
    _safe_addstr(stdscr, h - 1, 2, HELP, curses.A_DIM)
    stdscr.refresh()


def _apply_move(st: State) -> None:
    stream = st.current_stream()
    sink = st.current_sink()
    if not stream or not sink:
        st.message = "Nada que mover."
        return
    try:
        backend.move_stream(stream.index, sink.name)
        st.message = f"✓ {stream.label()} → {sink.short()}"
    except BackendError as exc:
        st.message = f"✗ {exc}"
    st.refresh()


def _set_default(st: State) -> None:
    sink = st.current_sink()
    if not sink:
        return
    try:
        backend.set_default(sink.name)
        st.message = f"✓ default → {sink.short()}"
    except BackendError as exc:
        st.message = f"✗ {exc}"
    st.refresh()


def _toggle_mute(st: State) -> None:
    sink = st.current_sink()
    if not sink:
        return
    try:
        backend.toggle_mute(sink.name)
        st.message = f"✓ mute alternado: {sink.short()}"
    except BackendError as exc:
        st.message = f"✗ {exc}"
    st.refresh()


def _loop(stdscr) -> int:
    curses.curs_set(0)
    stdscr.keypad(True)
    st = State()

    while True:
        _draw(stdscr, st)
        ch = stdscr.getch()

        if ch in (ord("q"), 27):  # q o ESC
            return 0
        elif ch in (ord("r"),):
            st.refresh()
            st.message = "Actualizado."
        elif ch in (9, curses.KEY_LEFT, curses.KEY_RIGHT, ord("h"), ord("l")):
            # Tab y flechas horizontales / h l cambian de panel
            if ch in (ord("h"), curses.KEY_LEFT):
                st.focus = 0
            elif ch in (ord("l"), curses.KEY_RIGHT):
                st.focus = 1
            else:
                st.focus ^= 1
        elif ch in (curses.KEY_UP, ord("k")):
            if st.focus == 0 and st.streams:
                st.sel_stream = (st.sel_stream - 1) % len(st.streams)
            elif st.focus == 1 and st.sinks:
                st.sel_sink = (st.sel_sink - 1) % len(st.sinks)
        elif ch in (curses.KEY_DOWN, ord("j")):
            if st.focus == 0 and st.streams:
                st.sel_stream = (st.sel_stream + 1) % len(st.streams)
            elif st.focus == 1 and st.sinks:
                st.sel_sink = (st.sel_sink + 1) % len(st.sinks)
        elif ch in (curses.KEY_ENTER, 10, 13):
            _apply_move(st)
        elif ch in (ord("d"),):
            _set_default(st)
        elif ch in (ord("m"),):
            _toggle_mute(st)


def run() -> int:
    try:
        # Comprobación temprana para dar un error legible fuera de curses.
        backend.list_sinks()
    except BackendError as exc:
        print(f"\033[31mao: {exc}\033[0m")
        return 1
    return curses.wrapper(_loop)
