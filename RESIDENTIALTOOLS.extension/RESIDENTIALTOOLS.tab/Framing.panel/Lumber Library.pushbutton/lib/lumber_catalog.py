# -*- coding: utf-8 -*-
"""Revit-independent section data. Dimensions are inches, not nominal sizes."""

SUPPORTED_CATEGORIES = (
    'untreated_dimensional', 'pressure_treated', 'LVL', 'LSL', 'PSL',
    'wood_i_joist', 'cold_formed_steel_c_joist',
)

# Only these three sections are implemented. Engineered/steel catalogs require
# manufacturer dimensions, materials and section details before implementation.
PROTOTYPES = (
    dict(key='UT_2x10', category='untreated_dimensional',
         family='LL_UT_2x10', type_name='UT 2x10 - Actual 1.5 x 9.25',
         profile='rectangle', width=1.5, depth=9.25,
         material_id='LL_WOOD_UNTREATED_UNSPECIFIED',
         materials=('LL_WOOD_UNTREATED_UNSPECIFIED',), color=(191, 151, 100)),
    dict(key='PT_2x10', category='pressure_treated',
         family='LL_PT_2x10', type_name='PT 2x10 - Actual 1.5 x 9.25',
         profile='rectangle', width=1.5, depth=9.25,
         material_id='LL_WOOD_PRESSURE_TREATED_UNSPECIFIED',
         materials=('LL_WOOD_PRESSURE_TREATED_UNSPECIFIED',), color=(129, 150, 91)),
    dict(key='IJOIST_GENERIC_11_875', category='wood_i_joist',
         family='LL_IJOIST_GENERIC_11_875',
         type_name='Generic I 11.875 - Flange 2.5 x 1.5 - Web 0.375',
         profile='i_section', width=2.5, depth=11.875,
         flange_thickness=1.5, web_thickness=0.375,
         material_id='LL_IJOIST_GENERIC_UNRATED',
         materials=('LL_IJOIST_FLANGE_UNSPECIFIED', 'LL_IJOIST_WEB_UNSPECIFIED'),
         color=(181, 135, 83)),
)


def rectangles(section):
    """Return non-overlapping (y0, z0, y1, z1, material_index) rectangles."""
    width, depth = section['width'], section['depth']
    if width <= 0 or depth <= 0:
        raise ValueError('Section dimensions must be positive.')
    if section['profile'] == 'rectangle':
        return [(-width / 2.0, -depth / 2.0, width / 2.0, depth / 2.0, 0)]
    if section['profile'] != 'i_section':
        raise ValueError('Profile not implemented: ' + section['profile'])
    flange, web = section['flange_thickness'], section['web_thickness']
    if not (0 < 2 * flange < depth and 0 < web < width):
        raise ValueError('Invalid flange/web dimensions.')
    return [
        (-width / 2.0, -depth / 2.0, width / 2.0, -depth / 2.0 + flange, 0),
        (-width / 2.0, depth / 2.0 - flange, width / 2.0, depth / 2.0, 0),
        (-web / 2.0, -depth / 2.0 + flange, web / 2.0, depth / 2.0 - flange, 1),
    ]


def area_inches(section):
    return sum((r[2] - r[0]) * (r[3] - r[1]) for r in rectangles(section))
