import ast
import csv
import io
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lib'))
from rt_accessory_layout import straight_stair,railing_paths,path_length
from rt_quantities import stock_estimate,allowance,csv_text


class AccessoryQuantityTests(unittest.TestCase):
    def test_breaker_quantity_measures_its_axis_and_groups_separately_from_perimeter(self):
        from test_hardware_families import Vector
        element=SimpleNamespace(Name='shape',Id=SimpleNamespace(Value=2**40),GetTypeId=lambda:None,
                                GetMaterialIds=lambda unused:[])
        points=[Vector(x,y,z) for x in (10,10.458333333) for y in (0,12) for z in (0,.94/12)]
        scope=dict(DB=SimpleNamespace(XYZ=Vector),api=SimpleNamespace(axes=lambda unused,s:(Vector(0,0,0),Vector(1,0,0),Vector(0,1,0)),
                                       vertices=lambda unused:points,read_stamp=lambda unused:{},id_value=lambda eid:eid.Value),
                   owned_registered=lambda *unused:True)
        tree=ast.parse((ROOT/'lib'/'rt_materials.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='measure')
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<breaker-quantity>','exec'),scope)
        parent=dict(anchor={},settings=dict(name='Deck',board_thickness_in=.94))
        item=dict(role='BORDER',key='BREAKER_1',axis='B',width_in=5.5,border_kind='breaker')
        record=dict(items=[dict(unique_id='breaker',item=item)])
        doc=SimpleNamespace(GetElement=lambda key:element if key=='breaker' else None)
        rows,volumes,warnings,lengths=scope['measure'](doc,parent,record,set())
        self.assertEqual(lengths,[12]); self.assertEqual(rows[0]['board_kind'],'breaker')
        self.assertTrue(rows[0]['type_name'].startswith('Breaker board |'))
        self.assertEqual(rows[0]['depth_in'],.94)
        item.pop('border_kind')
        rows,volumes,warnings,lengths=scope['measure'](doc,parent,record,set())
        self.assertFalse(rows[0]['type_name'].startswith('Breaker board |'))

    def test_stairs_quantities_preserve_equal_risers_and_one_fewer_treads(self):
        p=straight_stair(6,3,10,11)
        self.assertEqual(p['treads'],9)
        self.assertAlmostEqual(p['riser_in']*p['risers'],72)
        self.assertAlmostEqual(p['run_ft'],9*11/12)
        for args in ((0,3,10,11),(6,3,10.5,11),(6,3,1,11),(float('nan'),3,10,11)):
            with self.assertRaises(ValueError): straight_stair(*args)

    def test_closed_railing_and_stair_opening_have_correct_length_and_continuity(self):
        poly=[(0,0),(12,0),(12,10),(0,10)]
        paths=railing_paths(poly,[0,1,2,3])
        self.assertEqual(len(paths),1)
        self.assertEqual(paths[0][0],paths[0][-1])
        self.assertAlmostEqual(path_length(paths[0]),44)
        opened=railing_paths(poly,[0,1,2,3],0,6,3)
        self.assertEqual(len(opened),1)
        self.assertAlmostEqual(path_length(opened[0]),41)
        self.assertNotEqual(opened[0][0],opened[0][-1])

    def test_disconnected_rail_edges_stay_separate_and_invalid_opening_is_rejected(self):
        poly=[(0,0),(12,0),(12,10),(0,10)]
        self.assertEqual(len(railing_paths(poly,[0,2])),2)
        for args in ((poly,[],),(poly,[4],),(poly,[1],0,6,3),(poly,[0],0,1,3)):
            with self.assertRaises(ValueError): railing_paths(*args)

    def test_stock_estimate_allows_whole_stock_piece_but_accounts_for_saw_kerf(self):
        self.assertEqual(stock_estimate([20,10,9.9],20,.125)['stock_pieces'],2)
        self.assertEqual(stock_estimate([10,10],20,.125)['stock_pieces'],2)
        self.assertEqual(stock_estimate([10,10],20,0)['stock_pieces'],1)
        with self.assertRaises(ValueError): stock_estimate([21],20)
        self.assertEqual(stock_estimate([],20)['stock_pieces'],0)
        self.assertEqual(allowance(9,10),10)
        self.assertEqual(allowance(0,10),0)

    def test_csv_preserves_unicode_quotes_and_names_as_text(self):
        data=csv_text([['PT, "wood"','café','=CMD()',-3.5]])
        row=next(csv.reader(io.StringIO(data)))
        self.assertEqual(row,['PT, "wood"','café',"'=CMD()",'-3.5'])

    def test_aux_dependency_adoption_skips_existing_elements_types_and_cycles(self):
        class Type: pass
        class Element:
            def __init__(self,key,children): self.Id=SimpleNamespace(Value=key); self.children=children
            def GetDependentElements(self,unused): return [SimpleNamespace(Value=v) for v in self.children]
        root=Element(2**40,[2**40+1,7,8]); child=Element(2**40+1,[2**40]); old=Element(7,[])
        typed=Type(); typed.Id=SimpleNamespace(Value=8)
        elements={e.Id.Value:e for e in (root,child,old,typed)}
        scope=dict(DB=SimpleNamespace(ElementType=Type),api=SimpleNamespace(id_value=lambda eid:eid.Value))
        tree=ast.parse((ROOT/'lib'/'rt_accessories.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='newly_dependent')
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<new-dependencies>','exec'),scope)
        owned=scope['newly_dependent'](SimpleNamespace(GetElement=lambda eid:elements[eid.Value]),[root],{7})
        self.assertEqual({e.Id.Value for e in owned},{2**40,2**40+1})


if __name__=='__main__': unittest.main()
