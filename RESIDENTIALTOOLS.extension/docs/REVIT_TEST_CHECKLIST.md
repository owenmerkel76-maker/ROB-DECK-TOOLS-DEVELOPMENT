# Revit 2025 / 2027 test checklist

Run separately in both supported versions, in a disposable project copy. Local tests have not executed these Revit interactions. Reload pyRevit after installing; restart Revit if old modules remain cached. Ensure only the intended RESIDENTIALTOOLS copy is enabled.

## 1. Ribbon and the reported Floor failure

- Confirm Framing: Lumber Library, Joist Builder, Hello World; Deck Design: Deck Designer, Deck Stairs, Deck Railings, Hello World; Deck Management: Deck Manager, Material List.
- Start Deck Designer and choose **Use a horizontal Floor outline**. Select the flat stepped Floor from the screenshot. The old four-edge rectangle error should be gone.
- Leave beam supports, hardware and borders off initially. Confirm the preview follows the six-edge outline and does not fill the recessed notch or house area. Build with a verified loaded joist type. Verify native member solids stop at the boundary. The source Floor must remain unchanged.
- Re-pick after changing the Floor sketch. Curves/openings must stop with a clear error. Separate beam support zones may require separate layouts rather than one automatic two-beam layout.

## 2. Baseline, framing and rebuild safety

- Three-point 12 x 10 ft rectangle; A-axis boards; width 5.5 in; thickness .94 in; gaps .1875/.125 in; stock 20 ft; joists 1.5 x 9.25 in at 16 in O.C.; rims on; all three components enabled; no picture frame, blocking, supports or hardware. Expected: 22 field boards, 12 framing pieces, 210 modeled hidden clips.
- Select known treated/untreated Lumber Library types with matching exposure. An unidentified loaded family should use explicit custom mode and require verified section/material. Test generated RFAs and length flex separately; generating a file alone does not prove it works.
- Enable solid blocking, including a different loaded blocking type. Check dimensions, top alignment, bays, counts and short-span centered rows. Test 12/16/24 in O.C.
- Build twice: counts remain stable without duplicate registered geometry. Turn clips or borders off and rebuild: previous owned components disappear.
- Place unrelated manual models and an unregistered copy of a generated board: they must survive rebuilding/removal. Manually missing pieces should be reported/regenerated. Pinned/grouped pieces should stop replacement.
- Attach an unrelated dependency to an owned reference plane: unsafe cascade deletion must abort and retain the previous layout. Test cancellation and intentional family-flex failures for rollback.

## 3. Borders, lengths, angles and breakers

- Test one/two picture-frame courses, miter gaps, touching double border supports and their corner returns.
- Test 30 x 12 and 42 x 12 ft decks: every perimeter/field piece is at most selected stock. Check paired joists and cross-block backing at border seams; verify stagger preference.
- Enable **cross-deck breaker-board borders** at zero angle on a long rectangle. Confirm square-edge cross-deck boards separate the field, each has a center joist plus two touching edge-support pairs, and perimeter seams do not overlap this support band. Check excluded border fastening requirements manually.
- Test 15/30/45-degree decking with fixed framing, then optional framing rotation. Check stock lengths, actual paired-joist seam crossings, board cuts and unique clip placements in plan/3D. Verify manufacturer diagonal spacing separately.
- Test the stepped Floor with two courses and angled decking; check concave returns and seam backing. Test a trapezoid. Skewed backing remains a reviewed detail, not a completed automatic fastening design.

## 4. Hardware and two-beam supports

- Start with cached official LUS210; inspect its origin manually. The loader should offer its eligible native WorkPlaneBased Structural Connections type. Default hanger origin is joist bottom; adjust offset or origin setting to suit the actual family. Check near/far end orientation and seat fit in section/3D.
- Get **LUS210-2** for touching two-ply 2x10s (actual assembly width 3 in). Check one double hanger per assembly end and no substituted singles. Spaced seam supports remain separate singles. Missing double selection must warn.
- Select a corner bracket: corner-end hangers should disappear while interior hangers remain. A plain baseline with corner brackets has 16 single hangers plus four corner brackets. Check all orientations; stepped return vertices require review.
- With beams off, hurricane ties must be zero. Enable two freestanding beams and choose compatible framing/column types. Default rectangle: beam centers 1 and 9 ft along joist direction, beam tops at joist underside, six posts total, post tops at beam underside. Check each post's actual section/height and constraints.
- Select hurricane ties: default rectangle has 20 crossing ties. They must occur at beams, not rim ends. Additional seam/border joists increase crossings. Check family origins at beam top; plane count depends on distinct hardware elevations.
- Build twice; select Off and rebuild; remove using Deck Manager. Confirm stable counts and removal of owned hardware/reference planes only.
- Change joist family/size: cached selected-hanger provenance must be refreshed. Test unsupported hosted families and failed/offline downloads; review logs. Verify coating and fasteners outside the model lookup.

## 5. Roof projection, PA reference and accessories

