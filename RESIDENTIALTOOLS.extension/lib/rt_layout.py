# -*- coding: utf-8 -*-
"""Residential rectangular planning, feet unless suffixed _in; no Revit imports.

Balanced rows and polygon clipping adapt inspected DECKTOOLS board_math ideas.
Settings, staggered seams, double supports and clip eligibility are new here.
"""
import math
import rt_geometry

OWNER = 'RESIDENTIALTOOLS_RECT_V1'
VERSION = 1
EPS = 1.0e-7
DEFAULTS = dict(name='Residential deck', run_ft=12.0, span_ft=10.0,
                pa_jurisdiction='Montgomery / Berks / surrounding PA counties',
                height_in=0.0, board_axis='A', board_width_in=5.5,
                board_thickness_in=0.94, gap_in=0.1875, butt_gap_in=0.125,
                stock_ft=20.0, spacing_in=16.0, picture_frame=False,
                border_courses=1, board_angle_deg=0.0, joists_follow_angle=False, footprint_polygon=None,roof_clearance_in=6.0,
                stagger=True, seam_border=False, breaker_positions_ft='', rims=True, blocking=False,
                boards_enabled=True, framing_enabled=True, clips_enabled=True,
                exposure='Exterior pressure-treated', joist_width_in=1.5,
                joist_depth_in=9.25, blocking_spacing_ft=8.0,
                block_width_in=1.5, block_depth_in=9.25,
                clip_mode='Schematic solids', joist_symbol_uid='',
                block_symbol_uid='', clip_symbol_uid='', level_uid='',
                hanger_symbol_uid='', double_hanger_symbol_uid='',
                double_border_joists=False, hanger_anchor='Joist bottom', hanger_offset_in=0.0,
                hurricane_symbol_uid='', corner_strap_symbol_uid='',
                supports_enabled=False, beam_symbol_uid='', post_symbol_uid='',
                beam_width_in=3.0, beam_depth_in=9.25,
                beam_near_setback_ft=1.0, beam_far_setback_ft=1.0,
                post_width_in=5.5, post_depth_in=5.5, post_height_ft=6.0,
                post_end_setback_ft=0.5, post_spacing_ft=6.0)


def number(value, label, minimum, maximum):
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(label + ' must be numeric.')
    if math.isnan(result) or math.isinf(result) or not minimum <= result <= maximum:
        raise ValueError('{0} must be from {1:g} to {2:g}.'.format(label, minimum, maximum))
    return result


