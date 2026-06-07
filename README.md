# ao · audio router

**`ao`** is a terminal utility to **route each application's audio to the output you want**
on Linux: send your terminal music player to the Bluetooth headphones while the browser's
news keep playing on the laptop speakers — at the same time.

It works on **PipeWire** (via `pipewire-pulse`) and on native **PulseAudio**. Zero
dependencies: only Python ≥ 3.9 standard library and `pactl`.

```
┌─ ao · audio router ────────────────────────────┐
│ STREAMS (apps)         OUTPUTS (sinks)          │
│ ▶ mpv     → Headset    🎧 Bluetooth Headset ★   │
│   brave   → Speakers   🔊 Laptop Speakers       │
│                        🖥️ HDMI                    │
│ [↑↓] move [Tab] panel [Enter] apply [q] quit    │
└─────────────────────────────────────────────────┘
```

> The interactive UI and CLI messages are currently in Spanish; English/i18n is on the
> roadmap. The concepts and commands below are the source of truth.

## Why

GUI tools (`pavucontrol`, `helvum`) are powerful but slow for an everyday task. Raw
`wpctl`/`pactl` make you copy long names like `alsa_output.pci-0000_00_1f.3.analog-stereo`.
`ao` fills that gap with a **keyboard-driven TUI**, **short aliases** (`bt`, `speakers`,
`hdmi`…), **saved routing profiles**, and it **powers on a sound card automatically** when
you target an output whose card is currently off — without hijacking your default output.

## Design principles

- **Your defaults stay normal.** `ao` never changes the system's default output as a side
  effect. It only moves the specific streams you ask it to. New apps keep following the
  normal policy until *you* decide otherwise.
- **Hardware-agnostic.** Nothing is hard-coded to a machine. Outputs are addressed by
  semantic aliases (`bt`, `speakers`, `headphones`, `hdmi`) or substrings, so profiles are
  portable across machines and survive device reconnections.
- **No daemon.** `ao` is a one-shot tool. It does not run in the background.

## Install

### With pipx (recommended)
```bash
pipx install ao-audio-router
# or from a checkout:
pipx install .
```

### With the bundled installer (no pipx required)
```bash
./install.sh        # uses pipx if present, otherwise a self-contained venv
```

### With pip
```bash
pip install --user ao-audio-router
```

**System requirement:** `pactl` (package `pipewire-pulse` on PipeWire, or
`pulseaudio-utils` / `libpulse` on PulseAudio). `pactl >= 16` for JSON output.

Run `ao doctor` after installing to confirm your sound stack is detected.

## Usage

### Interactive TUI
```bash
ao            # opens the interface
```
| Key | Action |
|-----|--------|
| `↑`/`↓` or `j`/`k` | move selection |
| `Tab` or `←`/`→` | switch panel (apps ↔ outputs) |
| `Enter` | move the selected app to the selected output |
| `d` | set the output as default |
| `m` | mute/unmute the output |
| `r` | refresh |
| `q` | quit |

### CLI
```bash
ao list                  # apps currently playing + available outputs
ao doctor                # detect sound server, cards and outputs
ao sinks                 # outputs only

ao move mpv bt           # send mpv to the Bluetooth headphones
ao to brave speakers     # 'to' is an alias of 'move'
ao move brave 42         # also by sink index

ao default bt            # set the default output
ao speakers / headphones # switch the analog output port (speakers ↔ jack)
ao vol bt 30 / ao mute speakers
```

### Output aliases
`bt` · `bluetooth` · `speakers`/`spk`/`laptop` · `headphones`/`hp`/`jack` · `hdmi`/`dp`,
or **any substring** of the sink name/description, or its numeric index.

### Profiles (saved routing presets)
Named sets of `app → output` rules. Outputs are stored as portable aliases, so a profile
made on one machine works on another.
```bash
ao profile save work brave=speakers slack=bt   # define rules explicitly
ao profile save now                            # or snapshot what's playing right now
ao profile list
ao profile show work
ao profile apply work                          # move current matching apps
ao profile rename work office
ao profile rm office
```
Profiles live in `~/.config/ao/profiles.json`. Applying a profile only moves the streams
that are currently playing; rules for apps that aren't running are kept for later.

## How it works

`ao` does not reimplement audio. It translates friendly names and actions into `pactl`
calls (`move-sink-input`, `set-default-sink`, `set-sink-port`, `set-card-profile`) and
reads state with `pactl -f json`. See [`docs/`](docs/) for architecture, sequence and
use-case diagrams.

## A note about laptop hardware

On many laptops the **internal speakers and the wired headphone jack are the same device**
(one codec DAC): they can't play at once or take different apps. `ao speakers` /
`ao headphones` switch the active *port*. True multiplexing happens between **separate
devices** (analog codec ↔ Bluetooth ↔ HDMI), which is exactly what `ao` makes easy.

## License

MIT — see [LICENSE](LICENSE).
