English | [Français](publication-fr.md)

# Publication preparation

Checks performed on October 27, 2026, covering history reachable from local Git references through
commit `7c34e88` and subsequent preparation changes in the working tree.

## License and scope

MIT was selected for the project's own contributions, declared in `LICENSE`, Python metadata and
the Nix package. It permits reuse with the license notice retained. It grants no rights to the cited
external sources, trademarks or guest software.

See [NOTICE.md](../NOTICE.md) for scope and external dependencies.

## History and publication contents

The eight reachable commits contain 61 file versions totaling 404,134 bytes across 45 distinct paths.
All versions were scanned for private-key signatures, GitHub tokens, AWS keys, plaintext secret
assignments and URLs containing credentials. No matches were found. No file version contains a NUL
byte or exceeds 100 KB; the inventory revealed no ROM, complete manual or proprietary disk image.

Signature scanning does not guarantee the absence of secrets and does not cover unreachable objects,
untracked files or other repositories. Commit author names and email addresses remain in Git history.
Local paths to neighboring projects remain in research notes as provenance; the README provides
standalone instructions.

The `.claude/scheduled_tasks.lock` file was already deleted in the working tree before preparation.
Its historical version contains only session/process identifiers and a local timestamp. `.claude/`
is now ignored. No history was rewritten.

## Knowledge from firmware study

The comparison covered `cmd_match.c`, `boot_input.c` and `data/cmd_data.c` in
Dolphin-Apollo-II-Reborn at the commit listed in [references](references.md).

Command patterns, priorities, clause limits and register values express protocol compatibility rules.
Apolo-emu's tables associate patterns with its own Python handlers, without ROM addresses,
phoneme tables or acoustic data. Its clause accumulator uses a Python buffer rather than emulating
the processor and registers. ASCII conversion maps only characters needed for parsing; it does not
embed the full ROM table.

The old `hex_value` function did closely follow `cmd_hex_value`'s arithmetic in the C decompilation.
It was reformulated using input-value intervals rather than simulating processor instructions.
All 256 results were compared with the previous version to preserve behavior, including values
outside accepted command ranges.

This reformulation neither changes the knowledge's provenance nor removes the old version from
history. It cannot by itself establish absence of infringement. The targeted comparison is not an
exhaustive similarity audit against all consulted software.

## Legal framework and limits

Article 1 of [EU Directive 2009/24/EC](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32009L0024)
distinguishes protected program expression from the ideas and principles underlying interfaces.
Articles 5 and 6 govern studying operation and decompilation for interoperability, subject to conditions.
This distinction motivates separating protocol rules from firmware code; it does not grant blanket
permission to copy or redistribute firmware.

This report records technical checks, not legal advice or certification of the circumstances in which
third parties obtained or decompiled the firmware. `[ROM]` points remain attributed to that secondary
source, and fidelity uncertainties remain documented.

## Technical validation

- Exhaustive `hex_value` comparison before and after the change: all 256 results identical.
- `python3 -m unittest discover -s tests -t .`: 113 tests, successful, one skipped by default
  (actual speech). QEMU integration executed.
- `nix-build --no-out-link`: package and wheel built, suite passed within Nix;
  `LICENSE` and `NOTICE.md` included in the wheel.
- No new actual-speech trial and no neighboring-project VM started.