def settings(values, validate_layout=True):
    result = dict(DEFAULTS)
    result.update(values)
    result['name'] = result['name'].strip()
    result['pa_jurisdiction']=result['pa_jurisdiction'].strip()
    try:
        result['breaker_positions_ft']=result['breaker_positions_ft'].strip()
    except AttributeError:
        raise ValueError('Breaker positions must be comma-separated distances in feet.')
    if len(result['pa_jurisdiction'])>200:
        raise ValueError('PA project jurisdiction must be at most 200 characters.')
    if not result['name'] or len(result['name']) > 100:
        raise ValueError('Layout name must contain 1 to 100 characters.')
    limits = dict(run_ft=(2, 100), span_ft=(2, 100), height_in=(-12000, 12000),
                  board_width_in=(1, 5.5), board_thickness_in=(0.6, 2),
                  gap_in=(0.0625, 0.375), butt_gap_in=(0.0625, 0.375),
                  stock_ft=(12, 20), spacing_in=(12, 24),
                  joist_width_in=(0.5, 12), joist_depth_in=(2, 48),
                  blocking_spacing_ft=(2, 24), block_width_in=(0.5, 12),
                  block_depth_in=(2, 48), hanger_offset_in=(-48, 48),
                  beam_width_in=(0.5, 24), beam_depth_in=(2, 48),
                  beam_near_setback_ft=(0, 20), beam_far_setback_ft=(0, 20),
                  post_width_in=(2, 24), post_depth_in=(2, 24),
                  post_height_ft=(0.5, 30), post_end_setback_ft=(0, 20), post_spacing_ft=(1, 20),
                  board_angle_deg=(-180, 180), border_courses=(1, 2),roof_clearance_in=(0,1200))
    for key, bounds in limits.items():
        unit='inches' if key.endswith('_in') else 'feet' if key.endswith('_ft') else 'degrees' if key.endswith('_deg') else ''
        stem=key.rsplit('_',1)[0] if unit else key
        label={'run_ft':'Footprint edge A (feet)','span_ft':'Footprint edge B (feet)'}.get(
            key,stem.replace('_',' ').capitalize()+(' ('+unit+')' if unit else ''))
        result[key] = number(result[key], label, *bounds)
    if result['spacing_in'] not in (12, 16, 24):
        raise ValueError('Choose 12, 16 or 24 inch on-center spacing.')
    if result['stock_ft'] not in (12, 16, 20):
        raise ValueError('Choose 12, 16 or 20 foot stock.')
    if result['border_courses'] not in (1,2):
        raise ValueError('Choose one or two picture-frame courses.')
    result['border_courses'] = int(result['border_courses'])
    if result.get('footprint_polygon'):
        result['footprint_polygon'] = rt_geometry.polygon(result['footprint_polygon'])
        if any(min(p[i] for p in result['footprint_polygon']) < -EPS or
               max(p[i] for p in result['footprint_polygon']) > 100 for i in (0,1)):
            raise ValueError('Footprint exceeds the 100-foot prototype envelope.')
    if result['board_axis'] not in ('A', 'B'):
        raise ValueError('Choose board axis A or B. Joists run perpendicular.')
    if result['exposure'] not in ('Exterior pressure-treated', 'Interior untreated',
                                   'User-verified engineered/custom'):
        raise ValueError('Unknown framing exposure/category.')
    if result['clip_mode'] not in ('Schematic solids', 'Loaded family'):
        raise ValueError('Unknown clip mode.')
    if result['hanger_anchor'] not in ('Joist bottom', 'Framing top'):
        raise ValueError('Choose a valid hanger origin elevation.')
    for key in ('picture_frame', 'stagger', 'rims', 'blocking', 'boards_enabled',
                'framing_enabled', 'clips_enabled', 'double_border_joists', 'supports_enabled','joists_follow_angle','seam_border'):
        if not isinstance(result[key], bool):
            raise ValueError(key + ' must be a boolean.')
    if validate_layout:
        validate_layout_settings(result)
    return result


def validate_layout_settings(result):
    """Build/preview preflight; library loading and footprint editing remain independent."""
    if not result['boards_enabled'] and not result['framing_enabled']:
        raise ValueError('Enable boards, framing, or both.')
    if result['clips_enabled']:
        if not (result['boards_enabled'] and result['framing_enabled']):
            raise ValueError('Clips require generated boards and framing in this coordinated layout.')
        if result['clip_mode'] == 'Schematic solids' and abs(result['gap_in'] - .1875) > EPS:
            raise ValueError('Reused schematic clip fits a 3/16 inch gap only. '
                             'Disable clips or select a verified loaded clip for other gaps.')
    for key in ('hanger_symbol_uid', 'double_hanger_symbol_uid',
                'hurricane_symbol_uid', 'corner_strap_symbol_uid'):
        if result[key] and not result['framing_enabled']:
            raise ValueError('Hardware placement requires generated framing.')
        if result[key] and key != 'hurricane_symbol_uid' and not result['rims']:
            raise ValueError('Hardware placement requires end rim joists in this prototype.')
    if result['hanger_symbol_uid'] and result['hanger_symbol_uid'] == result['double_hanger_symbol_uid']:
        raise ValueError('Select different reviewed single and double hanger types.')
    if result['supports_enabled'] and not result['framing_enabled']:
        raise ValueError('Freestanding beams/posts require generated joists.')
    if result['seam_border']:
        if result['board_width_in'] <= 3*result['joist_width_in']+EPS:
            raise ValueError('Breaker-board backing requires board width greater than three joist widths.')


