# Simpson BIM library workflow

In Deck Designer or Joist Builder, open **3. Hardware > Get Simpson hardware from BIM library**. For size-matched single/double hangers, select a loaded joist and verify its actual section and exposure first. Explicit hurricane/corner choices and Drawing Finder can be browsed without a joist. Unfinished fields unrelated to the library remain editable; Build/Preview still validate all required settings. Ordinary families without LL/FT treatment metadata use explicit custom mode; section parameters do not certify material or treatment.

| Connection / actual section | Indexed candidate |
| --- | --- |
| Single 2x4: 1.5 x 3.5 in | LUS24 |
| Single 2x6: 1.5 x 5.5 in | LUS26 |
| Single 2x8: 1.5 x 7.25 in | LUS28 |
| Single 2x10: 1.5 x 9.25 in | LUS210 |
| Two touching 2x10s: total 3 x 9.25 in | LUS210-2 |
| Explicit hurricane tie choice | H2.5A |
| Explicit corner bracket choice | A35 |

Seven 3D native RFA URLs were read from [Simpson's official Drawing Finder](https://www.strongtie.com/search?v=%3Arelevance%3AdrawingFileType%3ARevit%3AdrawingDimension%3A3D&tab=drawing) on October 12, 2026. They use its linked `ssttoolbox.widen.net` host. This is a small candidate index, not a synchronized catalog or a capacity/coating/fastener specification. Exterior treatment does not silently change a candidate into ZMAX/stainless hardware. Unknown families require explicit solid-sawn verification; known engineered/steel types do not receive a guessed LUS match. Unsupported sections open Drawing Finder.

On October 14 all seven direct links returned HTTP 200 to HEAD requests without query parameters. The index now uses those simpler public URLs. This checked link availability only; no RFAs were downloaded or tested in Revit by that check. Existing old-URL cache sidecars may prompt a fresh download after terms acknowledgement.

## Download and native placement

The user acknowledges [Simpson terms](https://www.strongtie.com/resources/software/technical-notes/webapp-agreement) before downloading. The tool supports cached reuse, timeouts, a 40 MB size limit, partial-file cleanup and native container-header/hash checks. Only Revit can confirm that an RFA is valid.

Cache: `%LOCALAPPDATA%\RESIDENTIALTOOLS\BIM\Simpson\R2025` or `R2027`. JSON sidecars record URL, checksum, timestamp and terms link. Loaded same-name families are reused without overwrite; provenance identifies the source cache, not proof that the existing family is identical. Changing joist type/section requires refreshing selected hanger provenance.

Non-adaptive Generic Model or loadable Structural Connections types are eligible if point-based or WorkPlaneBased with host behavior 0. The native category is preserved. Face/wall/floor-hosted, adaptive and curve-based types need another workflow. Loading occurs before deck rebuilding; load-only is available and a loaded family can remain even if the later layout action stops.

Work-plane placement uses an upward managed ReferencePlane for each distinct insertion elevation and the [reference/location/direction API overload](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/be4b822c-829a-7e7b-8c03-a3a324bfb75b.htm). Planes share elevations, are owned/registered, and are excluded from installed hardware counts. They participate in guarded rebuild/removal.

## Connection rules

- Hanger origins default to **Joist bottom**. Use the vertical adjustment or **Framing top** if the actual family origin differs. Opposite ends reverse 180 degrees; inspect seat/orientation in Revit.
- Touching two-ply supports with identical endpoints get one selected double hanger at each assembly end. Spaced supports use singles. A missing double selection warns; single types are not substituted. More than two touching plies needs another workflow.
- Selected corner brackets suppress corner-end hangers; interior hangers remain. Return corners and skewed edges need individual inspection.
- Hurricane ties occur only at actual modeled joist/beam crossings, with origins at beam top. No modeled beams means no hurricane ties; ties are not placed at rim ends.

The user's Revit 2027 screenshot shows native LUS210 instances. Cached metadata/log inspection confirms Structural Connections, WorkPlaneBased, host behavior 0, work-plane flag 1 and non-adaptive. This is evidence of loading/instantiation, not verified seating or structural suitability. Revised bottom origins, double hangers, ties and corner rules have not been host-tested by the agent. Other downloads are not asserted successful.

Use `REVIT_TEST_CHECKLIST.md`: load-only/manual placement first, inspect near/far fit, test LUS210-2 touching pairs, build twice, turn hardware off, remove the owned layout and test unrelated reference-plane dependencies for rollback. No manufacturer RFAs are redistributed in the ZIP.
