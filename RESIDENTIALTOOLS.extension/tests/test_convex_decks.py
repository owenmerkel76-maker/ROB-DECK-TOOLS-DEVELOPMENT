"""Convex, angle, miter and stock checks; not live Revit tests."""
import math
import ast
import sys
from pathlib import Path
import unittest
from types import SimpleNamespace
from test_hardware_families import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lib'))
import rt_geometry as geo
from rt_layout import DEFAULTS, plan


class ConvexDeckTests(unittest.TestCase):
    def test_diagonal_border_support_combinations_respect_stock_and_outline(self):
        for run in (12,19.5,30,42):
            for span in (10,12):
                for angle in (15,30,45):
                    for courses in (1,2):
                        for beams in (False,True):
                            with self.subTest(run=run,span=span,angle=angle,courses=courses,beams=beams):
                                result=plan(dict(DEFAULTS,run_ft=run,span_ft=span,board_angle_deg=angle,
                                                 picture_frame=True,border_courses=courses,supports_enabled=beams))
                                boundary=geo.frame(result['settings'])['polygon']
                                for board in result['boards']:
                                    self.assertLessEqual(board['length_ft'],20+geo.EPS)
                                    self.assertTrue(all(geo.point_inside(p,boundary) for p in board['polygon']))
                                self.assertEqual(result['counts']['beams'],2 if beams else 0)

    def test_breaker_board_separates_long_fields_and_has_center_and_paired_backing(self):
        for run in (23,30,42,60):
            result=plan(dict(DEFAULTS,run_ft=run,span_ft=12,seam_border=True,picture_frame=True,
                             border_courses=2,double_hanger_symbol_uid='double'))
            breakers=[b for b in result['boards'] if b.get('border_kind')=='breaker']
            self.assertTrue(breakers)
            for board in result['boards']: self.assertLessEqual(board['length_ft'],20+geo.EPS)
            for breaker in breakers:
                x=sum(p[0] for p in breaker['polygon'])/4
                support=[m for m in result['members'] if m['role'] in ('JOIST','JOINT_SUPPORT') and abs(m['a'][0]-x)<.3]
                self.assertEqual(len(support),5)
                for field in (b for b in result['boards'] if b['role']=='BOARD'):
                    self.assertFalse(geo.intersect(field['polygon'],breaker['polygon']))
            self.assertGreaterEqual(result['counts']['double_hangers'],4*len(breakers))
        for invalid in (dict(breaker_positions_ft='nan'),dict(breaker_positions_ft='0'),
                        dict(breaker_positions_ft='10,10'),dict(board_width_in=3)):
            with self.assertRaises(ValueError): plan(dict(DEFAULTS,seam_border=True,run_ft=42,**invalid))

    def test_stepped_manual_breaker_trims_diagonal_fields_and_keeps_framing(self):
        poly=[(0,2),(9,2),(9,0),(20,0),(20,12),(0,12)]
        for angle in (0,15,45):
            for rotate in (False,True):
                result=plan(dict(DEFAULTS,run_ft=20,span_ft=12,footprint_polygon=poly,seam_border=True,
                                 breaker_positions_ft='10',board_angle_deg=angle,joists_follow_angle=rotate,
                                 picture_frame=True,border_courses=2,double_hanger_symbol_uid='double'))
                boundary=geo.frame(result['settings'])['polygon']
                breakers=[b for b in result['boards'] if b.get('border_kind')=='breaker']
                fields=[b for b in result['boards'] if b['role']=='BOARD']
                self.assertTrue(breakers); self.assertGreaterEqual(result['counts']['double_hangers'],4)
                for board in result['boards']:
                    self.assertTrue(all(geo.point_inside(p,boundary) for p in board['polygon']))
                    self.assertLessEqual(board['length_ft'],20+geo.EPS)
                for breaker in breakers:
                    for board in fields:
                        self.assertFalse(geo.intersection_parts(breaker['polygon'],board['polygon']))
                # Check actual clipped cut vertices against the physical width
                # and finite span of the corresponding framing members.
                deck_frame=geo.frame(result['settings'])
                framing_frame=deck_frame if rotate else geo.frame(dict(result['settings'],board_angle_deg=0))
                def to_framing(point):
                    c,s=math.cos(deck_frame['angle']),math.sin(deck_frame['angle'])
                    x=deck_frame['shift'][0]+c*point[0]-s*point[1]-framing_frame['shift'][0]
                    y=deck_frame['shift'][1]+s*point[0]+c*point[1]-framing_frame['shift'][1]
                    c,s=math.cos(framing_frame['angle']),math.sin(framing_frame['angle'])
                    return (c*x+s*y,-s*x+c*y)
                supports=[(to_framing(m['a']),to_framing(m['b'])) for m in result['members']
                          if m['role'] in ('JOIST','JOINT_SUPPORT','BORDER_SUPPORT')]
                targets=(10-(5.5/24+.125/12),10+(5.5/24+.125/12))
                cut_vertices=[to_framing(p) for b in fields for p in b['polygon']
                              if any(abs(to_framing(p)[0]-x)<1.e-6 for x in targets)]
                self.assertTrue(cut_vertices)
                for x,y in cut_vertices:
                    self.assertTrue(any(abs(x-a[0])<=1.5/24+geo.EPS and
                                        min(a[1],b[1])-geo.EPS<=y<=max(a[1],b[1])+geo.EPS for a,b in supports))
                for clip in result['clips']:
                    self.assertFalse(any(geo.point_inside((clip['x'],clip['y']),b['polygon']) for b in breakers))
                self.assertEqual(len(result['boards']),len(set(b['key'] for b in result['boards'])))

    def test_breakers_clip_at_notch_and_split_long_pieces_without_filling_voids(self):
        poly=[(0,0),(4,0),(4,25),(8,25),(8,0),(12,0),(12,30),(0,30)]
        result=plan(dict(DEFAULTS,run_ft=12,span_ft=30,footprint_polygon=poly,seam_border=True,
                         breaker_positions_ft='2,10',double_hanger_symbol_uid='double'))
        breakers=[b for b in result['boards'] if b.get('border_kind')=='breaker']
        self.assertEqual(len(breakers),4)
        for board in result['boards']:
            self.assertTrue(all(geo.point_inside(p,poly) for p in board['polygon']))
            self.assertLessEqual(board['length_ft'],20+geo.EPS)
        for x in (2,10):
            center=[m for m in result['members'] if m['role']=='JOIST' and abs(m['a'][0]-x)<geo.EPS]
            self.assertTrue(any(m['a'][1]<15<m['b'][1] for m in center))

    def test_breaker_automatic_stock_splits_on_long_stepped_outline(self):
        poly=[(0,2),(9,2),(9,0),(42,0),(42,12),(0,12)]
        for angle in (0,15,45):
            result=plan(dict(DEFAULTS,run_ft=42,span_ft=12,footprint_polygon=poly,seam_border=True,
                             board_angle_deg=angle,picture_frame=True,border_courses=2))
            self.assertTrue(any(b.get('border_kind')=='breaker' for b in result['boards']))
            self.assertTrue(all(b['length_ft']<=20+geo.EPS for b in result['boards']))

    def test_skewed_boundary_breaker_seams_have_backing_inside_actual_framing(self):
        poly=[(0,0),(30,0),(24,30),(0,30)]
        result=plan(dict(DEFAULTS,run_ft=30,span_ft=30,footprint_polygon=poly,seam_border=True,
                         breaker_positions_ft='10',blocking=True))
        breakers=[b for b in result['boards'] if b.get('border_kind')=='breaker']
        self.assertEqual(len(breakers),2)
        center=[m for m in result['members'] if m['role']=='JOIST' and abs(m['a'][0]-10)<geo.EPS]
        self.assertTrue(any(m['a'][1]<15<m['b'][1] for m in center))
        for m in (m for m in result['members'] if m['role']=='BORDER_BACKING'):
            width=m['section_width_in']/12
            a,b=m['a'],m['b']
            self.assertTrue(all(geo.point_inside(p,poly) for p in [(a[0],a[1]-width/2),(b[0],b[1]-width/2),
                                                                  (b[0],b[1]+width/2),(a[0],a[1]+width/2)]))

    def test_custom_breaker_supports_preserve_selected_maximum_joist_spacing(self):
        for spacing in (12,16,24):
            for center in (9.35,10,11.73):
                result=plan(dict(DEFAULTS,run_ft=30,span_ft=12,seam_border=True,
                                 breaker_positions_ft=str(center),spacing_in=spacing))
                xs=sorted(set(m['a'][0] for m in result['members'] if m['role'] in ('JOIST','JOINT_SUPPORT','BORDER_SUPPORT')))
                self.assertTrue(all(b-a<=spacing/12+geo.EPS for a,b in zip(xs,xs[1:])))

    def test_stepped_breaker_beam_ties_still_follow_actual_crossings(self):
        result=plan(dict(DEFAULTS,run_ft=20,span_ft=12,footprint_polygon=[(0,2),(9,2),(9,0),(20,0),(20,12),(0,12)],
                         seam_border=True,breaker_positions_ft='10',board_angle_deg=30,
                         picture_frame=True,border_courses=2,supports_enabled=True,hurricane_symbol_uid='tie',
                         double_hanger_symbol_uid='double'))
        joists=[m for m in result['members'] if m['role'] in ('JOIST','JOINT_SUPPORT','BORDER_SUPPORT')]
        self.assertEqual(result['counts']['beams'],2)
        self.assertEqual(result['counts']['hurricane_straps'],2*len(joists))
        self.assertGreaterEqual(result['counts']['double_hangers'],4)

    def test_u_outline_diagonal_rows_preserve_disconnected_regions(self):
        poly=[(0,0),(4,0),(4,7),(8,7),(8,0),(12,0),(12,10),(0,10)]
        for angle in (15,45):
            result=plan(dict(DEFAULTS,footprint_polygon=poly,board_angle_deg=angle,run_ft=12,span_ft=10))
            boundary=geo.frame(result['settings'])['polygon']
            for board in result['boards']:
                self.assertTrue(all(geo.point_inside(p,boundary) for p in board['polygon']))
            self.assertEqual(len(set(b['key'] for b in result['boards'])),len(result['boards']))

    def test_planar_sloped_floor_can_supply_level_roof_projection(self):
        class Line:
            def __init__(self,a,b): self.a,self.b=a,b; self.Length=(b-a).GetLength()
            def GetEndPoint(self,i): return self.a if i==0 else self.b
        class Face: pass
        points=[Vector(x,y,10+.2*x) for x,y in [(0,0),(12,0),(12,10),(0,10)]]
        face=Face(); face.FaceNormal=Vector(-.2,0,1).Normalize(); face.Origin=points[0]; face.Area=120/face.FaceNormal.Z
        face.GetEdgesAsCurveLoops=lambda:[[Line(a,b) for a,b in zip(points,points[1:]+points[:1])]]
        floor=SimpleNamespace(Id=SimpleNamespace(Value=2**40),UniqueId='roof-floor',get_Geometry=lambda options:None)
        scope=dict(DB=SimpleNamespace(Options=lambda:None,PlanarFace=Face,Line=Line,XYZ=Vector),
                   api=SimpleNamespace(geometry_solids=lambda unused:[SimpleNamespace(Faces=[face])],id_value=lambda eid:eid.Value))
        tree=ast.parse((Path(__file__).resolve().parents[1]/'lib'/'rt_command.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='floor_rectangle')
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<projected-floor>','exec'),scope)
        with self.assertRaises(ValueError): scope['floor_rectangle'](floor)
        anchor,run,span,z=scope['floor_rectangle'](floor,True)
        self.assertAlmostEqual(run*span,120); self.assertAlmostEqual(z,12.4)
        self.assertTrue(anchor['roof_projection']); self.assertEqual(anchor['footprint_polygon'],None)

    def test_stepped_floor_reader_accepts_six_edges_and_preserves_actual_area(self):
        class Line:
            def __init__(self,a,b): self.a,self.b=a,b; self.Length=(b-a).GetLength()
            def GetEndPoint(self,i): return self.a if i==0 else self.b
        class Face: pass
        points=[Vector(x,y,10) for x,y in [(0,2),(9,2),(9,0),(20,0),(20,12),(0,12)]]
        face=Face(); face.FaceNormal=Vector(0,0,1); face.Origin=points[0]; face.Area=222
        face.GetEdgesAsCurveLoops=lambda:[[Line(a,b) for a,b in zip(points,points[1:]+points[:1])]]
        floor=SimpleNamespace(Id=SimpleNamespace(Value=2**40),UniqueId='source-floor',get_Geometry=lambda options:None)
        scope=dict(DB=SimpleNamespace(Options=lambda:None,PlanarFace=Face,Line=Line,XYZ=Vector),
                   api=SimpleNamespace(geometry_solids=lambda unused:[SimpleNamespace(Faces=[face])],id_value=lambda eid:eid.Value))
        root=Path(__file__).resolve().parents[1]
        tree=ast.parse((root/'lib'/'rt_command.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='floor_rectangle')
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<six-edge-floor>','exec'),scope)
        anchor,run,span,z=scope['floor_rectangle'](floor)
        self.assertEqual(len(anchor['footprint_polygon']),6)
        self.assertAlmostEqual(geo.area(anchor['footprint_polygon']),222)
        self.assertEqual(anchor['source_floor_uid'],'source-floor')
        self.assertEqual(z,10)
        self.assertNotEqual(run*span,222)
        self.assertTrue(plan(dict(DEFAULTS,run_ft=run,span_ft=span,footprint_polygon=anchor['footprint_polygon']))['boards'])

    def test_stepped_outline_boards_do_not_fill_the_notch_and_supports_share_bearings(self):
        poly=[(0,2),(9,2),(9,0),(20,0),(20,12),(0,12)]
        for angle in (0,15,45):
            result=plan(dict(DEFAULTS,run_ft=20,span_ft=12,footprint_polygon=poly,board_angle_deg=angle,
                             picture_frame=True,border_courses=2,supports_enabled=True,hurricane_symbol_uid='tie'))
            boundary=geo.frame(result['settings'])['polygon']
            self.assertEqual(result['counts']['beams'],2)
            self.assertEqual(result['counts']['borders'],12)
            for board in result['boards']:
                self.assertTrue(all(geo.point_inside(p,boundary) for p in board['polygon']))
            self.assertGreater(result['counts']['hurricane_straps'],0)

    def test_u_outline_scan_and_clipping_return_two_actual_regions(self):
        poly=geo.polygon([(0,0),(4,0),(4,7),(8,7),(8,0),(12,0),(12,10),(0,10)])
        pieces=geo.intersection_parts([(0,1),(12,1),(12,2),(0,2)],poly)
        self.assertEqual(len(pieces),2)
        self.assertAlmostEqual(sum(geo.area(p) for p in pieces),8)
        self.assertEqual(geo.vertical_spans([(y,x) for x,y in poly][::-1],1),[(0,4),(8,12)])

    def test_polygon_rejects_concavity_self_intersection_and_degenerate_edges(self):
        for poly in ([(0,0),(5,0),(2,1),(5,5),(0,5)],[(0,0),(5,5),(0,5),(5,0)],
                     [(0,0),(0,0),(5,0),(5,5),(0,5)]):
            with self.assertRaises(ValueError):
                geo.convex(poly)
        self.assertAlmostEqual(geo.area(geo.convex([(0,0),(0,10),(12,10),(12,0)])),120)

    def test_inset_preserves_width_and_rejects_consumed_footprint(self):
        poly=[(0,0),(12,0),(10,10),(0,10)]
        inner=geo.inset(poly,.5)
        for a,b in zip(poly,poly[1:]+poly[:1]):
            length=math.hypot(b[0]-a[0],b[1]-a[1])
            distances=[((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]))/length for p in inner]
            self.assertAlmostEqual(min(distances),.5)
        with self.assertRaises(ValueError):
            geo.inset(poly,7)

    def test_angle_frame_maps_back_to_original_boundary_and_axis_b(self):
        for angle in (0,15,30,45,-30):
            for axis in ('A','B'):
                f=geo.frame(dict(DEFAULTS,board_angle_deg=angle,board_axis=axis))
                c,s=math.cos(f['angle']),math.sin(f['angle'])
                recovered=[(round(c*x-s*y+f['shift'][0],6),round(s*x+c*y+f['shift'][1],6)) for x,y in f['polygon']]
                self.assertEqual(set(recovered),{(0,0),(12,0),(12,10),(0,10)})

    def test_two_border_courses_have_gaps_miters_and_stock_limited_splits(self):
        poly=[(0,0),(42,0),(42,12),(0,12)]
        pieces,seams=geo.border_pieces(poly,5.5/12,.1875/12,2,20,.125/12)
        self.assertGreater(len(pieces),8)
        self.assertTrue(seams)
        self.assertEqual({b['course'] for b in pieces},{1,2})
        for board in pieces:
            self.assertLessEqual(board['length_ft'],20+geo.EPS)
            self.assertGreater(geo.area(board['polygon']),0)
        for i,a in enumerate(pieces):
            for b in pieces[i+1:]:
                self.assertEqual(geo.intersect(a['polygon'],b['polygon']),[])

    def test_long_double_border_plans_backing_and_countable_piece_lengths(self):
        result=plan(dict(DEFAULTS,run_ft=42,span_ft=12,picture_frame=True,border_courses=2,
                         double_border_joists=True,double_hanger_symbol_uid='double'))
        self.assertTrue(any(m['role']=='JOINT_SUPPORT' for m in result['members']))
        self.assertTrue(all(b['length_ft']<=20+geo.EPS for b in result['boards']))
        self.assertGreater(result['counts']['borders'],8)
        self.assertGreater(result['counts']['double_hangers'],0)

    def test_angled_boards_and_clip_locations_are_clipped_inside_trapezoid(self):
        poly=[(0,0),(18,0),(15,12),(0,12)]
        for angle in (0,15,45):
            result=plan(dict(DEFAULTS,run_ft=18,span_ft=12,footprint_polygon=poly,
                             board_angle_deg=angle,picture_frame=True,border_courses=2))
            boundary=geo.frame(result['settings'])['polygon']
            self.assertTrue(result['boards'])
            self.assertTrue(result['members'])
            for board in result['boards']:
                self.assertTrue(all(all((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])>=-1.e-6
                                       for a,b in zip(boundary,boundary[1:]+boundary[:1])) for p in board['polygon']))
                self.assertLessEqual(board['length_ft'],20+geo.EPS)
            self.assertEqual(len({(round(c['x'],6),round(c['y'],6)) for c in result['clips']}),result['counts']['clips'])


if __name__=='__main__':
    unittest.main()
