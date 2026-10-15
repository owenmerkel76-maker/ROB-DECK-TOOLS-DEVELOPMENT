# RESIDENTIALTOOLS implementation report

Updated October 14, 2026. Version **2026.10.14.1**, field-test build. Source: the local `RESIDENTIALTOOLS.extension` working copy. The release is also synchronized to the authorized Desktop RESIDENTIALTOOLS test copy during delivery.

The agent has not executed this build inside Revit. User screenshots show native LUS210 instances in Revit 2027; seating, revised origins and all new workflows still require host tests in both supported versions. Generated Lumber Library RFAs are not certified by local checks.

## Implemented features

| Area | Current behavior |
| --- | --- |
| Shared designer | Decking, Framing, Hardware, Supports, Preview & clips tabs; saved settings, editable drafts, plan preview, friendly counts, relevant dependent controls and explicit rebuild. Joist Builder uses the same engine. |
| Footprints | Three-point rectangles or one planar straight-edge Floor loop, including concave stepped returns. Reads actual boundary and preserves the source Floor. Floor extents are locked until re-picked. |
| Decking | Individual Generic Model DirectShapes, schematic grooves, adjustable default 3/16-inch gaps, edge rips, 12/16/20-foot stock, staggered supported seams and independently adjustable angle. |
| Borders and breakers | One/two mitered perimeter courses and stock-limited pieces. Clipped cross-deck breaker bands with automatic/manual centers, central joist and touching paired edge supports; long pieces split to stock. Fixed framing keeps breakers along joists while diagonal fields meet them. Clips avoid square-edge bands. |
| Joists/blocking | Loaded native Structural Framing, actual section checks, 12/16/24-inch O.C., rims and solid blocking. Explicit persistent “blocking follows joist,” or separately selected blocking family/section. Searchable loaded joist types. |
| Supports | Optional freestanding two-drop-beam layout, native two-level Structural Column posts, adjustable sections/setbacks/height/end offsets/maximum spacing. |
| Hardware | Single hangers, one double hanger per touching two-ply assembly end, selected corner brackets suppressing corner-end hangers, ties only at modeled beam crossings. Eligible native work-plane families use owned reference planes. |
| Simpson library | Seven indexed official RFA candidates: LUS24/26/28/210, LUS210-2, H2.5A, A35. Terms acknowledgement, cache hashes, type selection and provenance. Hardware browsing is independent of unfinished unrelated fields. |
| Deck Stairs | One native straight-run assembly; labeled loaded-type/level/dimension form, input summary, previous settings restored and picked plan direction. Separately managed replacement. |
| Deck Railings | Native perimeter paths; labeled type/edge/opening form, edge lengths/local endpoints, previous selections restored and connected-path preview summary. Separately managed replacement. |
| Deck Manager | Saved/live count distinction, current registered pieces/work planes/accessories, missing/stale warnings, selection, report export and guarded removal. |
| Material List | Current owned installed counts, lengths and primary volumes; separate compatible profile/material/section stock groups, kerf/end trim/extra allowance, JSON cut plans and incomplete-order warnings. |
| Pennsylvania | Official UCC/2021 IRC links, entered municipality, centerline support/span/cantilever/post-spacing review, basic PA stair-input checks. No automatic allowable-span sizing. |
| Roof option | One sloped planar Floor may provide a projected outline for a LEVEL deck above its peak with entered clearance. Automatic supports are blocked in this mode. |

Boards can be individually moved/marked/counted/deleted; dimensions change through settings/rebuild, not per-board RFA parameters. Native framing/beam/post actual geometry is checked during building; incompatible geometry aborts and rolls back.

## Ownership and updates

DataStorage records plus element Extensible Storage stamps identify owner/layout/generation. Rebuild checks new geometry before deleting the selected registry's old elements. Unsafe dependent deletion, pinned/grouped elements or changed ownership stops replacement. Missing registered elements are reported. Unregistered copied/manual elements, other layouts, source Floors and family definitions remain preserved.

Generated pieces edited manually within a registry are replaced on rebuild. A changed source Floor must be re-picked. Rebuilding a deck preserves its separately registered stairs/railings; rerun those commands after parent footprint/elevation changes. Material List and Manager warn about stale accessory generations. There is no model-change monitoring.

Hidden clip counts cover eligible modeled grooved field-board connections. Square-edge border/breaker face fasteners, starter clips, nails and screws are excluded. Double hangers are included in total hangers. Owned hardware reference planes are excluded from piece counts.

## Incomplete features

- Verified allowable-span/member sizing needs site loads, species/grade, wet-service/incising, beam ply construction and applicable table footnotes. Measurements are centerline distances, not capacity approval. House/ledger connections remain deferred by request.
- No footings, roof stanchions, post caps/bases, lateral bracing or generated built-up beam plies. One selected family instance represents each beam.
- No Floor holes/curves/multiple loops, multi-facet roofs, pitched decking/framing or automatic multi-zone support design. Some concave footprints require separate support layouts. Skewed and return-corner backing/details require review.
- Stairs are one native straight run, not complete wood-stringer fabrication; complex stairs/landings and full stair/guard design remain future work. Native types control component details. Railing opening is manually selected, not inferred from the stair.
- Lumber Library remains the preserved untreated 2x10, treated 2x10 and I-joist prototype. Full LVL/LSL/PSL/C-joist catalogs, specialized rims and X-bridging remain future work.
- Hardware fit/origin/orientation/coating/capacity/fasteners need verification. Adaptive and face/wall/floor-hosted hardware is unsupported; no vendor RFAs are bundled.
- Stock estimates pack lengths within compatible groups; no optimized nesting/ripped-width recovery. Rotated/width-changed boards are excluded from stock estimates with warnings. Native stair/railing subcomponent materials require schedules. Unmodeled items are not inferred.
- Rebuild replaces ElementIds; annotations may need reassociation. Worksharing/design options are not host-tested.

## Inspection, files and checks

All nine commands/shared backends were reviewed. Historical source paths/hashes remain in `SOURCE_INVENTORY.json`; recorded FRAMETOOLS/DECKTOOLS files are currently unavailable. Earlier selective geometry reuse is documented, but no new migration or complete legacy parity is claimed. No RVT was opened/mined for families.

Both Hello Worlds and Lumber Library retain 13 original-file hashes. No ROBMEPTOOLS or other extension was edited; no nested `.extension` folder was created.

New in this sweep: `lib/rt_presentation.py`, `lib/rt_forms.py`, `resources/ToolOptions.xaml`, `release.json`, four tab/panel `bundle.yaml` manifests, `tests/test_review_quality.py`, this release review and `docs/UI_RENDER_REVIEW.json`. Existing shared modules, designer XAML and documentation were edited in place. The delivery manifest lists every packaged file and SHA-256.

**103 local tests pass; zero validation errors.** Checks cover 40 Python files, 29 runtime Python-2 grammar/static files, 13 YAML files, nine button bundles/icons, two XAML resources, 45 installed Revit 2027 XML API members and the 13 preserved hashes. Eight sample WPF screens were rendered/reviewed offscreen; event binding and Revit execution were not tested by that rendering.

See `REVIEW_2026-10-14.md` for per-tool changes/comparisons and `REVIT_TEST_CHECKLIST.md` for host verification. Publishing a ZIP makes the field-test build downloadable; it does not establish native family or structural correctness.

Public packaging redacts absolute diagnostic paths/private model names and the Lumber Library document's historical path. Runtime files are byte-for-byte identical to the validated live/installed build. Public preservation metadata reflects the redacted document; original live-source hashes remain preserved privately.
