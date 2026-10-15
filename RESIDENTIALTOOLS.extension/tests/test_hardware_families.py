import ast
import math
import os
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from rt_layout import OWNER, VERSION, validate_deletion_scope


class Id:
    def __init__(self, value):
        self.Value = value
    def Equals(self, other):
        return self.Value == other.Value


class Vector:
    def __init__(self, x, y, z=0):
        self.X, self.Y, self.Z = x, y, z
    def __add__(self, other):
        return Vector(self.X + other.X, self.Y + other.Y, self.Z + other.Z)
    def __sub__(self, other):
        return Vector(self.X - other.X, self.Y - other.Y, self.Z - other.Z)
    def Negate(self):
        return Vector(-self.X, -self.Y, -self.Z)
    def DotProduct(self, other):
        return self.X * other.X + self.Y * other.Y + self.Z * other.Z
    def __mul__(self, scalar):
        return Vector(self.X*scalar,self.Y*scalar,self.Z*scalar)
    def GetLength(self):
        return math.sqrt(self.DotProduct(self))
    def Normalize(self):
        return self*(1/self.GetLength())


def symbol(name, category, placement='point', host=0, plane=0, adaptive=False):
    cat = SimpleNamespace(Id=Id(category), Name='Structural Connections' if category == -2 else 'Generic Models')
    params = dict(host=SimpleNamespace(AsInteger=lambda: host),
                  plane=SimpleNamespace(AsInteger=lambda: plane))
    family = SimpleNamespace(Name=name, FamilyCategory=cat, FamilyPlacementType=placement,
                             get_Parameter=params.get, adaptive=adaptive)
    return SimpleNamespace(UniqueId=name, Family=family, Category=cat)


