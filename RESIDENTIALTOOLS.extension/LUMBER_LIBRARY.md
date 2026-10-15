# Lumber Library prototype

The Framing panel now has a separate **Lumber Library** button. The Framing and
Decking Hello World buttons are preserved. No other extension is modified.

## Current status

**Not tested in Revit. No RFAs have been generated or verified in this workspace.**
Local Python/YAML checks cannot prove family constraints or beam placement work.
The button implements generation and automated Revit checks for these three sections:

| Family | Type / actual section (inches) | Materials |
| --- | --- | --- |
| LL_UT_2x10 | Untreated 2x10: 1.5 x 9.25 | LL_WOOD_UNTREATED_UNSPECIFIED |
| LL_PT_2x10 | Pressure-treated 2x10: 1.5 x 9.25 | LL_WOOD_PRESSURE_TREATED_UNSPECIFIED |
| LL_IJOIST_GENERIC_11_875 | Depth 11.875; flanges 2.5 wide x 1.5 thick; web 0.375 thick | Separate LL_IJOIST_FLANGE_UNSPECIFIED and LL_IJOIST_WEB_UNSPECIFIED |

The I-joist is an explicitly generic test profile, not a manufacturer product.
Its type material identifier is `LL_IJOIST_GENERIC_UNRATED`. All identifiers are
type parameters; actual Revit materials are associated to the solid extrusions.
Species, grade, treatment chemistry, physical assets and structural capacities
are unspecified. Cross sections are fixed per type/RFA. Formula-locked
`LL_AsGenerated_*` parameters report actual dimensions; width/depth do not flex.
Member length is driven by the template's native beam end planes and locked
solid end faces. The I section uses three touching, non-overlapping solids so
flanges and web have separate material identities.

## Run the prototype in Revit

1. Reload pyRevit and open a disposable project in Revit **2025 or 2027**.
2. Click Framing > Lumber Library.
3. Select the running version's **Structural Framing - Beams and Braces.rft**.
   Generic Model and Structural Column templates are rejected. The current
   prototype requires English end-plane names and the native instance Length
   parameter; unsupported skeletons fail with details in the log.
4. Select a destination folder. Each run creates a new
   `LumberLibrary_Revit<version>_<timestamp>` directory, with no overwrite.
5. Review `report.json` and `run.log`. Each family is generated in a temporary
   family document, then flexed **8 -> 14 -> 8 feet**. It is loaded into a new
   temporary project. Two instances (0 and 30 degree horizontal orientations)
   are each resized **8 -> 14 -> 8 feet**, with beam joins disabled. Tests check
   solid length, width, depth, volume, and actual face material identities.
   Transactions log warnings and roll back on Revit errors. Temporary documents
   are closed without saving; the active project receives no test instances.
6. An RFA is saved only after its generation and automated checks pass. A failure
   in one section is logged and the other two sections are still attempted.
   If save/close fails, consult the report before using any partial output.
7. Load each saved RFA into a fresh test project and verify **the saved file**:
   type name, materials, plan/section orientation, solid end coincidence,
   and 8/14-foot placement and resizing. Also check sloped members, rotation,
   joins/cutbacks and project scheduling manually; these are not automated yet.

Generate and test independently in each Revit version. A 2027-saved RFA cannot
be opened in Revit 2025. Automated checks run against the generated in-memory
family before saving; reopening saved files and visual QA remain required.

## Source inspection and scope

The previous generator **was found and inspected**, read-only, at:

`previous local FRAMETOOLS extension (private path omitted)`

Inspected `Create Joist RFAs.pushbutton/script.py`, `lib/joist_profiles.py` and
`README_FIRST.md`. The source itself describes an untested pilot. The new
generator adapts its end-plane discovery, sample-form removal, transverse
extrusion and end-alignment approach. This is a limited adaptation, **not a
complete FRAMETOOLS migration**. Original files are unchanged. The new catalog,
three-solid I section, distinct material identifiers, error reporting and
automated Revit tests were added here. Element IDs use 64-bit `ElementId.Value`
and native ElementId objects, without deprecated IntegerValue conversions.

The category registry includes untreated dimensional, pressure-treated, LVL,
LSL, PSL, wood I-joists and cold-formed steel C-joists. **Only the three prototype
sections are generated currently.** Future LVL/LSL/PSL sections need verified
product dimensions and material identities. C-joists need a dedicated lipped
channel profile with verified design thickness, corner radii and optional
punchouts. The old source's unlipped simplified C profile is not carried forward
as a valid steel joist. Manufacturer catalogs and editable cross-section
geometry remain future work.

## Local validation

- Five catalog/ID unit tests passed (actual sizes, separate identities, I-section
  area and non-overlap, invalid section rejection, and IDs larger than 32 bits).
- All five runtime Python files passed Python 2 grammar and Python 3 compile
  checks. These are static checks, not execution in an IronPython Revit host.
- All three bundle YAML files parsed successfully with duplicate-key rejection
  and metadata/version checks. The new button uses a clean IronPython engine.
- All three icons passed 32 x 32 PNG verification.
- The six original Hello World files matched their pre-edit SHA-256 hashes.
- No nested `.extension` directories were created. Local validation errors: 0.

Re-run pure tests using Python 3: `python -B -m unittest discover -s tests -v`.
No generated RFA or Revit test result is included with this prototype.

API references: [Autodesk family creation labs](https://blog.autodesk.io/revit-family-creation-api-labs/),
[family parameters](https://help.autodesk.com/cloudhelp/2024/PTB/Revit-API/files/Revit_API_Developers_Guide/Revit_Geometric_Elements/Family_Documents/Revit_API_Revit_API_Developers_Guide_Revit_Geometric_Elements_Family_Documents_Managing_family_types_and_parameters_html.html),
[64-bit Element IDs](https://blog.autodesk.io/64-bit-element-ids-maybe/).
The installed Revit 2027 `RevitAPI.xml` was also inspected for API members.

Public-package note: the historical source path above is redacted. The original local document and all Lumber Library runtime files remain preserved. The recorded legacy sources are currently unavailable locally.
