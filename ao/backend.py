"""Backend de ao: capa que habla con el servidor de sonido vía `pactl`.

Funciona sobre PipeWire (mediante pipewire-pulse) y sobre PulseAudio nativo,
porque solo usa la API de PulseAudio expuesta por `pactl`. Sin dependencias
externas: únicamente la librería estándar de Python.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field


class BackendError(RuntimeError):
    """Error al comunicarse con pactl / el servidor de sonido."""


# --------------------------------------------------------------------------- #
# Modelos
# --------------------------------------------------------------------------- #
@dataclass
class Sink:
    index: int
    name: str
    description: str
    state: str
    active_port: str | None
    ports: list[dict] = field(default_factory=list)
    volume_percent: str = "?"
    muted: bool = False

    @property
    def kind(self) -> str:
        """Clasificación amigable de la salida."""
        n = self.name.lower()
        if n.startswith("bluez_output") or "bluez" in n:
            return "bluetooth"
        if "hdmi" in n or "hdmi" in (self.active_port or "").lower():
            return "hdmi"
        if "analog" in n:
            return "analog"
        return "other"

    @property
    def icon(self) -> str:
        return {"bluetooth": "🎧", "hdmi": "🖥️", "analog": "🔊"}.get(self.kind, "🔈")

    def short(self) -> str:
        """Etiqueta corta para mostrar (ej. 'Sesh Evo (BT)')."""
        tag = {"bluetooth": "BT", "hdmi": "HDMI", "analog": "jack/spk"}.get(self.kind, "")
        desc = self.description or self.name
        return f"{desc} ({tag})" if tag else desc


@dataclass
class Stream:
    """Un sink-input: el audio que una aplicación reproduce hacia un sink."""

    index: int
    sink: int
    app: str
    media: str
    binary: str
    corked: bool = False
    volume_percent: str = "?"

    def label(self) -> str:
        name = self.app or self.binary or f"stream {self.index}"
        return name


# --------------------------------------------------------------------------- #
# Llamadas a pactl
# --------------------------------------------------------------------------- #
def _ensure_pactl() -> str:
    path = shutil.which("pactl")
    if not path:
        raise BackendError(
            "No se encontró 'pactl'. Instala pipewire-pulse (PipeWire) "
            "o pulseaudio-utils (PulseAudio)."
        )
    return path


def _run(args: list[str], capture: bool = True) -> str:
    _ensure_pactl()
    try:
        proc = subprocess.run(
            ["pactl", *args],
            check=True,
            text=True,
            capture_output=capture,
        )
    except subprocess.CalledProcessError as exc:
        msg = (exc.stderr or "").strip() or f"pactl {' '.join(args)} falló"
        raise BackendError(msg) from exc
    return proc.stdout if capture else ""


def _run_json(subcommand: str):
    out = _run(["-f", "json", "list", subcommand])
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:  # pactl muy antiguo sin soporte JSON
        raise BackendError(
            "Tu versión de pactl no soporta salida JSON (se requiere pactl >= 16)."
        ) from exc


# --------------------------------------------------------------------------- #
# Lecturas
# --------------------------------------------------------------------------- #
def list_sinks() -> list[Sink]:
    sinks: list[Sink] = []
    for s in _run_json("sinks"):
        vol = "?"
        if isinstance(s.get("volume"), dict) and s["volume"]:
            first = next(iter(s["volume"].values()))
            vol = first.get("value_percent", "?")
        sinks.append(
            Sink(
                index=s["index"],
                name=s["name"],
                description=s.get("description", ""),
                state=s.get("state", ""),
                active_port=s.get("active_port"),
                ports=s.get("ports", []) or [],
                volume_percent=vol,
                muted=bool(s.get("mute", False)),
            )
        )
    return sinks


def list_streams() -> list[Stream]:
    streams: list[Stream] = []
    for si in _run_json("sink-inputs"):
        props = si.get("properties", {}) or {}
        vol = "?"
        if isinstance(si.get("volume"), dict) and si["volume"]:
            first = next(iter(si["volume"].values()))
            vol = first.get("value_percent", "?")
        streams.append(
            Stream(
                index=si["index"],
                sink=si.get("sink", -1),
                app=props.get("application.name", ""),
                media=props.get("media.name", ""),
                binary=props.get("application.process.binary", ""),
                corked=bool(si.get("corked", False)),
                volume_percent=vol,
            )
        )
    return streams


def default_sink_name() -> str:
    return _run(["get-default-sink"]).strip()


def list_cards() -> list[dict]:
    """Tarjetas con sus perfiles (incluye las apagadas, perfil 'off')."""
    return _run_json("cards")


def server_info() -> dict[str, str]:
    """Devuelve los campos de `pactl info` como diccionario."""
    info: dict[str, str] = {}
    for line in _run(["info"]).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            info[key.strip()] = value.strip()
    return info


def detect_backend() -> str:
    """Identifica el servidor de sonido subyacente: 'pipewire', 'pulseaudio' u 'unknown'."""
    try:
        name = server_info().get("Server Name", "")
    except BackendError:
        return "unknown"
    low = name.lower()
    if "pipewire" in low:
        return "pipewire"
    if "pulseaudio" in low:
        return "pulseaudio"
    return "unknown"


# --------------------------------------------------------------------------- #
# Acciones
# --------------------------------------------------------------------------- #
def move_stream(stream_index: int, sink_name: str) -> None:
    _run(["move-sink-input", str(stream_index), sink_name], capture=False)


def set_default(sink_name: str) -> None:
    _run(["set-default-sink", sink_name], capture=False)


def set_port(sink_name: str, port: str) -> None:
    _run(["set-sink-port", sink_name, port], capture=False)


def set_volume(sink_name: str, percent: int) -> None:
    _run(["set-sink-volume", sink_name, f"{percent}%"], capture=False)


def set_card_profile(card_name: str, profile: str) -> None:
    _run(["set-card-profile", card_name, profile], capture=False)


def toggle_mute(sink_name: str) -> None:
    _run(["set-sink-mute", sink_name, "toggle"], capture=False)


# --------------------------------------------------------------------------- #
# Resolución de nombres amigables ("bt", "speakers", "hdmi", subcadenas...)
# --------------------------------------------------------------------------- #
_ALIASES = {
    "bt": "bluetooth",
    "bluetooth": "bluetooth",
    "bluez": "bluetooth",
    "spk": "speakers",
    "speaker": "speakers",
    "speakers": "speakers",
    "laptop": "speakers",
    "hp": "headphones",
    "jack": "headphones",
    "headphone": "headphones",
    "headphones": "headphones",
    "hdmi": "hdmi",
    "dp": "hdmi",
}


def _kind_for_alias(alias: str | None) -> str | None:
    if alias == "bluetooth":
        return "bluetooth"
    if alias == "hdmi":
        return "hdmi"
    if alias in ("speakers", "headphones"):
        return "analog"
    return None


# Prefijos de perfil a activar por tipo de salida, en orden de preferencia.
_PROFILE_PREFIX = {
    "analog": ("output:analog-stereo",),
    "hdmi": ("output:hdmi-stereo",),
}


def _try_activate_card(kind: str) -> bool:
    """Si existe una tarjeta apagada que puede dar este tipo de salida, la enciende.

    Preserva la salida por defecto del usuario: encender una tarjeta no debe
    "secuestrar" el destino global (el gestor de sesión tiende a promover el
    dispositivo recién aparecido a predeterminado). Devuelve True si activó algún
    perfil (y conviene re-listar los sinks).
    """
    prefixes = _PROFILE_PREFIX.get(kind)
    if not prefixes:
        return False  # p.ej. bluetooth: depende de que el dispositivo esté conectado

    previous_default = default_sink_name()
    for card in list_cards():
        if card.get("active_profile") not in (None, "off"):
            continue  # ya está activa; su sink debería existir
        profiles = card.get("profiles") or {}
        for prefix in prefixes:
            # coincidencia exacta primero, luego cualquier perfil que empiece igual
            candidates = [prefix] + [p for p in profiles if p.startswith(prefix)]
            for pname in candidates:
                info = profiles.get(pname)
                if info and info.get("available"):
                    try:
                        set_card_profile(card["name"], pname)
                    except BackendError:
                        continue
                    # Restaura el destino global: el usuario manda hasta que
                    # decida lo contrario explícitamente.
                    if previous_default:
                        try:
                            set_default(previous_default)
                        except BackendError:
                            pass
                    return True
    return False


def resolve_sink(query: str, sinks: list[Sink] | None = None) -> Sink:
    """Encuentra un sink por alias, índice, nombre o descripción (subcadena).

    Si se pide un tipo de salida (speakers/headphones/hdmi) cuya tarjeta está
    apagada, intenta encenderla automáticamente antes de fallar.
    """
    sinks = sinks if sinks is not None else list_sinks()
    q = query.strip()
    alias = _ALIASES.get(q.lower())

    def _search(pool: list[Sink]) -> Sink | None:
        # Por índice numérico exacto
        if q.isdigit():
            for s in pool:
                if s.index == int(q):
                    return s
        # Por alias semántico (tipo de salida)
        kind = _kind_for_alias(alias)
        if kind:
            for s in pool:
                if s.kind == kind:
                    return s
        # Por subcadena en nombre o descripción
        ql = q.lower()
        for s in pool:
            if ql in s.name.lower() or ql in (s.description or "").lower():
                return s
        return None

    found = _search(sinks)
    if found:
        return found

    # No existe el sink: si el alias pide un tipo cuya tarjeta está apagada, encenderla.
    kind = _kind_for_alias(alias)
    if kind and _try_activate_card(kind):
        found = _search(list_sinks())
        if found:
            return found

    if not sinks:
        raise BackendError("No hay sinks (salidas) disponibles.")
    raise BackendError(f"No se encontró ninguna salida que coincida con «{query}».")


def port_for_alias(sink: Sink, alias_query: str) -> str | None:
    """Si el alias pide speakers/headphones en un sink analógico, devuelve el port."""
    alias = _ALIASES.get(alias_query.strip().lower())
    if sink.kind != "analog" or alias not in ("speakers", "headphones"):
        return None
    target_type = "Speaker" if alias == "speakers" else "Headphones"
    for p in sink.ports:
        if p.get("type", "").lower() == target_type.lower():
            return p.get("name")
    # heurística por nombre del port
    key = "speaker" if alias == "speakers" else "headphone"
    for p in sink.ports:
        if key in p.get("name", "").lower():
            return p.get("name")
    return None


def resolve_stream(query: str, streams: list[Stream] | None = None) -> Stream:
    """Encuentra un stream por índice o por subcadena del nombre de la app."""
    streams = streams if streams is not None else list_streams()
    if not streams:
        raise BackendError("No hay aplicaciones reproduciendo audio ahora mismo.")

    q = query.strip()
    if q.isdigit():
        for st in streams:
            if st.index == int(q):
                return st

    ql = q.lower()
    matches = [
        st
        for st in streams
        if ql in st.app.lower() or ql in st.binary.lower() or ql in st.media.lower()
    ]
    if not matches:
        raise BackendError(f"No hay ninguna app reproduciendo que coincida con «{query}».")
    return matches[0]