def balanced_rows(span, width_in, gap_in):
    width, gap = width_in / 12.0, gap_in / 12.0
    count = max(1, int(math.ceil((span + gap - EPS) / (width + gap))))
    if count == 1:
        return [(0.0, span, 'square')]
    edge = (span - (count - 2) * width - (count - 1) * gap) / 2.0
    if edge < .5 / 12.0 - EPS or edge > width + EPS:
        raise ValueError('Balanced perimeter rip is outside 1/2 inch to board width. '
                         'Adjust footprint, board width or gap.')
    rows, low = [], 0.0
    for i, piece_width in enumerate([edge] + [width] * (count - 2) + [edge]):
        mode = 'both'
        if i == 0:
            mode = 'right'
        elif i == count - 1:
            mode = 'left'
        rows.append((low, low + piece_width, mode))
        low += piece_width + gap
    return rows


def stations(run, section_width, spacing):
    if run < 4 * section_width:
        raise ValueError('Framing footprint is too narrow for selected member width.')
    low, high = section_width / 2.0, run - section_width / 2.0
    result = [low]
    while result[-1] + spacing < high - EPS:
        result.append(result[-1] + spacing)
    if high - result[-1] > EPS:
        result.append(high)
    return result


def joint_stations(start, end, supports, maximum, phase=0.0):
    """Minimum-piece path, preferring offset seams on alternate rows."""
    run = end - start
    if run <= maximum + EPS:
        return []
    candidates = sorted(set(round(x, 8) for x in supports
                            if start + .5 <= x <= end - .5))
    minimum = int(math.ceil(run / maximum))
    for pieces in range(minimum, minimum + 5):
        layer = {start: (0.0, [])}
        for k in range(1, pieces):
            target = start + run * k / float(pieces) + phase
            next_layer = {}
            for x in candidates:
                choices = []
                for previous, (cost, path) in layer.items():
                    if .5 - EPS <= x - previous <= maximum + EPS:
                        choices.append((cost + (x - target) ** 2, path + [x]))
                if choices:
                    next_layer[x] = min(choices, key=lambda item: item[0])
            layer = next_layer
        feasible = [(cost, path) for last, (cost, path) in layer.items()
                    if .5 - EPS <= end - last <= maximum + EPS]
        if feasible:
            return min(feasible, key=lambda item: item[0])[1]
    raise ValueError('No supported stock-length split. Reduce spacing or revise footprint.')


def clip_polygon(points, normal, limit, above=True):
    """Convex half-plane clip, adapted from DECKTOOLS picture-frame math."""
    result = []
    for i, current in enumerate(points):
        previous = points[i - 1]
        a = previous[0] * normal[0] + previous[1] * normal[1] - limit
        b = current[0] * normal[0] + current[1] * normal[1] - limit
        inside_a = a >= -EPS if above else a <= EPS
        inside_b = b >= -EPS if above else b <= EPS
        if inside_a != inside_b:
            ratio = a / (a - b)
            result.append((previous[0] + ratio * (current[0] - previous[0]),
                           previous[1] + ratio * (current[1] - previous[1])))
        if inside_b:
            result.append(current)
    clean = []
    for point in result:
        if not clean or sum(abs(point[i] - clean[-1][i]) for i in (0, 1)) > EPS:
            clean.append(point)
    if len(clean) > 1 and sum(abs(clean[0][i] - clean[-1][i]) for i in (0, 1)) < EPS:
        clean.pop()
    return clean


def frame_boards(run, span, width, corner_gap):
    # One course only. Leave half the gap normal to each 45 degree miter.
    offset = corner_gap / math.sqrt(2.0)
    specs = [
        ('BOTTOM', [(0, 0), (run, 0), (run-width, width), (width, width)],
         [((1, -1), offset, True), ((1, 1), run-offset, False)], 'A'),
        ('TOP', [(width, span-width), (run-width, span-width), (run, span), (0, span)],
         [((1, 1), span+offset, True), ((1, -1), run-span-offset, False)], 'A'),
        ('LEFT', [(0, 0), (width, width), (width, span-width), (0, span)],
         [((-1, 1), offset, True), ((1, 1), span-offset, False)], 'B'),
        ('RIGHT', [(run-width, width), (run, 0), (run, span), (run-width, span-width)],
         [((1, 1), run+offset, True), ((-1, 1), span-run-offset, False)], 'B'),
    ]
    result = []
    for side, polygon, cuts, axis in specs:
        for normal, limit, above in cuts:
            polygon = clip_polygon(polygon, normal, limit, above)
        result.append(dict(key='FRAME_' + side, role='BORDER', polygon=polygon,
                           width_in=width * 12.0, axis=axis, edge_mode='square',
                           length_ft=max(p[0 if axis == 'A' else 1] for p in polygon)
                           - min(p[0 if axis == 'A' else 1] for p in polygon)))
    return result


