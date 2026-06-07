"""Interfaz de línea de comandos de ao (subcomandos rápidos y scriptables)."""

from __future__ import annotations

import argparse
import sys

from . import backend, profiles
from .backend import BackendError
from .profiles import ProfileError, Rule


# --------------------------------------------------------------------------- #
# Helpers de impresión
# --------------------------------------------------------------------------- #
def _err(msg: str) -> int:
    print(f"\033[31mao: {msg}\033[0m", file=sys.stderr)
    return 1


def _ok(msg: str) -> None:
    print(f"\033[32m✓\033[0m {msg}")


def _print_streams_and_sinks() -> None:
    sinks = backend.list_sinks()
    streams = backend.list_streams()
    by_index = {s.index: s for s in sinks}
    default = backend.default_sink_name()

    print("\033[1mSTREAMS (apps reproduciendo)\033[0m")
    if not streams:
        print("  (ninguna app reproduce audio ahora)")
    for st in streams:
        dest = by_index.get(st.sink)
        dest_label = dest.short() if dest else f"sink {st.sink}"
        state = " \033[90m[pausado]\033[0m" if st.corked else ""
        print(f"  [{st.index:>3}] {st.label():<22} → {dest_label}{state}")

    print("\n\033[1mSINKS (salidas disponibles)\033[0m")
    for s in sinks:
        star = " \033[33m★ default\033[0m" if s.name == default else ""
        mute = " \033[90m(mute)\033[0m" if s.muted else ""
        print(f"  [{s.index:>3}] {s.icon} {s.short():<28} vol {s.volume_percent}{mute}{star}")


def _print_sinks_only() -> None:
    default = backend.default_sink_name()
    for s in backend.list_sinks():
        star = " ★" if s.name == default else ""
        print(f"  [{s.index:>3}] {s.icon} {s.short():<28} {s.name}{star}")


# --------------------------------------------------------------------------- #
# Acciones de subcomandos
# --------------------------------------------------------------------------- #
def _do_move(stream_q: str, sink_q: str) -> int:
    sinks = backend.list_sinks()
    sink = backend.resolve_sink(sink_q, sinks)
    stream = backend.resolve_stream(stream_q)

    # Si el alias pide parlantes o jack en el sink analógico, ajusta el port.
    port = backend.port_for_alias(sink, sink_q)
    backend.move_stream(stream.index, sink.name)
    if port:
        backend.set_port(sink.name, port)
    _ok(f"{stream.label()} → {sink.short()}")
    return 0


def _do_default(sink_q: str) -> int:
    sink = backend.resolve_sink(sink_q)
    port = backend.port_for_alias(sink, sink_q)
    backend.set_default(sink.name)
    if port:
        backend.set_port(sink.name, port)
    _ok(f"salida por defecto → {sink.short()}")
    return 0


def _do_port(alias: str) -> int:
    """Atajo: cambia el port del sink analógico entre parlantes y auriculares."""
    sink = backend.resolve_sink("analog")
    port = backend.port_for_alias(sink, alias)
    if not port:
        return _err(f"no encontré el port «{alias}» en la salida analógica.")
    backend.set_port(sink.name, port)
    _ok(f"{sink.description}: port → {alias}")
    return 0


def _do_vol(sink_q: str, pct: str) -> int:
    sink = backend.resolve_sink(sink_q)
    try:
        value = int(pct.rstrip("%"))
    except ValueError:
        return _err(f"volumen inválido: «{pct}» (usa 0-100)")
    backend.set_volume(sink.name, value)
    _ok(f"{sink.short()} → {value}%")
    return 0


def _do_mute(sink_q: str) -> int:
    sink = backend.resolve_sink(sink_q)
    backend.toggle_mute(sink.name)
    _ok(f"mute alternado en {sink.short()}")
    return 0


def _parse_pairs(tokens: list[str]) -> list[Rule]:
    """Convierte ['brave=speakers', 'mpv=bt'] en reglas."""
    rules: list[Rule] = []
    for tok in tokens:
        if "=" not in tok:
            raise ProfileError(f"Regla inválida «{tok}». Usa formato app=salida.")
        app, _, out = tok.partition("=")
        if not app.strip() or not out.strip():
            raise ProfileError(f"Regla inválida «{tok}». Usa formato app=salida.")
        rules.append(Rule(app.strip(), out.strip()))
    return rules


def _do_profile(args) -> int:
    action = args.paction
    if action in (None, "list", "ls"):
        data = profiles.list_profiles()
        if not data:
            print("(no hay perfiles guardados)")
            return 0
        print("\033[1mPERFILES\033[0m")
        for name, rules in data.items():
            print(f"  \033[36m{name}\033[0m")
            for r in rules:
                print(f"      {r.app:<18} → {r.output}")
        return 0

    if action == "show":
        rules = profiles.get_profile(args.name)
        print(f"\033[1m{args.name}\033[0m")
        for r in rules:
            print(f"  {r.app:<18} → {r.output}")
        return 0

    if action == "save":
        if args.pairs:
            rules = _parse_pairs(args.pairs)
        else:
            rules = profiles.capture_current()  # snapshot del estado actual
            print("Capturado el estado actual:")
            for r in rules:
                print(f"  {r.app:<18} → {r.output}")
        profiles.save_profile(args.name, rules)
        _ok(f"perfil «{args.name}» guardado ({len(rules)} reglas)")
        return 0

    if action == "apply":
        results = profiles.apply_profile(args.name)
        print(f"\033[1mAplicando «{args.name}»\033[0m")
        for line in results:
            print(f"  {line}")
        return 0

    if action in ("rm", "delete"):
        profiles.delete_profile(args.name)
        _ok(f"perfil «{args.name}» eliminado")
        return 0

    if action == "rename":
        profiles.rename_profile(args.old, args.new)
        _ok(f"perfil «{args.old}» → «{args.new}»")
        return 0

    return _err(f"acción de perfil desconocida: {action}")