class HardwareFamilyTests(unittest.TestCase):
    def setUp(self):
        self.db = SimpleNamespace(
            BuiltInCategory=SimpleNamespace(OST_GenericModel=-1, OST_StructConnections=-2),
            FamilyPlacementType=SimpleNamespace(OneLevelBased='point', WorkPlaneBased='workplane'), ElementId=Id,
            XYZ=SimpleNamespace(BasisZ=Vector(0, 0, 1)),
            BuiltInParameter=SimpleNamespace(FAMILY_HOSTING_BEHAVIOR='host', FAMILY_WORK_PLANE_BASED='plane'),
            AdaptiveComponentFamilyUtils=SimpleNamespace(IsAdaptiveComponentFamily=lambda family: family.adaptive))
        self.symbols = [symbol('clip', -1), symbol('C_LUS210', -2),
                        symbol('hosted-connector', -2, host=1),
                        symbol('adaptive-connector', -2, adaptive=True),
                        symbol('plane-connector', -2, placement='workplane', plane=1),
                        symbol('other-category', -3)]
        self.scope = dict(DB=self.db, types=lambda doc, category:
                          [item for item in self.symbols if item.Category.Id.Value == category])
        tree = ast.parse((ROOT / 'lib' / 'rt_revit.py').read_text(encoding='utf-8'))
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name in ('clip_types', 'hardware_categories', 'hardware_types', 'point_family_reason',
                                       'hardware_family_reason', 'create_hardware', 'create_hardware_plane')]
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<hardware-family-policy>', 'exec'), self.scope)

    def test_native_structural_connection_family_is_hardware_not_a_clip(self):
        self.assertEqual([s.UniqueId for s in self.scope['hardware_types'](None)],
                         ['clip', 'C_LUS210', 'plane-connector'])
        self.assertEqual([s.UniqueId for s in self.scope['clip_types'](None)], ['clip'])

    def test_workplane_hardware_is_accepted_but_clip_policy_stays_point_only(self):
        for item in self.symbols[2:]:
            reason = self.scope['point_family_reason'](item.Family, self.scope['hardware_categories']())
            self.assertTrue(reason)
        self.assertIn('workplane', self.scope['point_family_reason'](
            self.symbols[4].Family, self.scope['hardware_categories']()))
        self.assertEqual(self.scope['hardware_family_reason'](self.symbols[4].Family), '')
        self.symbols.append(symbol('plane-generic', -1, placement='workplane', plane=1))
        self.assertNotIn('plane-generic', [s.UniqueId for s in self.scope['clip_types'](None)])

    def test_face_wall_adaptive_curve_and_other_categories_remain_ineligible(self):
        for item in [symbol('face-based', -2, placement='workplane', host=5),
                     symbol('wall-based', -2, host=1),
                     symbol('adaptive', -2, placement='workplane', adaptive=True),
                     symbol('curve', -2, placement='curve'),
                     symbol('other', -3, placement='workplane')]:
            self.assertTrue(self.scope['hardware_family_reason'](item.Family))

    def test_connector_category_uses_unhosted_xyz_overload_and_preserves_generic_level_overload(self):
        calls = []
        doc = SimpleNamespace(Create=SimpleNamespace(NewFamilyInstance=lambda *args: calls.append(args) or object()))
        self.scope.update(math=math, world_point=lambda *args: 'joint-point',
                          StructuralType=SimpleNamespace(NonStructural='nonstructural'))
        coord = (None, SimpleNamespace(X=1, Y=0))
        for item in (self.symbols[1], self.symbols[0]):
            self.scope['create_hardware'](doc, dict(x=0, y=0, key='hanger'), coord, 10, 'level', item)
        self.assertEqual(len(calls[0]), 3)
        self.assertEqual(len(calls[1]), 4)
        self.assertEqual(calls[0][0], 'joint-point')
        self.assertEqual(calls[1][2], 'level')

    def test_workplane_uses_reference_overload_and_in_plane_orientation_at_both_ends(self):
        calls = []
        doc = SimpleNamespace(Create=SimpleNamespace(NewFamilyInstance=lambda *args: calls.append(args) or object()))
        point = Vector(25, 31, 10)
        plane = SimpleNamespace(Origin=Vector(0, 0, 10), Normal=Vector(0, 0, 1))
        host = SimpleNamespace(GetPlane=lambda: plane, GetReference=lambda: 'managed-plane-reference')
        self.scope.update(math=math, world_point=lambda *args: point, LENGTH_TOL=.001/12)
        for angle in (0, math.pi/4, math.pi/2):
            u = Vector(math.cos(angle), math.sin(angle))
            for end in (0, 1):
                self.scope['create_hardware'](doc, dict(x=0, y=0, key='hanger', end=end),
                                              (None, u), 10, 'level', self.symbols[4], host)
                reference, location, direction, selected = calls[-1]
                self.assertEqual(reference, 'managed-plane-reference')
                self.assertIs(location, point)
                self.assertIs(selected, self.symbols[4])
                self.assertAlmostEqual(direction.DotProduct(plane.Normal), 0)
                self.assertAlmostEqual(direction.DotProduct(u), 1 if end == 0 else -1)
        # Fake DB has no RotateElement; rotating the hosted instance would fail.

    def test_workplane_requires_host_and_coplanar_location_before_creation(self):
        calls = []
        doc = SimpleNamespace(Create=SimpleNamespace(NewFamilyInstance=lambda *args: calls.append(args)))
        self.scope.update(world_point=lambda *args: Vector(0, 0, 11), LENGTH_TOL=.001/12)
        coord = (None, Vector(1, 0))
        args = (doc, dict(x=0, y=0, key='hanger'), coord, 10, None, self.symbols[4])
        with self.assertRaisesRegex(ValueError, 'requires a managed'):
            self.scope['create_hardware'](*args)
        host = SimpleNamespace(GetPlane=lambda: SimpleNamespace(Origin=Vector(0, 0, 10),
                                                                Normal=Vector(0, 0, 1)))
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.scope['create_hardware'](*args, hardware_plane=host)
        self.assertEqual(calls, [])

    def test_support_plane_flips_downward_normal_and_rejects_invalid_reference(self):
        calls = []
        geom = SimpleNamespace(Origin=Vector(0, 0, 10), Normal=Vector(0, 0, -1))
        host = SimpleNamespace(GetPlane=lambda: geom, GetReference=lambda: 'plane-ref',
                               Flip=lambda: setattr(geom, 'Normal', geom.Normal.Negate()))
        doc = SimpleNamespace(ActiveView='plan-view', Regenerate=lambda: None,
                              Create=SimpleNamespace(NewReferencePlane=lambda *args: calls.append(args) or host))
        origin = Vector(0, 0, 10)
        self.scope.update(world_point=lambda *args: origin)
        coord = (None, Vector(1, 0), Vector(0, 1))
        self.assertIs(self.scope['create_hardware_plane'](doc, coord, 10, 'layout-a', 'generation-a'), host)
        self.assertEqual(geom.Normal.Z, 1)
        bubble, free, cut, view = calls[0]
        self.assertAlmostEqual((bubble-free).DotProduct(cut), 0)
        self.assertEqual(view, 'plan-view')
        self.assertIn('layout-a', host.Name)
        host.GetReference = lambda: None
        with self.assertRaisesRegex(ValueError, 'no usable reference'):
            self.scope['create_hardware_plane'](doc, coord, 10, 'layout-a', 'generation-b')

    def test_vendor_workplane_loader_accepts_native_category_and_reuses_empty_owner_name(self):
        tree = ast.parse((ROOT / 'lib' / 'rt_simpson.py').read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == 'load_compatible')
        source_family = self.symbols[4].Family
        source_family.Name = ''  # Observed in the user's native LUS210 log.
        loaded = SimpleNamespace(Name='C_LUS210_3d_Cad_MULT_Prod', GetFamilySymbolIds=lambda: [17])
        doc = SimpleNamespace(GetElement=lambda key: self.symbols[4])
        for reuse in (True, False):
            actions = []
            family_doc = SimpleNamespace(IsFamilyDocument=True, OwnerFamily=source_family,
                LoadFamily=lambda target: actions.append('load') or loaded,
                Close=lambda save: actions.append(('close', save)))
            doc.Application = SimpleNamespace(OpenDocumentFile=lambda path: family_doc)
            api = SimpleNamespace(family_diagnostics=lambda family: dict(name='', category='Structural Connections',
                                                                         placement='WorkPlaneBased'),
                                  hardware_family_reason=self.scope['hardware_family_reason'],
                                  hardware_types=lambda target: [self.symbols[4]], symbol_name=lambda item: item.UniqueId)
            scope = dict(api=api, json=__import__('json'), os=os,
                DB=SimpleNamespace(Family=object, FilteredElementCollector=lambda target:
                    SimpleNamespace(OfClass=lambda cls: [loaded] if reuse else [])))
            exec(compile(ast.Module(body=[function], type_ignores=[]), '<native-loader>', 'exec'), scope)
            chosen, reused = scope['load_compatible'](doc, 'C_LUS210_3d_Cad_MULT_Prod.rfa', lambda msg: None)
            self.assertEqual(chosen, [self.symbols[4]])
            self.assertEqual(reused, reuse)
            self.assertEqual(actions.count('load'), 0 if reuse else 1)
            self.assertEqual(actions[-1], ('close', False))


