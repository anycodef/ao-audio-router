"""Perfiles de enrutamiento: configuraciones nombradas y persistentes.

Un perfil es una lista de reglas «app → salida». Las salidas se guardan como
*alias semánticos* (bt, speakers, headphones, hdmi, o una subcadena), nunca como
nombres de dispositivo concretos: así el perfil es portable entre equipos y
sobrevive a reconexiones de Bluetooth, cambios de tarjeta, etc.

Almacenamiento: JSON en $XDG_CONFIG_HOME/ao/profiles.json (por defecto
~/.config/ao/profiles.json).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from . import backend
from .backend import BackendError


class ProfileError(RuntimeError):
    """Error de gestión de perfiles."""


@dataclass
class Rule:
    app: str  # subcadena del nombre de la app, ej. "brave"
    output: str  # alias o subcadena de la salida, ej. "speakers"

    def to_dict(self) -> dict:
        return {"app": self.app, "output": self.output}


# --------------------------------------------------------------------------- #
# Ubicación y E/S
# --------------------------------------------------------------------------- #
def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "ao"


def _config_file() -> Path:
    return config_dir() / "profiles.json"


def _load_raw() -> dict[str, list[dict]]:
    path = _config_file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise ProfileError(f"No se pudo leer {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError(f"Formato inválido en {path}.")
    return data


def _save_raw(data: dict[str, list[dict]]) -> None:
    path = _config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)  # escritura atómica


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
def list_profiles() -> dict[str, list[Rule]]:
    raw = _load_raw()
    return {
        name: [Rule(r.get("app", ""), r.get("output", "")) for r in rules]
        for name, rules in raw.items()
    }


def get_profile(name: str) -> list[Rule]:
    raw = _load_raw()
    if name not in raw:
        raise ProfileError(f"El perfil «{name}» no existe.")
    return [Rule(r.get("app", ""), r.get("output", "")) for r in raw[name]]


def save_profile(name: str, rules: list[Rule]) -> None:
    if not name.strip():
        raise ProfileError("El nombre del perfil no puede estar vacío.")
    if not rules:
        raise ProfileError("Un perfil necesita al menos una regla app→salida.")
    raw = _load_raw()
    raw[name] = [r.to_dict() for r in rules]
    _save_raw(raw)


def delete_profile(name: str) -> None:
    raw = _load_raw()
    if name not in raw:
        raise ProfileError(f"El perfil «{name}» no existe.")
    del raw[name]
    _save_raw(raw)


def rename_profile(old: str, new: str) -> None:
    raw = _load_raw()
    if old not in raw:
        raise ProfileError(f"El perfil «{old}» no existe.")
    if not new.strip():
        raise ProfileError("El nuevo nombre no puede estar vacío.")
    if new in raw:
        raise ProfileError(f"Ya existe un perfil llamado «{new}».")
    raw[new] = raw.pop(old)
    _save_raw(raw)


# --------------------------------------------------------------------------- #
# Captura y aplicación
# --------------------------------------------------------------------------- #
def _sink_to_alias(sink) -> str:
    """Convierte un sink concreto en un alias portable."""
    if sink.kind == "bluetooth":
        return "bt"
    if sink.kind == "hdmi":
        return "hdmi"
    if sink.kind == "analog":
        # distingue parlantes de auriculares según el port activo
        port = (sink.active_port or "").lower()
        if "headphone" in port:
            return "headphones"
        return "speakers"
    # último recurso: una subcadena estable de la descripción
    return (sink.description or sink.name).split()[0].lower()


def capture_current() -> list[Rule]:
    """Crea reglas a partir de las apps que reproducen ahora mismo."""
    sinks = backend.list_sinks()
    by_index = {s.index: s for s in sinks}
    rules: list[Rule] = []
    for st in backend.list_streams():
        sink = by_index.get(st.sink)
        if not sink:
            continue
        app = (st.app or st.binary).strip()
        if not app:
            continue
        rules.append(Rule(app=app, output=_sink_to_alias(sink)))
    if not rules:
        raise ProfileError("No hay apps reproduciendo audio para capturar.")
    return rules


def apply_profile(name: str) -> list[str]:
    """Aplica un perfil a los streams actuales. Devuelve líneas de resultado.

    No cambia la salida por defecto: solo reubica los streams que coinciden,
    respetando el comportamiento normal del sistema para todo lo demás.
    """
    rules = get_profile(name)
    sinks = backend.list_sinks()
    streams = backend.list_streams()
    results: list[str] = []

    for rule in rules:
        # resuelve la salida (puede encender una tarjeta apagada sin tocar el default)
        try:
            sink = backend.resolve_sink(rule.output, sinks)
        except BackendError as exc:
            results.append(f"✗ {rule.app} → {rule.output}: {exc}")
            continue
        # re-lista por si la resolución activó una tarjeta nueva
        sinks = backend.list_sinks()
        port = backend.port_for_alias(sink, rule.output)

        matched = [
            st
            for st in streams
            if rule.app.lower() in (st.app or "").lower()
            or rule.app.lower() in (st.binary or "").lower()
        ]
        if not matched:
            results.append(f"– {rule.app}: no está reproduciendo (regla guardada)")
            continue
        for st in matched:
            try:
                backend.move_stream(st.index, sink.name)
                if port:
                    backend.set_port(sink.name, port)
                results.append(f"✓ {st.label()} → {sink.short()}")
            except BackendError as exc:
                results.append(f"✗ {st.label()} → {sink.short()}: {exc}")
    return results
