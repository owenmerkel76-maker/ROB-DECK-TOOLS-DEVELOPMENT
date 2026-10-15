# -*- coding: utf-8 -*-
"""Schematic clip geometry reused from inspected DECKTOOLS clip_family.py.

3/16 inch gap spacer; all other dimensions approximate, not CAMO product CAD.
Origin is gap center at board underside; X follows board, Y crosses gap.
"""
import math

FAMILY_NAME = 'RT_GENERIC_CAMO_STYLE_SCHEMATIC_V1'


def rectangle(half_x, half_y):
    return [(-half_x, -half_y), (half_x, -half_y),
            (half_x, half_y), (-half_x, half_y)]


def octagon(radius):
    return [(radius * math.cos(i * math.pi / 4.0),
             radius * math.sin(i * math.pi / 4.0)) for i in range(8)]


def parts():
    """(outline XY inches, z inches, height inches, material key)."""
    return [
        (rectangle(.34, .09375), .35, .205, 'nylon'),
        (rectangle(.27, .36), .425, .037, 'steel'),
        (octagon(.061), -1.20, 1.75, 'steel'),
        (octagon(.10), .55, .05, 'steel'),
        ([(-.31, -.18), (-.23, -.18), (-.23, -.12), (-.31, -.12)], .13, .26, 'nylon'),
        ([(-.31, .12), (-.23, .12), (-.23, .18), (-.31, .18)], .13, .26, 'nylon'),
    ]
