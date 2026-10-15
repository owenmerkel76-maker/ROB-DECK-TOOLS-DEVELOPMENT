# -*- coding: utf-8 -*-
"""Pure-Python cross-section calculations, no Autodesk dependency.
Coordinates: (Y,Z) in INCHES; length extrusion along world X.
Revit 2025/2027 + IronPython 2.7 compatible.
This is an engineered *schematic* groove, not manufacturer shop geometry.
"""

THICKNESS_IN = 0.94
STOCK_WIDTH_IN = 5.50
MAX_STOCK_FT = 20.0
GAP_IN = 3.0 / 16.0
GROOVE_DEPTH_IN = 0.25     # ASSUMPTION - NOT TREX CAD
GROOVE_BOTTOM_IN = 0.35   # ASSUMPTION - NOT TREX CAD
GROOVE_TOP_IN = 0.55      # ASSUMPTION - NOT TREX CAD

MODES = ('both', 'left', 'right', 'square')


def make_outline(width_in, mode='both', depth_in=GROOVE_DEPTH_IN,
                 bottom_in=GROOVE_BOTTOM_IN, top_in=GROOVE_TOP_IN,
                 thickness_in=THICKNESS_IN):
    """Return ordered closed-outline vertices without duplicated last vertex.

    'both': factory grooved on both edges.
    'left': one factory groove, opposite rip flat.
    'right': one factory groove, opposite rip flat.
    'square': neither groove, both edges square.
    """
    w = float(width_in)
    if mode not in MODES:
        raise ValueError('Unknown edge mode: ' + str(mode))
    if not (0.5 <= w <= STOCK_WIDTH_IN + 1.e-8):
        raise ValueError('Width must be 0.5 to 5.5 inches.')
    # A 1/2-inch rip can retain one 1/4-inch groove. Only opposed grooves
    # require room between them; square profiles do not use groove dimensions.
    if mode != 'square' and not (0 < depth_in < (w / 2.0 if mode == 'both' else w)):
        raise ValueError('Groove depth does not fit rip width.')
    if not thickness_in > 0:
        raise ValueError('Board thickness must be positive.')
    if mode != 'square' and not (0 < bottom_in < top_in < thickness_in):
        raise ValueError('Groove vertical limits out of range.')
    lo = -w / 2.0
    hi = w / 2.0
    p = [(lo, 0.0), (hi, 0.0)]
    if mode in ('both', 'right'):
        p.extend([(hi, bottom_in), (hi - depth_in, bottom_in),
                  (hi - depth_in, top_in), (hi, top_in)])
    p.extend([(hi, thickness_in), (lo, thickness_in)])
    if mode in ('both', 'left'):
        p.extend([(lo, top_in), (lo + depth_in, top_in),
                  (lo + depth_in, bottom_in), (lo, bottom_in)])
    return p


def section_area_in2(points):
    accum = 0.0
    for i in range(len(points)):
        a = points[i]
        b = points[(i + 1) % len(points)]
        accum += a[0] * b[1] - b[0] * a[1]
    return abs(accum) / 2.0


def validate_length_ft(length_ft):
    ln = float(length_ft)
    if not (0.5 <= ln <= MAX_STOCK_FT):
        raise ValueError('Initial board length must be 0.5 to 20 ft.')
    return ln
