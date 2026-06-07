#!/usr/bin/env bash
# Installer for `ao`. Prefers pipx; falls back to a self-contained venv.
# Works on any Linux distro without touching system packages (no sudo needed
# for the venv path). Re-run to upgrade.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
VENV_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/ao/venv"

note() { printf '\033[36m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*"; }
ok()   { printf '\033[32m✓ %s\033[0m\n' "$*"; }

# --- runtime requirement check (general, distro-agnostic) -------------------
if ! command -v pactl >/dev/null 2>&1; then
  warn "Warning: 'pactl' was not found."
  warn "Install it via your distro: pipewire-pulse (PipeWire) or pulseaudio-utils (PulseAudio)."
fi

# --- install ----------------------------------------------------------------
if command -v pipx >/dev/null 2>&1; then
  note "pipx detected — installing with pipx…"
  pipx install --force "$PROJECT_DIR"
  ok "Installed with pipx. Run: ao doctor"
  exit 0
fi

note "pipx not found — installing into a dedicated venv at $VENV_DIR"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet "$PROJECT_DIR"

mkdir -p "$BIN_DIR"
ln -sf "$VENV_DIR/bin/ao" "$BIN_DIR/ao"
ok "Installed. Symlink: $BIN_DIR/ao -> $VENV_DIR/bin/ao"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) warn "Note: $BIN_DIR is not in your PATH. Add it to your shell profile." ;;
esac

note "Run: ao doctor"
