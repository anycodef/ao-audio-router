# Architecture

`ao` is a thin, stateless controller on top of the standard Linux audio stack. It does
**not** process audio; it reads state and issues routing commands through `pactl`, the
PulseAudio control client (which also drives PipeWire via `pipewire-pulse`). This keeps
`ao` portable across distributions and across both sound servers.

## Where `ao` sits in the Linux audio stack

From the lowest-level hardware up to the command you type:

```mermaid
flowchart TB
    subgraph USER["User space — ao"]
        AOCLI["ao CLI / TUI"]
        AOBACK["ao.backend<br/>(pactl wrapper + name resolution)"]
        AOPROF["ao.profiles<br/>(saved presets, JSON)"]
        AOCLI --> AOBACK
        AOCLI --> AOPROF
        AOPROF --> AOBACK
    end

    subgraph CTL["Control plane"]
        PACTL["pactl<br/>(PulseAudio control protocol)"]
    end

    subgraph SERVER["Sound server (user space)"]
        PWPULSE["pipewire-pulse<br/>(Pulse API shim)"]
        PIPEWIRE["pipewire<br/>(media graph)"]
        WP["WirePlumber<br/>(session & policy manager)"]
        PULSE["— or — PulseAudio<br/>(native server)"]
    end

    subgraph KERNEL["Kernel"]
        ALSA["ALSA core (snd_pcm)"]
        DRIVERS["Card drivers<br/>(snd_hda_intel, snd_sof, bluez, usb-audio…)"]
    end

    subgraph HW["Hardware"]
        SPK["🔊 Speakers / 🎧 jack<br/>(shared analog codec)"]
        BT["🎧 Bluetooth"]
        HDMI["🖥️ HDMI / DisplayPort"]
        USB["🎚️ USB audio"]
    end

    AOBACK --> PACTL
    PACTL --> PWPULSE
    PACTL -.native.-> PULSE
    PWPULSE --> PIPEWIRE
    PIPEWIRE <--> WP
    PULSE --> ALSA
    PIPEWIRE --> ALSA
    ALSA --> DRIVERS
    DRIVERS --> SPK
    DRIVERS --> BT
    DRIVERS --> HDMI
    DRIVERS --> USB
```

**Reading the layers (bottom → top):**

1. **Hardware** — the physical transducers and links (speakers, headphone jack, Bluetooth,
   HDMI, USB audio).
2. **Kernel / ALSA** — drivers expose each output as a PCM device.
3. **Sound server** — PipeWire (with WirePlumber as the policy manager) or native
   PulseAudio builds a graph of *nodes* and decides who connects to whom.
4. **Control plane** — `pactl` speaks the PulseAudio control protocol to the server.
5. **ao** — translates friendly intent ("move mpv to bluetooth") into control commands.

## Internal components

```mermaid
flowchart LR
    subgraph CLI["ao.cli"]
        ARGS["argparse dispatch"]
        FMT["formatted output"]
    end
    subgraph TUI["ao.tui"]
        CURSES["curses two-panel UI"]
    end
    subgraph BACKEND["ao.backend"]
        MODELS["Sink / Stream models"]
        RESOLVE["resolve_sink / resolve_stream<br/>(aliases, substrings, index)"]
        ACTIVATE["auto power-on cards<br/>(preserves default)"]
        ACTIONS["move / default / port / volume"]
        PACTLIO["pactl JSON I/O"]
    end
    subgraph PROFILES["ao.profiles"]
        CRUD["CRUD (JSON store)"]
        CAPTURE["capture_current()"]
        APPLY["apply_profile()"]
    end

    ARGS --> RESOLVE
    ARGS --> CRUD
    CURSES --> ACTIONS
    RESOLVE --> PACTLIO
    ACTIONS --> PACTLIO
    ACTIVATE --> PACTLIO
    RESOLVE --> ACTIVATE
    APPLY --> RESOLVE
    APPLY --> ACTIONS
    CAPTURE --> MODELS
    CRUD --> APPLY
```

### Key design decisions

| Decision | Rationale |
|----------|-----------|
| Drive `pactl`, not the PipeWire/Pulse C APIs | One code path works on PipeWire *and* PulseAudio; no compiled bindings. |
| Address outputs by **semantic alias** (`bt`, `speakers`, …) | Portable across machines; profiles survive device reconnection. |
| **Never** change the default output as a side effect | The system's "normal" behavior is preserved until the user asks otherwise. |
| Auto power-on a card, then **restore the previous default** | Targeting `speakers` works even if the card was off, without hijacking output. |
| No daemon; one-shot commands + on-demand profile apply | Predictable; nothing runs in the background unexpectedly. |
