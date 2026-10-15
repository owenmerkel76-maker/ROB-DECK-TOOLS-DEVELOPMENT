"""Pure math/ownership checks. These are not Revit integration tests."""
import ast
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
import rt_board_profile
import rt_clip
from rt_layout import (DEFAULTS, EPS, OWNER, VERSION, clip_polygon, owned_registered,
                       plan, settings, hanger_groups, validate_deletion_scope)


def polygon_area(points):
    return abs(sum(points[i][0]*points[(i+1) % len(points)][1]
                   - points[(i+1) % len(points)][0]*points[i][1]
                   for i in range(len(points)))) / 2.0


class RectangularLayoutTests(unittest.TestCase):
    def test_default_counts_and_balanced_rips(self):
        result = plan(DEFAULTS)
        self.assertEqual(result['counts'], dict(boards=22, borders=0, framing=12, clips=210,
                                                beams=0, posts=0, hangers=0, double_hangers=0, hurricane_straps=0, corner_straps=0))
        self.assertAlmostEqual(result['rows'][0][0], 0)
        self.assertAlmostEqual(result['rows'][-1][1], 10)
        self.assertAlmostEqual(result['rows'][0][1]-result['rows'][0][0],
                               result['rows'][-1][1]-result['rows'][-1][0])
        for a, b in zip(result['rows'], result['rows'][1:]):
            self.assertAlmostEqual(b[0]-a[1], .1875/12)

    def test_spacing_choices_and_final_edge_support(self):
        for spacing, member_count in ((12, 15), (16, 12), (24, 9)):
            result = plan(dict(DEFAULTS, spacing_in=spacing))
            self.assertEqual(result['counts']['framing'], member_count)
            centers = [x for x, role in result['supports']]
            self.assertAlmostEqual(centers[0], .0625)
            self.assertAlmostEqual(centers[-1], 11.9375)
            for a, b in zip(centers[:-2], centers[1:-1]):
                self.assertAlmostEqual(b-a, spacing/12)

    def test_axis_swap_changes_array_and_span(self):
        result = plan(dict(DEFAULTS, board_axis='B'))
        self.assertEqual((result['run'], result['span']), (10, 12))
        self.assertEqual(result['members'][0]['a'][1], .125)
        self.assertEqual(result['members'][0]['b'][1], 11.875)

    def test_long_boards_have_supported_staggered_joints(self):
        result = plan(dict(DEFAULTS, run_ft=30))
        boards = [b for b in result['boards'] if b['role'] == 'BOARD']
        self.assertEqual(result['counts']['boards'], 44)
        self.assertEqual(len(result['joints']), 2)
        row0 = [b['end'] for b in boards if b['row'] == 0]
        row1 = [b['end'] for b in boards if b['row'] == 1]
        self.assertNotEqual(row0, row1)
        for b in boards:
            self.assertLessEqual(b['length_ft'], 20 + EPS)
        supports = [x for x, role in result['supports'] if role == 'JOINT_SUPPORT']
        for joint in result['joints']:
            self.assertTrue(any(abs(x-(joint-.0625)) < EPS for x in supports))
            self.assertTrue(any(abs(x-(joint+.0625)) < EPS for x in supports))

    def test_clip_points_have_two_actual_board_edges_and_finite_joists(self):
        for length in (12, 30, 47):
            result = plan(dict(DEFAULTS, run_ft=length))
            points = set()
            for clip in result['clips']:
                key = (round(clip['x'], 7), round(clip['y'], 7))
                self.assertNotIn(key, points)
                points.add(key)
                self.assertTrue(any(abs(m['a'][0]-clip['x']) < EPS and
                                    m['a'][1]-EPS <= clip['y'] <= m['b'][1]+EPS
                                    for m in result['members']
                                    if m['role'] in ('JOIST', 'JOINT_SUPPORT', 'BORDER_SUPPORT')))
                adjacent = [b for b in result['boards'] if b['role'] == 'BOARD' and
                            b['start']-EPS <= clip['x'] <= b['end']+EPS and
                            (abs(b['high']+.1875/24-clip['y']) < EPS or
                             abs(b['low']-.1875/24-clip['y']) < EPS)]
                self.assertEqual(len(adjacent), 2)
            self.assertEqual(len(points), result['counts']['clips'])

    def test_picture_frames_are_separate_mitered_nonoverlapping_solids(self):
        result = plan(dict(DEFAULTS, picture_frame=True))
        self.assertEqual(result['counts'], dict(boards=20, borders=4, framing=16, clips=190,
                                                beams=0, posts=0, hangers=0, double_hangers=0, hurricane_straps=0, corner_straps=0))
        frames = [b for b in result['boards'] if b['role'] == 'BORDER']
        for frame in frames:
            self.assertEqual(frame['edge_mode'], 'square')
            self.assertEqual(len(frame['polygon']), 4)
            self.assertGreater(polygon_area(frame['polygon']), 0)
            self.assertLessEqual(frame['length_ft'], 20)
        for i, a in enumerate(frames):
            for b in frames[i+1:]:
                intersection = a['polygon']
                for k, p in enumerate(b['polygon']):
                    q = b['polygon'][(k+1) % len(b['polygon'])]
                    normal = (p[1]-q[1], q[0]-p[0])
                    if intersection:
                        intersection = clip_polygon(intersection, normal,
                                                    p[0]*normal[0]+p[1]*normal[1])
                self.assertLess(polygon_area(intersection), 1.e-7)
        self.assertTrue(any('face' in warning for warning in result['warnings']))

    def test_adjustable_gap_and_schematic_clip_gap_guard(self):
        result = plan(dict(DEFAULTS, gap_in=.125, clips_enabled=False))
        self.assertAlmostEqual(result['rows'][1][0]-result['rows'][0][1], .125/12)
        with self.assertRaises(ValueError):
            plan(dict(DEFAULTS, gap_in=.125))
        result = plan(dict(DEFAULTS, gap_in=.125, clip_mode='Loaded family'))
        self.assertGreater(result['counts']['clips'], 0)

    def test_framing_only_and_boards_only(self):
        framing = plan(dict(DEFAULTS, boards_enabled=False, clips_enabled=False, blocking=True))
        self.assertEqual(framing['boards'], [])
        self.assertEqual(framing['clips'], [])
        self.assertEqual(sum(m['role'] == 'BLOCK' for m in framing['members']), 9)
        boards = plan(dict(DEFAULTS, framing_enabled=False, clips_enabled=False))
        self.assertEqual(boards['members'], [])
        self.assertTrue(any('disabled' in warning for warning in boards['warnings']))

    def test_blocking_rows_follow_spacing_and_selected_section_dimensions(self):
        framing = plan(dict(DEFAULTS, span_ft=30, boards_enabled=False, clips_enabled=False,
                            blocking=True, blocking_spacing_ft=8,
                            block_width_in=1.5, block_depth_in=7.25,
                            block_symbol_uid='loaded-blocking-type'))
        blocks = [member for member in framing['members'] if member['role'] == 'BLOCK']
        rows = sorted(set(member['a'][1] for member in blocks))
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(right-left <= 8 + EPS for left, right in zip(rows, rows[1:])))
        self.assertTrue(all(member['section_width_in'] == 1.5 and
                            member['section_depth_in'] == 7.25 for member in blocks))
        self.assertEqual(len(blocks), 3 * (len(framing['supports']) - 1))

    def test_optional_hardware_points_and_count_totals(self):
        values = dict(DEFAULTS, hanger_symbol_uid='hanger-type',
                      hurricane_symbol_uid='strap-type', corner_strap_symbol_uid='corner-type')
        result = plan(values)
        joists = [member for member in result['members']
                  if member['role'] in ('JOIST', 'JOINT_SUPPORT', 'BORDER_SUPPORT')]
        self.assertEqual(result['counts']['hangers'], 2 * len(joists)-4)
        self.assertEqual(result['counts']['hurricane_straps'], 0)
        self.assertEqual(result['counts']['corner_straps'], 4)
        self.assertEqual(len(result['hardware']), 2 * len(joists))
        self.assertEqual(len(set(item['key'] for item in result['hardware'])), len(result['hardware']))
        self.assertTrue(any('not an engineered connection design' in warning
                            for warning in result['warnings']))
        with self.assertRaisesRegex(ValueError, 'requires generated framing'):
            plan(dict(values, framing_enabled=False, clips_enabled=False))
        with self.assertRaisesRegex(ValueError, 'requires end rim joists'):
            plan(dict(values, rims=False))

    def test_bounds_and_nonfinite_inputs_fail_before_geometry(self):
        for change in ({'run_ft': float('nan')}, {'span_ft': float('inf')},
                       {'spacing_in': 15}, {'stock_ft': 21}, {'board_axis': 'C'},
                       {'gap_in': 0}, {'board_thickness_in': 0},
                       {'exposure': 'Unclassified'},
                       {'boards_enabled': False}, {'border_courses': 3}):
            with self.assertRaises(ValueError, msg=str(change)):
                plan(dict(DEFAULTS, **change))

    def test_touching_border_pairs_get_four_centered_double_hangers_not_eight_singles(self):
        result = plan(dict(DEFAULTS, picture_frame=True, double_border_joists=True,
                           hanger_symbol_uid='single', double_hanger_symbol_uid='double'))
        doubles = [h for h in result['hardware'] if h['role'] == 'DOUBLE_HANGER']
        self.assertEqual(len(doubles), 4)
        self.assertEqual(result['counts']['double_hangers'], 4)
        members = {m['key']: m for m in result['members']}
        double_members = set()
        for hanger in doubles:
            self.assertEqual(hanger['width_in'], 3)
            a, b = [members[key] for key in hanger['member_keys']]
            self.assertAlmostEqual(b['a'][0]-a['a'][0], 1.5/12)
            self.assertAlmostEqual(hanger['x'], (a['a'][0]+b['a'][0])/2)
            double_members.update(hanger['member_keys'])
        self.assertEqual(len(double_members), 4)
        self.assertFalse(any(set(h['member_keys']) & double_members for h in result['hardware'] if h['role'] == 'HANGER'))
        self.assertEqual(result['counts']['hangers'], 24)

    def test_spaced_border_supports_remain_single_and_missing_double_is_reported(self):
        spaced = plan(dict(DEFAULTS, picture_frame=True, hanger_symbol_uid='single', double_hanger_symbol_uid='double'))
        self.assertEqual(spaced['counts']['double_hangers'], 0)
        touching = plan(dict(DEFAULTS, picture_frame=True, double_border_joists=True, hanger_symbol_uid='single'))
        self.assertEqual(touching['counts']['hangers'], 20)
        self.assertTrue(any('no selected double hanger' in w for w in touching['warnings']))

    def test_corner_brackets_exclude_only_corner_hangers_and_origins_can_be_adjusted(self):
        result = plan(dict(DEFAULTS, picture_frame=True, double_border_joists=True,
                           hanger_symbol_uid='single', double_hanger_symbol_uid='double', corner_strap_symbol_uid='corner'))
        self.assertEqual(result['counts']['hangers'], 20)
        self.assertEqual(result['counts']['double_hangers'], 4)
        self.assertEqual(len(result['skipped_hanger_connections']), 4)
        hangers = [h for h in result['hardware'] if h['role'] in ('HANGER', 'DOUBLE_HANGER')]
        self.assertTrue(all(h['z_offset_in'] == -9.25 for h in hangers))
        top = plan(dict(result['settings'], hanger_anchor='Framing top', hanger_offset_in=-.25))
        self.assertTrue(all(h['z_offset_in'] == -.25 for h in top['hardware'] if 'member_keys' in h))

    def test_freestanding_supports_meet_joists_and_hurricane_ties_only_cross_beams(self):
        result = plan(dict(DEFAULTS, supports_enabled=True, hurricane_symbol_uid='tie'))
        self.assertEqual(result['counts']['beams'], 2)
        self.assertEqual(result['counts']['posts'], 6)
        self.assertEqual(result['counts']['hurricane_straps'], 20)
        self.assertEqual([beam['a'][1] for beam in result['beams']], [1, 9])
        self.assertTrue(all(beam['z_offset_in'] == -9.25 for beam in result['beams']))
        for beam in result['beams']:
            posts = [p for p in result['posts'] if p['beam_key'] == beam['key']]
            self.assertTrue(all(p['y'] == beam['a'][1] and p['top_offset_in'] == -18.5 for p in posts))
            self.assertTrue(all(b['x']-a['x'] <= 6+EPS for a,b in zip(posts,posts[1:])))
        self.assertTrue(all(h['y'] in (1,9) and h['z_offset_in'] == -9.25 for h in result['hardware']))
        self.assertEqual(plan(dict(result['settings'], supports_enabled=False))['counts']['hurricane_straps'], 0)

    def test_invalid_support_geometry_and_same_hanger_type_are_rejected(self):
        for change in (dict(beam_near_setback_ft=0), dict(beam_near_setback_ft=5, beam_far_setback_ft=5),
                       dict(post_end_setback_ft=0), dict(post_end_setback_ft=6),
                       dict(framing_enabled=False, clips_enabled=False)):
            with self.assertRaises(ValueError):
                plan(dict(DEFAULTS, supports_enabled=True, **change))
        with self.assertRaisesRegex(ValueError, 'different reviewed'):
            plan(dict(DEFAULTS, hanger_symbol_uid='same', double_hanger_symbol_uid='same'))

    def test_pair_grouping_respects_span_and_does_not_span_an_air_gap(self):
        members = [dict(key='a', role='JOIST', a=(0,0), b=(0,10)),
                   dict(key='b', role='JOIST', a=(.125,0), b=(.125,9)),
                   dict(key='c', role='JOIST', a=(.25,0), b=(.25,9)),
                   dict(key='d', role='JOIST', a=(.4,0), b=(.4,9))]
        self.assertEqual([len(g) for g in hanger_groups(members, 1.5)], [1,2,1])

    def test_many_stock_and_spacing_combinations(self):
        for stock in (12, 16, 20):
            for spacing in (12, 16, 24):
                for length in (12, 19, 25, 39, 60):
                    result = plan(dict(DEFAULTS, run_ft=length, stock_ft=stock, spacing_in=spacing))
                    all_items = result['boards'] + result['members'] + result['clips']
                    keys = [item['key'] for item in all_items]
                    self.assertEqual(len(keys), len(set(keys)))
                    self.assertEqual(result, plan(result['settings']))
                    self.assertTrue(all(b['length_ft'] <= stock+EPS for b in result['boards']))
                    centers = [x for x, role in result['supports']]
                    self.assertTrue(all(b-a >= .125-EPS for a, b in zip(centers, centers[1:])))

    def test_source_board_profile_and_clip_geometry(self):
        self.assertEqual(len(rt_clip.parts()), 6)
        spacer = rt_clip.parts()[0][0]
        self.assertEqual(max(p[1] for p in spacer)-min(p[1] for p in spacer), .1875)
        grooved = rt_board_profile.make_outline(5.5, 'both')
        self.assertAlmostEqual(rt_board_profile.section_area_in2(grooved), 5.5*.94 - 2*.25*.2)


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.record = dict(layout_id='one', generation='current', element_uids=['registered'])
        self.stamp = dict(owner=OWNER, version=VERSION, layout_id='one', generation='current', role='BOARD')

    def test_only_registered_correct_generation_is_owned(self):
        self.assertTrue(owned_registered(self.record, self.stamp, 'registered'))
        self.assertFalse(owned_registered(self.record, self.stamp, 'manually-copied'))
        for role in ('HANGER', 'DOUBLE_HANGER', 'BEAM', 'POST', 'HURRICANE_STRAP', 'CORNER_STRAP', 'HARDWARE_PLANE'):
            self.assertTrue(owned_registered(self.record, dict(self.stamp, role=role), 'registered'))
            self.assertFalse(owned_registered(self.record, dict(self.stamp, role=role), 'manually-copied'))
        for change in ({'owner': 'DECKTOOLS'}, {'layout_id': 'other'},
                       {'generation': 'old'}, {'version': 2}, {'role': 'LAYOUT'}):
            self.assertFalse(owned_registered(self.record, dict(self.stamp, **change), 'registered'))

    def test_unrelated_dependencies_refuse_deletion(self):
        validate_deletion_scope({2**40, 2**40+1}, {2**40, 2**40+1})
        with self.assertRaisesRegex(ValueError, 'unrelated'):
            validate_deletion_scope({2**40}, {2**40, 7})

    def test_modern_element_id_helper_never_reads_32_bit_value(self):
        tree = ast.parse((ROOT / 'lib' / 'rt_revit.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'id_value')
        namespace = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<id-helper>', 'exec'), namespace)
        class Id:
            Value = 2**40 + 42
            @property
            def IntegerValue(self):
                raise AssertionError('Deprecated 32-bit API access')
        self.assertEqual(namespace['id_value'](Id()), 2**40 + 42)


class ClipPreflightTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT / 'lib' / 'rt_revit.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == 'validate_clip_type')
        self.symbol = SimpleNamespace(UniqueId='chosen', Family=SimpleNamespace(Name=rt_clip.FAMILY_NAME+'_R2027'))
        scope = dict(rt_clip=rt_clip, clip_types=lambda doc: [self.symbol])
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<clip-preflight>', 'exec'), scope)
        self.validate = scope['validate_clip_type']
        self.doc = SimpleNamespace(GetElement=lambda uid: self.symbol if uid == 'chosen' else None)

    def test_loaded_reused_schematic_requires_exact_gap(self):
        s = dict(DEFAULTS, clip_mode='Loaded family', clip_symbol_uid='chosen')
        self.assertIs(self.validate(self.doc, s), self.symbol)
        with self.assertRaisesRegex(ValueError, '3/16'):
            self.validate(self.doc, dict(s, gap_in=.125))

    def test_custom_eligible_clip_can_fit_other_gap(self):
        self.symbol.Family.Name = 'User verified 1-8 clip'
        self.assertIs(self.validate(self.doc, dict(DEFAULTS, clip_mode='Loaded family',
                                                 clip_symbol_uid='chosen', gap_in=.125)), self.symbol)

    def test_missing_selection_refuses_arbitrary_generic_model(self):
        with self.assertRaisesRegex(ValueError, 'Choose'):
            self.validate(self.doc, dict(DEFAULTS, clip_mode='Loaded family', clip_symbol_uid=''))


class HardwarePreflightTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT / 'lib' / 'rt_revit.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == 'validate_hardware_type')
        self.symbol = SimpleNamespace(UniqueId='hanger')
        scope = dict(hardware_types=lambda doc: [self.symbol])
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<hardware-preflight>', 'exec'), scope)
        self.validate = scope['validate_hardware_type']
        self.doc = SimpleNamespace(GetElement=lambda uid: self.symbol if uid == 'hanger' else None)

    def test_optional_point_family_must_be_loaded_and_eligible(self):
        self.assertIsNone(self.validate(self.doc, '', 'joist hangers'))
        self.assertIs(self.validate(self.doc, 'hanger', 'joist hangers'), self.symbol)
        with self.assertRaisesRegex(ValueError, 'point-based Generic Model'):
            self.validate(self.doc, 'missing', 'joist hangers')


if __name__ == '__main__':
    unittest.main()
