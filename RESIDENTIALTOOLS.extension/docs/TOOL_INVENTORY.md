# Tool inventory and consolidation

Reviewed October 14, 2026 (version 2026.10.14.1). This release has nine complete pushbutton bundles. Every current command and its shared backend was included in the review; legacy source paths recorded earlier are currently unavailable. This is not a claim that every legacy command has been migrated.

| Panel | Button | Role |
| --- | --- | --- |
| Framing | Lumber Library | Preserved three-family generator prototype; family generation/flex requires Revit tests. |
| Framing | Joist Builder | Framing-focused entry into the shared designer; native joists, rims, solid blocking, supports and selected hardware. |
| Framing | Hello World | Preserved ribbon smoke test, last in panel. |
| Deck Design | Deck Designer | Coordinated boards, framing, borders, clips, hardware, supports, settings, plan preview and rebuild. |
| Deck Design | Deck Stairs | Native straight stair prototype; separately owned accessory replacement. |
| Deck Design | Deck Railings | Native perimeter railings with selected edges/opening; separately owned replacement. |
| Deck Design | Hello World | Preserved Decking test button, last in panel. |
| Deck Management | Deck Manager | Inspect saved/live counts and missing/stale warnings, select, open reports or safely remove registered layout and accessories. |
| Deck Management | Material List | Owned installed quantities, lengths, primary material volumes and profile/material/section-separated board-stock estimates with kerf, end trim and extra allowance. |

Deck Designer combines former Deck Builder, Deck Clip Builder and Residential Settings launch points into one shared workflow. Joist Builder is retained as a useful framing entry. Deck Manager combines inspect/select/remove operations; separate accessory commands keep native stair/railing edits independent of primary rebuilding. This avoids deleting an accessory while changing decking.

## Legacy mapping

`SOURCE_INVENTORY.json` preserves historical read-only paths/hashes. The recorded FRAMETOOLS/DECKTOOLS files are absent now; the validator reports that explicitly. Earlier selective board-profile/schematic clip reuse remains in the project. No new source migration was invented.

| Previously recorded capability | Current handling / remaining gap |
| --- | --- |
| FRAMETOOLS joist generation / layout | Lumber Library prototype preserved; coordinated native framing implemented. Complete old generator parity not claimed. |
| DECKTOOLS auto layout / settings / update | Unified Deck Designer and registry-checked rebuild. Old unregistered layouts are not automatically adopted. |
| Standalone Trex Board Builder | Not migrated; integrated boards remain countable DirectShapes. |
| Deck Materials color/texture creation | Not migrated as a separate editor; Material List reports modeled quantities rather than creating materials. |
| Inspect / select / remove / reports | Deck Manager consolidates these for the current registry. |
| Manufacturer shortcut | Small official Simpson candidate index inside shared settings; not a synchronized full catalog. |
| CAMO-style schematic clips | Existing adapted geometry preserved, with countable solids or a generated generic RFA workflow. Not certified manufacturer CAD. |
| Source reload/update utilities | Use pyRevit reload; no tool changes unrelated extensions. |

The previously located RVT files were not opened or mined for embedded families. The user supplied evidence of loaded Simpson LUS210 instances; the new positioning/double hardware logic still requires checking in the running model.

No ROBMEPTOOLS or other extension is edited. Both Hello World tests and Lumber Library retain their original hashes. See `IMPLEMENTATION_REPORT.md` for implemented/deferred features and `REVIT_TEST_CHECKLIST.md` for exact host tests.

Ribbon order is explicit in four layout manifests. Shared settings use five numbered tabs: Decking, Framing, Hardware, Supports, Preview & clips. Stairs, railings and materials have labeled forms; stairs/railings restore prior accessory choices. See `REVIEW_2026-10-14.md` for each tool's changes and host-test boundary.
