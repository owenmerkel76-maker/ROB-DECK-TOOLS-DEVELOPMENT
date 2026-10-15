# -*- coding: utf-8 -*-
"""Small verified US Drawing Finder index; dimensions narrow model lookup only.

3D RFA links observed in Simpson's US Drawing Finder on 2026-10-12.
No files are bundled and this is not a structural connector design catalog.
"""
import math
try:
    from urllib.parse import urlencode, urlparse
except ImportError:
    from urllib import urlencode
    from urlparse import urlparse

LICENSE_URL = 'https://www.strongtie.com/resources/software/technical-notes/webapp-agreement'
FINDER_URL = 'https://www.strongtie.com/search'
ROLE_KEYS = dict(hanger='hanger_symbol_uid', double_hanger='double_hanger_symbol_uid', hurricane='hurricane_symbol_uid',
                 corner='corner_strap_symbol_uid')
MODELS = (
    dict(model='LUS24', role='hanger', width_in=1.5, depth_in=3.5,
         url='https://ssttoolbox.widen.net/content/sl8oyhqmg2/original/C_LUS24_3d_Cad_MULT_Prod.rfa'),
    dict(model='LUS26', role='hanger', width_in=1.5, depth_in=5.5,
         url='https://ssttoolbox.widen.net/content/tjuvbpn7ia/original/C_LUS26_3d_Cad_MULT_Prod.rfa'),
    dict(model='LUS28', role='hanger', width_in=1.5, depth_in=7.25,
         url='https://ssttoolbox.widen.net/content/elxlevxo9b/original/C_LUS28_3d_Cad_MULT_Prod.rfa'),
    dict(model='LUS210', role='hanger', width_in=1.5, depth_in=9.25,
         url='https://ssttoolbox.widen.net/content/hqsckahllb/original/C_LUS210_3d_Cad_MULT_Prod.rfa'),
    dict(model='H2.5A', role='hurricane',
         url='https://ssttoolbox.widen.net/content/la8gcqmapy/original/C_H25A_3d_Cad_MULT_Prod.rfa'),
    dict(model='A35', role='corner',
         url='https://ssttoolbox.widen.net/content/b6wggepwee/original/C_A35_3d_Cad_MULT_Prod.rfa'),
    dict(model='LUS210-2', role='double_hanger', width_in=3.0, depth_in=9.25,
         url='https://ssttoolbox.widen.net/content/tw5vwnq6zm/original/C_LUS210-2_3d_Cad_MULT_Prod.rfa'),
)


def dimensions(width, depth):
    width, depth = float(width), float(depth)
    if (math.isnan(width) or math.isinf(width) or math.isnan(depth) or math.isinf(depth)
            or width <= 0 or depth <= 0):
        raise ValueError('Verify positive, finite joist width and depth before hardware lookup.')
    return width, depth


def candidates(role, width, depth, category, verified_solid_sawn=False):
    if role not in ('hanger', 'double_hanger'):
        # These are explicit product choices, never sized or selected by load.
        return [dict(row) for row in MODELS if row['role'] == role]
    width, depth = dimensions(width, depth)
    known_sawn = category in ('pressure_treated', 'untreated_dimensional')
    if not known_sawn and not (category == 'unknown' and verified_solid_sawn):
        return []
    return [dict(row) for row in MODELS if row['role'] == role
            and abs(row['width_in']-width) < .01 and abs(row['depth_in']-depth) < .01]


def finder_url(keyword=''):
    return FINDER_URL + '?' + urlencode(dict(
        v=':relevance:drawingFileType:Revit:drawingDimension:3D',
        tab='drawing', keywordFilter=keyword))


def filename(entry):
    url = urlparse(entry['url'])
    if url.scheme != 'https' or url.hostname != 'ssttoolbox.widen.net':
        raise ValueError('Only the verified Simpson Drawing Finder content host is supported.')
    name = url.path.rsplit('/', 1)[-1]
    if not name.lower().endswith('.rfa') or not name or '..' in name:
        raise ValueError('Expected a direct native RFA download.')
    return name


def validate_rfa_header(header):
    # Native Revit RFA files use Microsoft's compound-document container.
    # This rejects HTML/error pages; only Revit can validate the actual model.
    if header != b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        raise ValueError('Download is not a native RFA container. No family was loaded.')


def validate_selections(values, category=None):
    for role, source in values.get('simpson_sources', {}).items():
        key = ROLE_KEYS.get(role)
        if not key or values.get(key) != source.get('unique_id'):
            continue
        if role in ('hanger', 'double_hanger'):
            opposite_key = ROLE_KEYS['double_hanger' if role == 'hanger' else 'hanger']
            if values.get(opposite_key) == source.get('unique_id'):
                raise ValueError('A Simpson single/double hanger was assigned to the wrong connection picker.')
        if role in ('hanger', 'double_hanger'):
            width, depth = dimensions(values['joist_width_in'], values['joist_depth_in'])
            if role == 'double_hanger':
                width *= 2
            if (abs(width-source['width_in']) >= .01 or abs(depth-source['depth_in']) >= .01
                    or values.get('joist_symbol_uid') != source.get('joist_symbol_uid')
                    or (category is not None and category not in
                        ('unknown', 'pressure_treated', 'untreated_dimensional'))):
                raise ValueError('The joist changed after the Simpson hanger lookup. '
                                 'Use Simpson BIM library again for the selected joist.')
