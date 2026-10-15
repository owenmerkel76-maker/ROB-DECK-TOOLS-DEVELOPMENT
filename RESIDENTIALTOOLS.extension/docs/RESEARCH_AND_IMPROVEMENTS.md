# Research and improvements

Review date: October 14, 2026. See `REVIEW_2026-10-14.md` for the latest per-tool decisions and eight-screen UI review. This compares documented vendor/Autodesk workflows with the local extension. Third-party tools were not installed or executed, and parity with commercial framing products is not claimed.

| Reference | Documented approach | Applied here / remaining gap |
| --- | --- | --- |
| [Revit beam systems](https://help.autodesk.com/cloudhelp/2027/ENU/Revit-StructEng/files/GUID-53449E14-6E16-4641-9023-332CC40DD59A.htm) | Boundary, beam type, layout rule and a 3D option for uneven systems. | Explicit footprint/type/spacing inputs and native individual members. Arbitrary pitched framing is deferred. |
| [ARKANCE framing interface update](https://arkance.world/au-en/resources/read/product-updates/be-smart-wood-and-metal-framing-a-faster-clearer-more-intuitive-framing-experience-in-revit) | Grouped settings, contextual guidance, numbering, family catalog paths and explicit frame updates. | One designer, inline help, plan preview, stable ownership keys and explicit rebuild. Batch frame edits, shop drawings, CNC output and automatic adoption of manually copied members are absent. |
| [ARKANCE timber BIM workflow](https://arkance.world/global/solutions/be-smart/timber-industry?showpopup=true) | Coordinated modeling, documentation and takeoffs. | Shared deck settings and a registry-based material report; no commercial fabrication/documentation parity. |
| [Trex joist/breaker-board guide](https://www.trex.com/academy/how-to-guides/all-guides/how-to-install-deck-joists/) | Separate joist/beam connections, blocking, breaker-board framing and product-specific spacing. | Hurricane ties at actual beam crossings, hanger bottom-origin controls, solid blocking, clipped breaker boards with adjustable centers and independent diagonal decking direction. Model spacing is still an input; no universal product span approval is inferred. |
| [Simpson official Drawing Finder](https://www.strongtie.com/search?v=%3Arelevance%3AdrawingFileType%3ARevit%3AdrawingDimension%3A3D&tab=drawing) | Native product RFAs. | Seven verified indexed links, user terms, cache integrity and eligible native category/placement handling. Load/fit every product before using the placed model. |

## Pennsylvania reference

The [November 2025 PA UCC rulemaking](https://www.pacodeandbulletin.gov/secure/pabulletin/data/vol55/55-45/1513.html) establishes the January 1, 2026 update. [Current 34 Pa. Code 403.21](https://www.pacodeandbulletin.gov/secure/pacode/data/034/chapter403/s403.21.html) adopts the 2021 IRC with specified exceptions/modifications, including residential stair amendments. Use current permit/local requirements; older generic deck charts are not automatically the applicable Pennsylvania design basis.

User region: Montgomery, Berks and surrounding Pennsylvania counties. The actual township/borough and site loads are still needed. They are not uniform county-wide presets in this implementation.

The UI now opens official references and the saved report measures actual modeled support-center distances. Joists, beams, post heights, bearing and cantilevers have distinct review requirements. Automated allowable-span lookup is deferred until verified species/grade, service/incising, beam ply construction, loading and table/footnote inputs are available. No IRC capacity tables were fabricated or copied from an unofficial calculator. ICC Digital Codes returned a 403 to the research fetch; its official link remains available to the user. House connections are deferred by request.

## API choices

- [Reference-based family placement](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/be4b822c-829a-7e7b-8c03-a3a324bfb75b.htm) handles eligible native work-plane hardware with an upward managed reference plane at each insertion elevation. Point placement alone cannot place all vendor RFAs.
- [Native stairs workflow](https://help.autodesk.com/cloudhelp/2024/ENU/Revit-API/files/Revit_API_Developers_Guide/Revit_Geometric_Elements/Stairs_and_Railings/Revit_API_Revit_API_Developers_Guide_Revit_Geometric_Elements_Stairs_and_Railings_Creating_and_Editing_Stairs_html.html) uses a stairs edit scope with inner transactions. Straight stairs are separate assemblies, not uneditable copied mesh geometry.
- [Native railing creation](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/34a36770-964a-60eb-5ad7-c013913dfd05.htm) uses planar connected paths and existing native types. One opening can divide perimeter paths.
- [Autodesk stair takeoff guidance](https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/Unable-to-create-material-takeoff-containing-all-stair-surfaces-in-Revit.html) distinguishes stair components. The prototype avoids pretending its accessory root volumes are a complete stair/railing material breakdown; use native schedules for those components.

Installed Revit 2027 XML confirms 45 required members. IronPython-compatible runtime syntax, 64-bit ElementId handling, source-preserving Floor reads and transaction ownership checks were retained. These checks do not execute an API call in Revit 2025 or 2027.

## Priorities for the next focused iterations

1. User-host verification of stepped outline, native framing flex, LUS210/LUS210-2 origins and support heights; preserve logs/settings for repeatable cases.
2. Verified PA span-table or engineered sizing integration with complete design inputs and explicit measurement/table assumptions.
3. Return-corner/skewed border backing, multi-zone supports, footings/post caps/bases, then deferred house connections.
4. Native stair landing/support/rail refinements and complete guard/stair review before expanding to complex stairs.
5. Materials: validate the new compatible-group/end-trim estimates in the model, then native component schedules and ripped-width recovery before verified fastener procurement quantities.