class HardwareRebuildTests(unittest.TestCase):
    """Exercise the actual rebuild registry/deletion flow with an API stub."""
    def setUp(self):
        self.elements = {}
        self.serial = 2**40
        self.cascade = False
        self.deleted = []
        class Level:
            Elevation = 0
        class GenericList(list):
            def __class_getitem__(cls, key):
                return cls
            def Add(self, item):
                self.append(item)
        level = Level()
        self.symbol = symbol('plane-connector', -2, placement='workplane', plane=1)
        self.symbol.Activate = lambda: None
        def new_element():
            self.serial += 1
            element = SimpleNamespace(Id=Id(self.serial), UniqueId=str(self.serial), stamp={})
            self.elements[element.UniqueId] = element
            return element
        manual = new_element()
        self.manual_uid = manual.UniqueId
        def get_element(key):
            if key == 'level':
                return level
            return self.elements.get(str(key.Value) if isinstance(key, Id) else key)
        def delete(ids):
            self.deleted.append({item.Value for item in ids})
            for item in ids:
                self.elements.pop(str(item.Value), None)
            return list(ids) + ([manual.Id] if self.cascade else [])
        self.doc = SimpleNamespace(GetElement=get_element, Regenerate=lambda: None, Delete=delete)
        @contextmanager
        def transaction(doc, title, log):
            snapshot = dict(self.elements)
            try:
                yield
            except Exception:
                self.elements.clear()
                self.elements.update(snapshot)
                raise
        def write_stamp(element, payload):
            element.stamp = payload
        def tag(element, item, layout_id, generation, name):
            write_stamp(element, dict(owner=OWNER, version=VERSION, layout_id=layout_id,
                                      generation=generation, role=item['role']))
        collector = SimpleNamespace(WherePasses=lambda unused: [])
        self.scope = dict(DB=SimpleNamespace(Level=Level, ElementId=Id,
                          FamilyPlacementType=SimpleNamespace(WorkPlaneBased='workplane'),
                          FilteredElementCollector=lambda doc: collector),
                          schema=lambda: None, uuid=uuid, OWNER=OWNER, VERSION=VERSION,
                          SCHEMA_GUID='schema', ExtensibleStorageFilter=lambda guid: None,
                          validate_type=lambda doc, s: None,
                          validate_support_types=lambda doc, s: (None,None),
                          rt_simpson_catalog=SimpleNamespace(validate_selections=lambda *args: None),
                          validate_clip_type=lambda doc, s: None,
                          validate_hardware_type=lambda doc, uid, label: self.symbol if uid else None,
                          registered_elements=lambda doc, record:
                              ([doc.GetElement(uid) for uid in record['element_uids']], []) if record else ([], []),
                          axes=lambda anchor, s: None, transaction=transaction,
                          material=lambda *args: 1, create_hardware_plane=lambda *args: new_element(),
                          create_hardware=lambda *args: new_element(), tag=tag, write_stamp=write_stamp,
                          read_stamp=lambda element: element.stamp,
                          id_value=lambda eid: eid.Value, List=GenericList,
                          validate_deletion_scope=validate_deletion_scope, json=__import__('json'),
                          symbol_name=lambda item: item.UniqueId,
                          DataStorage=SimpleNamespace(Create=lambda doc: new_element()))
        tree = ast.parse((ROOT / 'lib' / 'rt_revit.py').read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'rebuild')
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<rebuild-registry>', 'exec'), self.scope)
        self.planned = dict(settings=dict(level_uid='level', name='Test', height_in=12, spacing_in=16,
                                         hanger_symbol_uid='plane-connector'),
                            boards=[], members=[], clips=[],
                            hardware=[dict(role='HANGER', key='near'), dict(role='HANGER', key='far')],
                            counts=dict(hangers=2), warnings=[])

    def build(self, storage=None, record=None, planned=None):
        return self.scope['rebuild'](self.doc, storage, record, {}, planned or self.planned, lambda message: None)

    def test_rebuild_replaces_shared_plane_and_hardware_then_hardware_off_cleans_all(self):
        first = self.build()
        self.assertEqual(first['counts']['hangers'], 2)
        self.assertEqual(first['managed_hardware_planes'], 1)
        self.assertEqual([entry['item']['role'] for entry in first['items']],
                         ['HARDWARE_PLANE', 'HANGER', 'HANGER'])
        self.assertEqual(len(first['element_uids']), 3)
        storage = next(item for item in self.elements.values() if item.stamp.get('role') == 'LAYOUT')
        second = self.build(storage, first)
        self.assertTrue(set(first['element_uids']).isdisjoint(self.elements))
        self.assertEqual(len(second['element_uids']), 3)
        self.assertEqual(self.deleted[-1], {int(uid) for uid in first['element_uids']})
        off = dict(self.planned, hardware=[], counts=dict(hangers=0),
                   settings=dict(self.planned['settings'], hanger_symbol_uid=''))
        third = self.build(storage, second, off)
        self.assertEqual(third['managed_hardware_planes'], 0)
        self.assertEqual(third['element_uids'], [])
        self.assertEqual(set(self.elements), {self.manual_uid, storage.UniqueId})

    def test_unregistered_dependency_on_host_plane_rolls_back_rebuild(self):
        first = self.build()
        storage = next(item for item in self.elements.values() if item.stamp.get('role') == 'LAYOUT')
        old_uids = set(self.elements)
        self.cascade = True
        with self.assertRaisesRegex(ValueError, 'unrelated'):
            self.build(storage, first)
        self.assertEqual(set(self.elements), old_uids)
        self.assertIs(storage.stamp, first)

    def test_hardware_elevation_planes_are_shared_by_height_and_removed_on_rebuild(self):
        planned=dict(self.planned,hardware=[dict(role='HANGER',key='near',z_offset_in=-9.25),
                                            dict(role='HANGER',key='far',z_offset_in=-9.25),
                                            dict(role='HANGER',key='different',z_offset_in=0)])
        first=self.build(planned=planned)
        self.assertEqual(first['managed_hardware_planes'],2)
        self.assertEqual(sum(i['item']['role']=='HARDWARE_PLANE' for i in first['items']),2)
        storage=next(e for e in self.elements.values() if e.stamp.get('role')=='LAYOUT')
        second=self.build(storage,first)
        self.assertEqual(second['managed_hardware_planes'],1)
        self.assertTrue(set(first['element_uids']).isdisjoint(self.elements))