def hanger_groups(members, width_in):
    """Group only touching parallel joists with identical span endpoints."""
    joists = sorted([m for m in members if m['role'] in
                     ('JOIST', 'JOINT_SUPPORT', 'BORDER_SUPPORT')], key=lambda m: m['a'][0])
    groups = []
    for member in joists:
        if groups:
            previous = groups[-1][-1]
            touching = abs(member['a'][0] - previous['a'][0] - width_in/12.0) < EPS
            same_span = (abs(member['a'][1] - previous['a'][1]) < EPS and
                         abs(member['b'][1] - previous['b'][1]) < EPS and
                         abs(member['a'][0] - member['b'][0]) < EPS and
                         abs(previous['a'][0] - previous['b'][0]) < EPS)
            if touching and same_span:
                groups[-1].append(member)
                continue
        groups.append([member])
    return groups


def boards_by_row(boards,row_count):
    result=dict((row,[]) for row in range(row_count))
    for board in boards:
        row=board.get('row')
        if row in result: result[row].append(board)
    return result


def plan(values):
    s = settings(values)
    if (s['seam_border'] or abs(s['board_angle_deg'])>EPS or s.get('footprint_polygon') or s['border_courses']==2 or
            (s['picture_frame'] and max(s['run_ft'],s['span_ft'])>s['stock_ft'])):
        from rt_advanced_layout import plan as advanced_plan
        return advanced_plan(s)
    # Geometry is always board-local. Coordinate adapter swaps the footprint axes.
    run, span = s['run_ft'], s['span_ft']
    if s['board_axis'] == 'B':
        run, span = span, run
    jw, step = s['joist_width_in'] / 12.0, s['spacing_in'] / 12.0
    base = stations(run, jw, step)
    inset = ((s['board_width_in'] + s['gap_in']) / 12.0
             if s['picture_frame'] and s['boards_enabled'] else 0.0)
    if min(run - 2*inset, span - 2*inset) < 1.0:
        raise ValueError('Picture frame leaves less than one foot of decking field.')
    if inset and max(run, span) > s['stock_ft'] + EPS:
        raise ValueError('Prototype picture-frame sides must fit one stock board. '
                         'Long border splits/backing are not implemented yet.')
    rows, boards, seam_positions = [], [], set()
    if s['boards_enabled']:
        rows = [(a+inset, b+inset, mode) for a, b, mode in
                balanced_rows(span-2*inset, s['board_width_in'], s['gap_in'])]
        joint_cache={}
        for row, (low, high, mode) in enumerate(rows):
            phase = 2 * step if s['stagger'] and row % 2 else 0.0
            if phase not in joint_cache:
                joint_cache[phase]=joint_stations(inset,run-inset,base,s['stock_ft'],phase)
            joints=joint_cache[phase]
            seam_positions.update(joints)
            limits = [inset] + joints + [run-inset]
            for piece in range(len(limits)-1):
                start = limits[piece] + (s['butt_gap_in']/24.0 if piece else 0.0)
                end = limits[piece+1] - (s['butt_gap_in']/24.0
                                         if piece < len(limits)-2 else 0.0)
                boards.append(dict(key='BOARD_{0:03d}_{1:02d}'.format(row+1, piece+1),
                                   role='BOARD', row=row, start=start, end=end,
                                   low=low, high=high, width_in=(high-low)*12.0,
                                   length_ft=end-start, edge_mode=mode))
        if inset:
            boards.extend(frame_boards(run, span, s['board_width_in']/12.0,
                                       s['butt_gap_in']/12.0))
    required_supports = []
    for joint in sorted(seam_positions):
        required_supports.extend([(joint-jw/2.0, 'JOINT_SUPPORT'),
                                  (joint+jw/2.0, 'JOINT_SUPPORT')])
    if inset:
        width = s['board_width_in'] / 12.0
        if width < jw - EPS:
            raise ValueError('Picture-frame width must be at least the selected framing width.')
        if s['double_border_joists']:
            # Straddle the field/border gap with two touching members. Keep
            # each ply countable; the hanger is centered on their assembly.
            center = width + s['gap_in']/24.0
            required_supports.extend([(center-jw/2.0, 'BORDER_SUPPORT'),
                                      (center+jw/2.0, 'BORDER_SUPPORT'),
                                      (run-center-jw/2.0, 'BORDER_SUPPORT'),
                                      (run-center+jw/2.0, 'BORDER_SUPPORT')])
        else:
            required_supports.extend([(width-jw/2.0, 'BORDER_SUPPORT'),
                                      (run-width+jw/2.0, 'BORDER_SUPPORT'),
                                      (inset+jw/2.0, 'BORDER_SUPPORT'),
                                      (run-inset-jw/2.0, 'BORDER_SUPPORT')])
    supports = [(x, 'JOIST') for x in base
                if not any(abs(x-j) < jw-EPS for j, role in required_supports)]
    supports.extend(required_supports)
    supports.sort()
    # Avoid overlapping framing when a requested border support is nearly on-grid.
    clean_supports = []
    for x, role in supports:
        if clean_supports and x - clean_supports[-1][0] < jw - EPS:
            if role == 'JOINT_SUPPORT' or clean_supports[-1][1] == 'JOINT_SUPPORT':
                raise ValueError('Joint support overlaps framing. Change spacing or deck dimensions.')
            continue
        clean_supports.append((x, role))
    members = []
    start_y = jw if s['rims'] else 0.0
    end_y = span-jw if s['rims'] else span
    if s['framing_enabled']:
        for i, (x, role) in enumerate(clean_supports):
            members.append(dict(key='JOIST_{0:03d}'.format(i+1), role=role,
                                a=(x, start_y), b=(x, end_y)))
        if s['rims']:
            for label, y in (('NEAR', jw/2.0), ('FAR', span-jw/2.0)):
                members.append(dict(key='RIM_' + label, role='RIM', a=(0.0, y), b=(run, y)))
        if s['blocking']:
            for i in range(len(clean_supports)-1):
                a = clean_supports[i][0] + jw/2.0
                b = clean_supports[i+1][0] - jw/2.0
                if b-a > .5/12.0:
                    # Preserve the original one-row behavior for spans up to the
                    # chosen maximum row spacing; distribute additional rows
                    # evenly so no bay between rows exceeds that maximum.
                    clear_span = end_y - start_y
                    row_count = max(1, int(math.ceil(clear_span / s['blocking_spacing_ft'])) - 1)
                    for row in range(row_count):
                        y = start_y + clear_span * (row + 1) / float(row_count + 1)
                        members.append(dict(key='BLOCK_{0:02d}_{1:03d}'.format(row+1, i+1),
                                            role='BLOCK', a=(a, y), b=(b, y),
                                            section_width_in=s['block_width_in'],
                                            section_depth_in=s['block_depth_in']))
    beams, posts = [], []
    if s['supports_enabled']:
        beam_ys = [s['beam_near_setback_ft'], span-s['beam_far_setback_ft']]
        beam_half = s['beam_width_in']/24.0
        post_half_y = s['post_depth_in']/24.0
        if any(y-beam_half < start_y-EPS or y+beam_half > end_y+EPS or
               y-post_half_y < -EPS or y+post_half_y > span+EPS for y in beam_ys):
            raise ValueError('Beam setbacks must place beams fully below the joist spans and posts inside the footprint.')
        if beam_ys[1]-beam_ys[0] < max(s['beam_width_in'], s['post_depth_in'])/12.0+EPS:
            raise ValueError('Freestanding beams or their posts would overlap; revise setbacks.')
        low, high = s['post_end_setback_ft'], run-s['post_end_setback_ft']
        if low < s['post_width_in']/24.0-EPS or high-low < s['post_width_in']/12.0+EPS:
            raise ValueError('Post end setbacks must fit at least two separate posts inside each beam length.')
        intervals = max(1, int(math.ceil((high-low)/s['post_spacing_ft'])))
        if (high-low)/intervals < s['post_width_in']/12.0+EPS:
            raise ValueError('Post spacing would overlap adjacent posts.')
        for i, y in enumerate(beam_ys):
            beam_key = 'BEAM_{0}'.format(i+1)
            beams.append(dict(key=beam_key, role='BEAM', a=(0, y), b=(run, y),
                              section_width_in=s['beam_width_in'], section_depth_in=s['beam_depth_in'],
                              z_offset_in=-s['joist_depth_in']))
            for j in range(intervals+1):
                posts.append(dict(key='POST_{0}_{1:02d}'.format(i+1, j+1), role='POST', beam_key=beam_key,
                                  x=low+(high-low)*j/float(intervals), y=y,
                                  top_offset_in=-s['joist_depth_in']-s['beam_depth_in'],
                                  height_ft=s['post_height_ft'], width_in=s['post_width_in'], depth_in=s['post_depth_in']))
    clips, hardware, warnings, skipped_hangers = [], [], [], []
    if s['clips_enabled']:
        by_row = boards_by_row(boards,len(rows))
        for row in range(len(rows)-1):
            gap_y = (rows[row][1] + rows[row+1][0]) / 2.0
            if not start_y-EPS <= gap_y <= end_y+EPS:
                continue
            for x, role in clean_supports:
                if all(any(b['start']-EPS <= x <= b['end']+EPS for b in by_row[r])
                       for r in (row, row+1)):
                    clips.append(dict(key='CLIP_{0:03d}_{1:03d}'.format(row+1, len(clips)+1),
                                      role='CLIP', x=x, y=gap_y))
    joist_members = [member for member in members
                     if member['role'] in ('JOIST', 'JOINT_SUPPORT', 'BORDER_SUPPORT')]
    groups = hanger_groups(members, s['joist_width_in'])
    if s['hanger_symbol_uid'] or s['double_hanger_symbol_uid']:
        for group in groups:
            if len(group) > 2:
                raise ValueError('Three or more touching joists require a reviewed multi-ply hanger workflow.')
            double = len(group) == 2
            if not s['double_hanger_symbol_uid' if double else 'hanger_symbol_uid']:
                continue
            role = 'DOUBLE_HANGER' if double else 'HANGER'
            for end, endpoint in enumerate(('a', 'b')):
                point = (sum(m[endpoint][0] for m in group)/len(group), group[0][endpoint][1])
                at_corner = (abs(group[0]['a'][0]-jw/2.0) < EPS or
                             abs(group[-1]['a'][0]+jw/2.0-run) < EPS)
                if s['corner_strap_symbol_uid'] and at_corner:
                    skipped_hangers.append(dict(member_keys=[m['key'] for m in group], end=end,
                                                reason='Selected corner bracket at perimeter rim connection'))
                    continue
                hardware.append(dict(key='{0}_{1}_{2}'.format(role, group[0]['key'], end+1),
                                     role=role, x=point[0], y=point[1], end=end,
                                     member_keys=[m['key'] for m in group], ply_count=len(group),
                                     width_in=s['joist_width_in']*len(group), depth_in=s['joist_depth_in'],
                                     z_offset_in=s['hanger_offset_in'] -
                                         (s['joist_depth_in'] if s['hanger_anchor'] == 'Joist bottom' else 0)))
        if any(len(group) == 2 for group in groups) and not s['double_hanger_symbol_uid']:
            warnings.append('Touching double joists have no selected double hanger; '
                            'single hangers are not substituted for them.')
        if s['double_hanger_symbol_uid'] and not any(len(group) == 2 for group in groups):
            warnings.append('No touching double joists exist; no double hangers will be placed.')
    if s['hurricane_symbol_uid']:
        if not beams:
            warnings.append('Hurricane ties require enabled beams/posts; none are placed at rim ends.')
        for i, beam in enumerate(beams):
            for member in joist_members:
                hardware.append(dict(key='HURRICANE_{0}_{1}'.format(beam['key'], member['key']),
                                     role='HURRICANE_STRAP', x=member['a'][0], y=beam['a'][1], end=i,
                                     joist_key=member['key'], beam_key=beam['key'],
                                     z_offset_in=-s['joist_depth_in']))
    if s['corner_strap_symbol_uid']:
        for label, point,rotation in (('SW', (0.0, 0.0),0), ('SE', (run, 0.0),90),
                             ('NW', (0.0, span),270), ('NE', (run, span),180)):
            hardware.append(dict(key='CORNER_STRAP_' + label, role='CORNER_STRAP',
                                 x=point[0], y=point[1],rotation_deg=rotation))
    if hardware:
        warnings.append('Hardware families are inserted at planned '
                        'joist/rim or footprint-corner points. Verify family origins, orientation, '
                        'fasteners and manufacturer installation requirements in Revit; these '
                        'placements are not an engineered connection design.')
    if skipped_hangers:
        warnings.append('{0} end hangers omitted where selected corner brackets occupy '
                        'the perimeter rim connections.'.format(len(skipped_hangers)))
    if inset:
        warnings.append('Square-edge picture-frame boards require separate perimeter/face '
                        'fasteners. Hidden-clip count covers grooved field gaps only.')
    if seam_positions:
        warnings.append('Butt joints use paired full-span joists. Verify required '
                        'end distances, twin supports and fastening against your product.')
    if s['stagger'] and seam_positions:
        patterns = [tuple(round(b['end'], 6) for b in boards
                          if b.get('row') == r and b['end'] < run-inset-EPS)
                    for r in range(len(rows))]
        if any(patterns[i] == patterns[i+1] for i in range(len(patterns)-1)):
            warnings.append('Some adjacent joint patterns coincide because stock/grid '
                            'constraints prevent the preferred stagger.')
    if not s['rims']:
        warnings.append('Rims are disabled; end bearing/supports require separate modeling.')
    if s['boards_enabled'] and not s['framing_enabled']:
        warnings.append('Framing is disabled. Board joint positions use a planned grid; '
                        'their physical supports have not been generated.')
    if beams:
        warnings.append('Freestanding drop beams and posts use user-selected sections and spacing. '
                        'Check member sizing, bearing, cantilevers, materials and connections; '
                        'footings, post bases/caps and structural design are not included.')
    count = len(boards) + len(members) + len(beams) + len(posts) + len(clips) + len(hardware)
    if count > 15000:
        raise ValueError('Prototype limit is 15,000 generated elements per layout.')
    return dict(settings=s, run=run, span=span, boards=boards, members=members,
                beams=beams, posts=posts, clips=clips, hardware=hardware, joints=sorted(seam_positions), rows=rows,
                supports=clean_supports, warnings=warnings, skipped_hanger_connections=skipped_hangers,
                counts=dict(boards=sum(b['role'] == 'BOARD' for b in boards),
                            borders=sum(b['role'] == 'BORDER' for b in boards),
                            framing=len(members), clips=len(clips),
                            beams=len(beams), posts=len(posts),
                            hangers=sum(h['role'] in ('HANGER', 'DOUBLE_HANGER') for h in hardware),
                            double_hangers=sum(h['role'] == 'DOUBLE_HANGER' for h in hardware),
                            hurricane_straps=sum(h['role'] == 'HURRICANE_STRAP' for h in hardware),
                            corner_straps=sum(h['role'] == 'CORNER_STRAP' for h in hardware)))


def owned_registered(record, stamp, unique_id):
    """Deletion eligibility requires BOTH registry membership and exact ownership."""
    return (unique_id in record.get('element_uids', []) and
            stamp.get('owner') == OWNER and stamp.get('version') == VERSION and
            stamp.get('layout_id') == record.get('layout_id') and
            stamp.get('generation') == record.get('generation') and
            stamp.get('role') in ('BOARD', 'BORDER', 'JOIST', 'JOINT_SUPPORT',
                                  'BORDER_SUPPORT', 'RIM', 'BLOCK', 'CLIP', 'HANGER',
                                  'DOUBLE_HANGER', 'BEAM', 'POST', 'BORDER_BACKING', 'HURRICANE_STRAP', 'CORNER_STRAP',
                                  'HARDWARE_PLANE', 'STAIR', 'STAIR_PART', 'RAILING', 'RAILING_PART'))


def validate_deletion_scope(registered_ids, deleted_ids):
    unexpected = set(deleted_ids) - set(registered_ids)
    if unexpected:
        raise ValueError('Deleting generated elements would also delete unrelated '
                         'dependent elements {0}. Rebuild rolled back.'.format(sorted(unexpected)))
