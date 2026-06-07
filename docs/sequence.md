# Sequences

Step-by-step behavior of the two most important operations.

## 1. Moving one application to an output

Example: `ao move brave speakers`, where the analog card is currently **off**.

```mermaid
sequenceDiagram
    actor U as User
    participant CLI as ao.cli
    participant B as ao.backend
    participant P as pactl
    participant S as Sound server

    U->>CLI: ao move brave speakers
    CLI->>B: resolve_sink("speakers")
    B->>P: pactl -f json list sinks
    P->>S: query sinks
    S-->>P: sinks JSON
    P-->>B: (no analog sink — card is off)

    Note over B: alias "speakers" → kind "analog"<br/>no sink found → try to power on a card
    B->>P: pactl get-default-sink
    P-->>B: previous default (e.g. bluetooth)
    B->>P: pactl set-card-profile <card> output:analog-stereo
    P->>S: activate profile
    B->>P: pactl set-default-sink <previous default>
    Note over B: restore default → no surprise output switch

    B->>P: pactl -f json list sinks
    P-->>B: now includes analog sink
    B-->>CLI: Sink(analog)

    CLI->>B: resolve_stream("brave")
    B->>P: pactl -f json list sink-inputs
    P-->>B: matching stream
    CLI->>B: move_stream(stream, analog) [+ set speaker port]
    B->>P: pactl move-sink-input / set-sink-port
    P->>S: reroute stream
    S-->>U: 🔊 Brave now plays on speakers
    CLI-->>U: ✓ Brave → Laptop Speakers
```

The important detail is the **save/restore of the default sink**: powering on a card would
normally make the session manager promote the new device to default. `ao` restores the
prior default so the global routing of *other* apps does not change.

## 2. Applying a saved profile

Example: `ao profile apply work`, with rules `brave=speakers`, `slack=bt`.

```mermaid
sequenceDiagram
    actor U as User
    participant CLI as ao.cli
    participant PR as ao.profiles
    participant B as ao.backend
    participant P as pactl

    U->>CLI: ao profile apply work
    CLI->>PR: apply_profile("work")
    PR->>PR: load ~/.config/ao/profiles.json
    loop for each rule (app → output)
        PR->>B: resolve_sink(output alias)
        B->>P: list sinks (+ power on card if needed)
        P-->>B: sink
        B-->>PR: sink
        PR->>B: list_streams() and match app substring
        alt app is playing
            PR->>B: move_stream(stream, sink)
            B->>P: pactl move-sink-input
            PR-->>CLI: ✓ moved
        else app not playing
            PR-->>CLI: – rule kept for later
        end
    end
    CLI-->>U: per-rule results
```

Profiles only act on streams that are currently playing; rules for apps that are not
running are reported and kept, ready for next time.