class PostGeometryTests(unittest.TestCase):
    def setUp(self):
        self.values={}
        self.missing=False; self.frozen=False
        keys=SimpleNamespace(FAMILY_BASE_LEVEL_PARAM='base',FAMILY_TOP_LEVEL_PARAM='top',
                             FAMILY_BASE_LEVEL_OFFSET_PARAM='base-offset',FAMILY_TOP_LEVEL_OFFSET_PARAM='top-offset')
        def get_parameter(key):
            if self.missing: return None
            return SimpleNamespace(IsReadOnly=False,Set=lambda value:self.values.update({key:value}) or True)
        result=SimpleNamespace(Id=Id(2**40),get_Parameter=get_parameter)
        self.doc=SimpleNamespace(Create=SimpleNamespace(NewFamilyInstance=lambda *args:result),Regenerate=lambda:None)
        self.level=SimpleNamespace(Id=Id(10),Elevation=5)
        self.coord=(None,Vector(1,0),Vector(0,1))
        self.item=dict(key='POST_1',x=4,y=3,top_offset_in=-18.5,height_ft=6,width_in=5.5,depth_in=5.5)
        def vertices(element):
            lo=self.values['base-offset']+5
            hi=self.values['top-offset']+5+(1 if self.frozen else 0)
            return [Vector(x,y,z) for x in (4-5.5/24,4+5.5/24) for y in (3-5.5/24,3+5.5/24) for z in (lo,hi)]
        scope=dict(DB=SimpleNamespace(BuiltInParameter=keys),StructuralType=SimpleNamespace(Column='column'),
                   math=math,LENGTH_TOL=.001/12,vertices=vertices,world_point=lambda coord,x,y,z:Vector(x,y,z))
        tree=ast.parse((ROOT/'lib'/'rt_revit.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='create_post')
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<post-constraints>','exec'),scope)
        self.create=scope['create_post']

    def test_column_base_top_offsets_match_beam_underside_and_post_height(self):
        self.create(self.doc,self.item,self.coord,10,'post-symbol',self.level)
        self.assertAlmostEqual(self.values['top-offset']+5,10-18.5/12)
        self.assertAlmostEqual(self.values['top-offset']-self.values['base-offset'],6)
        self.assertEqual(self.values['base'].Value,self.values['top'].Value)

    def test_missing_constraints_and_inflexible_solids_fail_before_commit(self):
        self.missing=True
        with self.assertRaisesRegex(ValueError,'constraints'):
            self.create(self.doc,self.item,self.coord,10,'post-symbol',self.level)
        self.missing=False; self.frozen=True
        with self.assertRaisesRegex(ValueError,'geometry top mismatch'):
            self.create(self.doc,self.item,self.coord,10,'post-symbol',self.level)


if __name__ == '__main__':
    unittest.main()
