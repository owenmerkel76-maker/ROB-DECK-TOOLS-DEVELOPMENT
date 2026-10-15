# RESIDENTIALTOOLS

Residential deck/framing pyRevit extension for **Revit 2025 and 2027**.

## Download 2026.10.14.1

**[Download the new tools ZIP](downloads/RESIDENTIALTOOLS-2026.10.14.1.zip?raw=true)** · [SHA-256](downloads/RESIDENTIALTOOLS-2026.10.14.1.sha256) · [Delivery manifest](downloads/DELIVERY_FILES.json)

This is a **field-test build**. All nine current tools and shared code were reviewed. The source and ZIP pass **103 local tests with zero packaging validation errors**, including IronPython-compatible runtime syntax, YAML, bundle/icons, ownership and layout/quantity checks. Eight sample WPF screens were rendered and visually reviewed offscreen. Native Revit execution by the agent remains **NOT RUN**; family flex, hardware seating/orientation and stair/railing behavior require testing in each supported version.

## Install / update

1. Download the ZIP above. Extract its single `RESIDENTIALTOOLS.extension` folder into your pyRevit extension location, replacing your previous RESIDENTIALTOOLS copy.
2. Keep one enabled copy. Do not nest it inside another `.extension` folder. Other extensions, including ROBMEPTOOLS, are outside this update.
3. Reload pyRevit. Restart Revit if the previous interface persists. The designer title should show `2026.10.14.1`.
4. Start in a disposable project copy with the [Revit test checklist](RESIDENTIALTOOLS.extension/docs/REVIT_TEST_CHECKLIST.md).

## Included tools

| Panel | Commands |
| --- | --- |
| Framing | Lumber Library, Joist Builder, Hello World |
| Deck Design | Deck Designer, Deck Stairs, Deck Railings, Hello World |
| Deck Management | Deck Manager, Material List |

Deck Designer coordinates boards, one/two perimeter borders, clipped breaker borders, angled decking, native joists/solid blocking, clips, eligible Simpson hardware and freestanding two-beam/post supports. Its five tabs are Decking, Framing, Hardware, Supports, Preview & clips. Joist Builder shares the engine. Managed rebuild preserves source Floors and unrelated elements. Stairs/railings are separately managed native prototypes.

This update adds searchable joist selection, persistent blocking-follow behavior, accessible hardware lookup while unrelated fields are unfinished, labeled accessory forms, live Manager inspection and profile/material-separated board estimates with kerf/end trim. Original Lumber Library/Hello World runtime files retain their preservation hashes. Public diagnostic/documentation paths and private model names are redacted; runtime bytes match the validated live build.

## Reports and limits

- [Per-tool improvement review and documented comparisons](RESIDENTIALTOOLS.extension/docs/REVIEW_2026-10-14.md)
- [Implementation report / incomplete features](RESIDENTIALTOOLS.extension/docs/IMPLEMENTATION_REPORT.md)
- [Pennsylvania references and research decisions](RESIDENTIALTOOLS.extension/docs/RESEARCH_AND_IMPROVEMENTS.md)
- [Simpson BIM library workflow](RESIDENTIALTOOLS.extension/docs/SIMPSON_BIM_LIBRARY.md)
- [Local validation](RESIDENTIALTOOLS.extension/docs/LOCAL_VALIDATION.json) and [test results](RESIDENTIALTOOLS.extension/docs/TEST_RESULTS.json)

Pennsylvania UCC/2021 IRC references are included for Montgomery/Berks/surrounding areas; actual municipality/site criteria remain necessary. Automatic capacity/span sizing, house connections, footings, complex stairs, pitched framing and complete fabrication/fastener takeoffs are future work. Material estimates pack compatible lengths, not optimal nesting or ripped-width recovery. No vendor RFA/RVT is redistributed. The prior recorded FRAMETOOLS/DECKTOOLS source paths are currently unavailable; complete legacy migration is not claimed.

## Development

Source is in `RESIDENTIALTOOLS.extension/`. With Python 3 and Pillow: `python -B -m unittest discover -s tests` and `python -B tools/validate_extension.py`, run from that folder. Optional installed Revit XML can be supplied with `--api-xml`. The runtime uses IronPython-compatible code; local validation does not launch Revit.
