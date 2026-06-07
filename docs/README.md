# ao · documentation

Technical documentation for **ao**, the per-application audio router for Linux
(PipeWire / PulseAudio).

- [Architecture](architecture.md) — how `ao` sits on top of the Linux audio stack,
  from low-level hardware to the user-facing command. Component and layer diagrams.
- [Sequences](sequence.md) — what happens, step by step, when you move a stream or
  apply a profile. Sequence diagrams.
- [Use case](use-case.md) — a representative end-to-end scenario, with diagrams.

> These documents are intentionally **hardware-agnostic**. `ao` is general-purpose: it
> detects the available sound server and devices at runtime (`ao doctor`) and never
> hard-codes machine-specific names.