def _do_doctor() -> int:
    """Detecta el stack de sonido y el hardware disponible."""
    import shutil

    server = backend.detect_backend()
    label = {
        "pipewire": "PipeWire (compatibilidad PulseAudio)",
        "pulseaudio": "PulseAudio nativo",
        "unknown": "desconocido",
    }[server]
    print("\033[1mao · diagnóstico\033[0m")
    print(f"  servidor de sonido : {label}")
    print(f"  pactl              : {'sí' if shutil.which('pactl') else 'NO ENCONTRADO'}")

    info = backend.server_info()
    if info:
        print(f"  servidor           : {info.get('Server Name', '?')} {info.get('Server Version', '')}")
        print(f"  default sink       : {info.get('Default Sink', '?')}")

    cards = backend.list_cards()
    print(f"\n  tarjetas ({len(cards)}):")
    for c in cards:
        print(f"    • {c.get('name')}  [perfil: {c.get('active_profile')}]")

    sinks = backend.list_sinks()
    print(f"\n  salidas ({len(sinks)}):")
    for s in sinks:
        print(f"    • {s.icon} {s.short()}  [{s.kind}]")
    return 0


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ao",
        description="ao · enruta el audio de cada app a la salida que quieras "
        "(PipeWire/PulseAudio). Sin argumentos abre la TUI interactiva.",
        epilog="Alias de salida: bt, speakers/spk, headphones/jack/hp, hdmi, "
        "o cualquier subcadena del nombre/descripción del sink.",
    )
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("tui", help="abrir la interfaz interactiva (por defecto)")
    sub.add_parser("list", aliases=["ls"], help="listar apps y salidas")
    sub.add_parser("sinks", help="listar solo las salidas")
    sub.add_parser("doctor", aliases=["info"], help="detectar el stack de sonido y el hardware")

    m = sub.add_parser("move", aliases=["to"], help="mover una app a una salida")
    m.add_argument("stream", help="app a mover (subcadena o índice), ej. mpv")
    m.add_argument("sink", help="salida destino (alias/subcadena/índice), ej. bt")

    d = sub.add_parser("default", aliases=["def"], help="fijar la salida por defecto")
    d.add_argument("sink", help="salida (alias/subcadena/índice)")

    sub.add_parser("speakers", aliases=["spk"], help="salida analógica → parlantes")
    sub.add_parser("headphones", aliases=["hp", "jack"], help="salida analógica → jack")

    v = sub.add_parser("vol", help="fijar volumen de una salida")
    v.add_argument("sink", help="salida (alias/subcadena/índice)")
    v.add_argument("percent", help="volumen 0-100")

    mu = sub.add_parser("mute", help="alternar silencio de una salida")
    mu.add_argument("sink", help="salida (alias/subcadena/índice)")

    # ----- perfiles (configuraciones nombradas: CRUD) -----
    prof = sub.add_parser(
        "profile",
        aliases=["p"],
        help="gestionar perfiles de enrutamiento (configuraciones guardadas)",
    )
    pa = prof.add_subparsers(dest="paction")
    pa.add_parser("list", aliases=["ls"], help="listar perfiles")
    ps = pa.add_parser("show", help="ver las reglas de un perfil")
    ps.add_argument("name")
    psave = pa.add_parser(
        "save",
        help="guardar perfil; sin pares app=salida captura el estado actual",
    )
    psave.add_argument("name")
    psave.add_argument(
        "pairs", nargs="*", help="reglas app=salida, ej. brave=speakers mpv=bt"
    )
    papply = pa.add_parser("apply", help="aplicar un perfil a las apps actuales")
    papply.add_argument("name")
    prm = pa.add_parser("rm", aliases=["delete"], help="eliminar un perfil")
    prm.add_argument("name")
    pren = pa.add_parser("rename", help="renombrar un perfil")
    pren.add_argument("old")
    pren.add_argument("new")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.cmd in (None, "tui"):
            from .tui import run as run_tui

            return run_tui()
        if args.cmd in ("list", "ls"):
            _print_streams_and_sinks()
            return 0
        if args.cmd == "sinks":
            _print_sinks_only()
            return 0
        if args.cmd in ("doctor", "info"):
            return _do_doctor()
        if args.cmd in ("move", "to"):
            return _do_move(args.stream, args.sink)
        if args.cmd in ("default", "def"):
            return _do_default(args.sink)
        if args.cmd in ("speakers", "spk"):
            return _do_port("speakers")
        if args.cmd in ("headphones", "hp", "jack"):
            return _do_port("headphones")
        if args.cmd == "vol":
            return _do_vol(args.sink, args.percent)
        if args.cmd == "mute":
            return _do_mute(args.sink)
        if args.cmd in ("profile", "p"):
            return _do_profile(args)
    except (BackendError, ProfileError) as exc:
        return _err(str(exc))
    except KeyboardInterrupt:
        return 130

    parser.print_help()
    return 0
