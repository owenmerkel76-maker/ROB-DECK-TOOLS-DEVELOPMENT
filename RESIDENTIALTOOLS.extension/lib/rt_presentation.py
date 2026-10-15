# -*- coding: utf-8 -*-
"""Shared menu text and editable drafts, independent of Revit/WPF."""
from rt_layout import DEFAULTS
import io
import json
import os


def release_version():
    path=os.path.join(os.path.dirname(os.path.dirname(__file__)),'release.json')
    try:
        with io.open(path,'r',encoding='utf-8-sig') as stream: return json.load(stream)['version']
    except (IOError,ValueError,KeyError): return 'development'


def editable_settings(values):
    result=dict(DEFAULTS)
    result.update(values)
    # Combo selections are limited values; leave numeric text fields editable
    # so a family lookup is not blocked by unfinished, unrelated dimensions.
    for key in ('stock_ft','spacing_in','border_courses'):
        result[key]=int(float(result[key]))
    return result


def count_text(counts,breakers=0):
    c=lambda key:int(counts.get(key,0))
    return ('Boards {0} | Borders {1} (breakers {2}) | Clips {3}\n'
            'Framing {4} | Beams {5} | Posts {6}\n'
            'Hangers {7} (double {8}) | Beam ties {9} | Corner brackets {10}').format(
                c('boards'),c('borders'),int(breakers),c('clips'),c('framing'),c('beams'),c('posts'),
                c('hangers'),c('double_hangers'),c('hurricane_straps'),c('corner_straps'))


def edge_labels(poly):
    import math
    return ['Edge {0}: {1:.2f} ft | ({2:.2f}, {3:.2f}) to ({4:.2f}, {5:.2f})'.format(
        i+1,math.hypot(b[0]-a[0],b[1]-a[1]),a[0],a[1],b[0],b[1])
        for i,a in enumerate(poly) for b in [poly[(i+1)%len(poly)]]]