- Optional roof test: select a single planar sloped Floor through **Level roof-deck outline from a sloped Floor**. Result must be level above its peak with specified framing clearance. Automatic freestanding supports are blocked in this mode. Pitched decking and actual Roof elements/multi-facet surfaces are not implemented.
- Enter the actual Montgomery/Berks-area township/borough. Open PA reference review; compare reported centerline spans/cantilevers/post spacing with dimensions. These are not allowable-span calculations. Confirm current permit edition, local site loads, species/grade, treatment/incising and applicable table footnotes before selecting sizes. House connections remain deferred.
- Deck Stairs: choose native type and levels; enter rise-related dimensions, pick deck-edge top center and ground direction in plan. Confirm top meets deck, actual risers/treads/width, type, supports, rails and scope commit. Verify landing/headroom/handrail clearance separately. Repeat/cancel and confirm no duplicate stair.
- Deck Railings: select native type/edges and a stair/gate opening. Check path, deck-top offset, rail height/balusters and clear access. Repeat to replace only that accessory. Change the deck elevation, rebuild, then rerun accessories; they do not automatically follow primary rebuilds.

## 6. Material List and removal

- Export one/all managed decks. Compare installed counts, live lengths and primary material volumes with native schedules; double hangers are already included in total hangers.
- Missing owned pieces and stale accessories must be flagged. Exclude manual/unregistered copies and reference planes. Confirm accessory assemblies do not double count their owned dependent parts.
- Review stock/kerf/extra allowance estimates against a manual cut list. They are length-only estimates; entered end trim but no ripped-width recovery or unmodeled fasteners are included. Use native stair/railing schedules for their subcomponent materials.
- Deck Manager selection should select modeled roots; removal should safely remove primary deck/accessories and their registries, leaving source Floor and unrelated models intact.

Report failures with the tool name, Revit version, selected family/type, settings, screenshot and the full `%LOCALAPPDATA%\RESIDENTIALTOOLS\Reports\...\run.log`. JSON reports contain settings, planned pieces, ownership and hardware provenance.

Regression check: with a stepped Floor and breaker-board option enabled, **Get Simpson hardware** must open the library and **Re-pick footprint** must remain usable. Enter a valid breaker center and confirm Build/Preview accept the stepped Floor. Invalid backing width or overlapping centers must still stop the build. Confirm canceled/finished library actions return to the editable settings window without losing values.


### First test for the user's stepped Floor

1. Reload pyRevit, select the stepped Floor and keep one/two perimeter courses as desired. Enable **Add cross-deck breaker boards with coordinated backing**.
2. Enter a single **Breaker center** in feet along the selected framing A/B axis, for example `10` for a roughly 20-foot layout. Verify the plan preview before building; offsets start at the framing footprint origin, not a picked point on the house. Move the center if needed. Blank means automatic stock divisions and may produce no breaker on a short deck.
3. Confirm the orange breaker ends follow the stepped outline/inner perimeter border and no board fills the notch. Confirm five backing lines around the band (center plus two touching pairs), their finite lengths, double hangers and field board end seating. Keep supports off for the initial test, then test two beams/ties separately.
4. Test 15/30/45-degree field boards with fixed framing: breaker orientation stays with its joists and cut ends meet it at an angle. Test rotated framing separately. Check return corners, gaps, seat geometry and manufacturer fastening in Revit.
5. Test `10,20` on a suitably long layout, automatic divisions beyond stock, and a breaker longer than stock. Continuous framing must carry the breaker butt seam; inspect any generated cross-blocks. Too-close/outside centers must error before model edits.
6. Build twice and inspect stable counts; disable the breaker and rebuild to remove its owned pieces/backing. Verify hidden clips avoid its square-edge band. Material List must report a separate Breaker board group while including its lengths in the board-order estimate.

103 local tests pass. The agent has not performed these Revit host tests.

## October 14 interface and quantity regressions

1. Confirm the title includes `2026.10.14.1` and five numbered tabs appear. Check all controls/footer buttons at your normal Windows display scaling. Confirm ordinary deck mode hides roof clearance; Floor extents are locked. Use Help and searchable loaded joist picker.
2. Enter unfinished text in an unrelated numeric field, then open Hardware > Get Simpson hardware. Drawing Finder/explicit ties/brackets should remain accessible without a joist; matched hangers should require a valid joist section. Cancel/finish and verify your draft and Hardware tab remain. Build/Preview must still reject invalid numeric inputs. Restore valid values before building.
3. With blocking following joist, build/save/reopen, then change 2x10 to 2x12: block dimensions and selected framing type must follow. Uncheck follow, choose a separate blocking type, rerun and verify it stays independent. Restore follow and check actual member geometry.
4. Uncheck Generate joists/supports: hardware selections clear, supports and clips switch off. Re-enable components intentionally and verify preview counts before rebuild.
5. Stairs: verify labeled fields and Check inputs, cancel invalid values without model changes, then repeat to confirm saved type/levels/dimensions return. Railings: verify selected edge lengths/coordinates, opening controls and restored choices. Do not infer complete code compliance from the input summary.
6. Material List: confirm grooved field stock and square-edge border/breaker stock order separately. Use two modeled materials and verify separate groups. Inspect JSON cut plans. Test zero end trim with a full stock-length cut, then positive trim: affected order totals must be withheld with a warning while installed length stays reported. Manually rotate a board: stock estimate must flag/exclude it; rebuild before final takeoff.
7. Delete one registered board manually, then inspect Deck Manager: saved build totals remain identified as saved; current pieces and missing count must reflect the model. Rebuild and re-inspect. Separately changed primary deck generation must flag old stair/railing accessories.

The offscreen WPF sample review covers appearance with events removed. These steps verify actual pyRevit events and native Revit behavior.
