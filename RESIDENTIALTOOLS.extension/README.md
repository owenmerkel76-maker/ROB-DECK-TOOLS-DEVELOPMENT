# RESIDENTIALTOOLS

Version **2026.10.14.1 — field-test build** for pyRevit in Revit 2025 and 2027.

Deck Designer combines individual decking boards, picture-frame/breaker borders, native joists and blocking, clips, selected hardware, freestanding beams/posts, preview and managed rebuild. It accepts three-point rectangles and simple straight-edge Floor outlines, including stepped returns. Decking and framing directions can be independent.

The settings workflow is **1. Decking → 2. Framing → 3. Hardware → 4. Supports → 5. Preview & clips**. Joist Builder opens the same engine for framing work. Deck Stairs and Deck Railings create separately managed native accessories. Deck Manager inspects/selects/removes layouts; Material List exports installed quantities and grouped board-order estimates. Lumber Library and both Hello World tests are preserved.

Install the ZIP by extracting its single `RESIDENTIALTOOLS.extension` folder into your pyRevit extension location. Replace the existing RESIDENTIALTOOLS copy, enable only one copy, and reload pyRevit. Do not place it inside another `.extension` folder. Restart Revit if cached modules still show the previous interface. Existing layouts rebuild when you explicitly request it; source Floors and unrelated model elements remain preserved.

Pennsylvania UCC/2021 IRC references are included for Montgomery/Berks/surrounding areas. Enter the actual municipality and verify site/design inputs. Automatic allowable-span/member sizing and house connections are not implemented.

- [October 14 review: every tool, improvements and remaining work](docs/REVIEW_2026-10-14.md)
- [Implementation report](docs/IMPLEMENTATION_REPORT.md)
- [Exact tests in Revit 2025 and 2027](docs/REVIT_TEST_CHECKLIST.md)
- [Tool inventory and legacy gaps](docs/TOOL_INVENTORY.md)
- [Documented comparisons and PA references](docs/RESEARCH_AND_IMPROVEMENTS.md)
- [Local packaging validation](docs/LOCAL_VALIDATION.json)
- [Offscreen WPF review evidence](docs/UI_RENDER_REVIEW.json)
- [Lumber Library instructions](LUMBER_LIBRARY.md)
- [Simpson BIM workflow](docs/SIMPSON_BIM_LIBRARY.md)

**Validation:** 103 local tests pass; packaging reports zero errors. Eight sample WPF screens were rendered and reviewed offscreen. The agent has not run this build inside Revit. Native transactions, family flex, Simpson fit/orientation, stairs and railings require the linked host tests in both versions. No vendor RFA or RVT is bundled; Lumber Library remains a three-family prototype.

Development checks: `python -B -m unittest discover -s tests` and `python -B tools/validate_extension.py --api-xml <installed RevitAPI.xml>`. Use Python 3 with Pillow for checks; runtime scripts remain IronPython-compatible. YAML validation uses a strict bundle/layout schema when PyYAML is unavailable. Checks do not launch Revit.

Public package: diagnostic paths/private model names are redacted; runtime code is unchanged. The 13 original-file hashes refer to the live source; the public Lumber Library document has its private path removed.
