"""Regression coverage for the October 14 workflow/quantity review."""
import ast
import math
from pathlib import Path
import sys
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lib'))
import rt_layout
import rt_presentation
import rt_simpson_catalog
from rt_quantities import grouped_stock,stock_estimate
from test_hardware_families import Vector


def function(module,name,scope):
    tree=ast.parse((ROOT/'lib'/module).read_text(encoding='utf-8'))
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),module,'exec'),scope)
    return scope[name],node


class ReviewQualityTests(unittest.TestCase):
    def test_manager_inspection_distinguishes_saved_counts_from_current_missing_items(self):
        child=dict(root_uids=['stair'],parent_generation='old')
        elements=[Obj(UniqueId='board',role='BOARD'),Obj(UniqueId='plane',role='HARDWARE_PLANE')]
        def registered(doc,record,require_editable=False):
            return ([Obj(UniqueId='stair')],[]) if record is child else (elements,['missing-board'])
        module=Obj(records=lambda *args:[(None,child)])
        with patch.dict(sys.modules,{'rt_accessories':module}):
            inspect,unused=function('rt_manager.py','_inspection',dict(
                api=Obj(registered_elements=registered,read_stamp=lambda e:dict(role=e.role)),_summary=lambda r:'Saved summary'))
            details=inspect(None,dict(layout_id='deck',generation='new',counts={},items=[]))
        self.assertIn('Current registered primary pieces: 1',details)
        self.assertIn('Current hardware work planes: 1',details)
        self.assertIn('Current stair/railing assemblies: 1',details)
        self.assertIn('Missing registered elements: 1',details)
        self.assertIn('older deck generation',details)

    def test_ties_and_brackets_can_be_browsed_without_joist_dimensions(self):
        self.assertEqual(rt_simpson_catalog.candidates('hurricane',None,None,'unknown')[0]['model'],'H2.5A')
        self.assertEqual(rt_simpson_catalog.candidates('corner','unfinished','unfinished','unknown')[0]['model'],'A35')
        with self.assertRaises((ValueError,TypeError)):
            rt_simpson_catalog.candidates('hanger',None,None,'unknown')

    def test_family_type_label_avoids_repeating_identical_names(self):
        label,node=function('rt_revit.py','symbol_name',dict(DB=Obj(BuiltInParameter=Obj(SYMBOL_NAME_PARAM=1))))
        symbol=Obj(Family=Obj(Name='LUS210'),UniqueId='id',get_Parameter=lambda key:Obj(HasValue=True,AsString=lambda:'LUS210'))
        self.assertEqual(label(symbol),'LUS210')
        symbol.get_Parameter=lambda key:Obj(HasValue=True,AsString=lambda:'Type A')
        self.assertEqual(label(symbol),'LUS210 | Type A')

    def test_stock_groups_do_not_share_square_grooved_or_different_material_stock(self):
        def row(role,length,material,profile):
            return dict(role=role,length_ft=length,materials=[material],stock_profile=profile,stock_width_in=5.5,depth_in=.94)
        rows=[row('BOARD',12,'Brown','Grooved field'),row('BORDER',8,'Brown','Square-edge'),
              row('BOARD',8,'Gray','Grooved field')]
        estimates=grouped_stock(rows,20,0,0,0)
        self.assertEqual(len(estimates),3)
        self.assertEqual(sum(e['stock_pieces'] for e in estimates),3)
        self.assertEqual(sum(e['installed_length_ft'] for e in estimates),28)

    def test_trim_oversize_withholds_order_without_discarding_installed_length(self):
        rows=[dict(role='BOARD',length_ft=20,materials=['Brown'],stock_width_in=5.5,depth_in=.94)]
        report=grouped_stock(rows,20,.125,.25,10)[0]
        self.assertFalse(report['estimate_complete']); self.assertIsNone(report['order_with_allowance'])
        self.assertEqual(report['installed_length_ft'],20)
        self.assertEqual(grouped_stock(rows,20,.125,0,0)[0]['order_with_allowance'],1)

    def test_stock_cut_plan_preserves_cuts_and_accounts_for_kerf_and_trim(self):
        cuts=[12,7.8,10,8,4,3]
        result=stock_estimate(cuts,20,.125,.25)
        self.assertEqual(sorted(v for board in result['cut_plan'] for v in board),sorted(cuts))
        for board in result['cut_plan']:
            self.assertLessEqual(sum(board)+.125/12*(len(board)-1)+.25/12,20+1.e-7)

    def test_unfinished_dimension_draft_stays_editable_until_build(self):
        values=rt_presentation.editable_settings(dict(run_ft='unfinished',stock_ft='20',border_courses='2'))
        self.assertEqual(values['run_ft'],'unfinished'); self.assertEqual(values['stock_ft'],20)
        with self.assertRaisesRegex(ValueError,'Footprint edge A'):
            rt_layout.settings(values)

    def test_hardware_collect_keeps_unfinished_unrelated_fields_without_normalization(self):
        def fail(*args,**kwargs): raise AssertionError('Build validation ran during a library operation')
        collect,node=function('rt_ui.py','collect',dict(settings=fail,api=Obj(text_type=str)))
        obj=Obj(footprint_polygon=None,simpson_sources={},block_symbol_is_default=False,
                hardware=[],levels=[],joists=[],block_types=[],beams=[],posts=[],clips=[])
        names={n.attr for n in ast.walk(node) if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name) and n.value.id=='self' and n.attr[0].isupper()}
        names.update(n.value for n in ast.walk(node) if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value[:1].isupper() and n.value.isalnum())
        for name in names: setattr(obj,name,Obj(Text='unfinished',SelectedItem='20',SelectedIndex=-1,IsChecked=False))
        result=collect(obj,False)
        self.assertEqual(result['run_ft'],'unfinished'); self.assertEqual(result['joist_symbol_uid'],'')

    def test_following_blocking_persists_as_following_after_joist_changes(self):
        collect,node=function('rt_ui.py','collect',dict(api=Obj(text_type=str)))
        obj=Obj(footprint_polygon=None,simpson_sources={},block_symbol_is_default=True,
                hardware=[],levels=[],joists=[Obj(UniqueId='joist-new')],
                block_types=[Obj(UniqueId='blocking-old')],beams=[],posts=[],clips=[])
        names={n.attr for n in ast.walk(node) if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name) and n.value.id=='self' and n.attr[0].isupper()}
        names.update(n.value for n in ast.walk(node) if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value[:1].isupper() and n.value.isalnum())
        for name in names: setattr(obj,name,Obj(Text='0',SelectedItem='20',SelectedIndex=-1,IsChecked=False))
        obj.JoistType.SelectedIndex=obj.BlockingType.SelectedIndex=0
        obj.JoistWidth.Text='1.5'; obj.JoistDepth.Text='11.25'; obj.BlockDepth.Text='9.25'
        result=collect(obj,False)
        self.assertEqual(result['joist_symbol_uid'],'joist-new')
        self.assertEqual(result['block_symbol_uid'],'')
        self.assertEqual(result['block_depth_in'],'11.25')
        obj.block_symbol_is_default=False
        result=collect(obj,False)
        self.assertEqual(result['block_symbol_uid'],'blocking-old')
        self.assertEqual(result['block_depth_in'],'9.25')

    def test_framing_off_clears_dependent_hardware_and_supports(self):
        changed,node=function('rt_ui.py','options_changed',{})
        support,unused=function('rt_ui.py','support_changed',{})
        names={n.attr for n in ast.walk(node) if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name) and n.value.id=='self' and n.attr[0].isupper()}
        names.update(n.value for n in ast.walk(node) if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value[:1].isupper() and n.value.isalnum())
        obj=Obj(initializing=False,block_symbol_is_default=True)
        for name in names: setattr(obj,name,Obj(IsChecked=True,SelectedIndex=3,SelectedItem='Loaded family',IsEnabled=True))
        for name in ('BeamType','BeamWidth','BeamDepth','BeamNearSetback','BeamFarSetback',
                     'PostType','PostWidth','PostDepth','PostHeight','PostEndSetback','PostSpacing'):
            setattr(obj,name,Obj(IsEnabled=True))
        obj.support_changed=lambda sender,args:support(obj,sender,args)
        obj.BuildFraming.IsChecked=False
        changed(obj,None,None)
        self.assertFalse(obj.BuildClips.IsChecked); self.assertFalse(obj.BuildSupports.IsChecked)
        self.assertFalse(obj.BeamType.IsEnabled); self.assertFalse(obj.HurricaneType.IsEnabled)
        self.assertEqual(obj.HangerType.SelectedIndex,0); self.assertEqual(obj.DoubleHangerType.SelectedIndex,0)
        self.assertFalse(obj.BlockingType.IsEnabled)

    def test_typed_options_keep_invalid_inputs_open_then_accept_valid_values(self):
        collect,unused=function('rt_forms.py','collect',{})
        checked,unused=function('rt_forms.py','checked',dict(text_type=str))
        accept,unused=function('rt_forms.py','accept',{})
        obj=Obj(inputs=dict(size=('number',Obj(Text='unfinished'),None),
                            type=('choice',Obj(SelectedIndex=1),[('First','uid-one'),('Second','uid-two')]),
                            edges=('checklist',None,[(Obj(IsChecked=False),0),(Obj(IsChecked=True),2)])),
                Summary=Obj(Text=''),Status=Obj(Text=''),result=None,closed=False)
        def validate(values):
            values['size']=float(values['size'])
            return values
        obj.validator=validate; obj.describe=lambda values:'Width '+str(values['size'])
        obj.collect=lambda:collect(obj); obj.checked=lambda:checked(obj); obj.Close=lambda:setattr(obj,'closed',True)
        accept(obj,None,None)
        self.assertFalse(obj.closed); self.assertIsNone(obj.result); self.assertTrue(obj.Status.Text)
        obj.inputs['size'][1].Text='3.5'
        accept(obj,None,None)
        self.assertTrue(obj.closed); self.assertEqual(obj.result,dict(size=3.5,type='uid-two',edges=[2]))
        self.assertEqual(obj.Status.Text,'')

    def test_regular_layout_reuses_the_two_stagger_patterns(self):
        original=rt_layout.joint_stations
        with patch.object(rt_layout,'joint_stations',wraps=original) as calls:
            result=rt_layout.plan(dict(rt_layout.DEFAULTS,run_ft=42,span_ft=40))
        self.assertEqual(calls.call_count,2)
        self.assertTrue(all(b['length_ft']<=20+1.e-7 for b in result['boards']))
        self.assertGreater(len(result['rows']),50)

    def test_schematic_clips_group_under_one_type_without_per_instance_type_queries(self):
        elements={uid:Obj(Name='Unique '+uid,Id=Obj(Value=i+1),GetMaterialIds=lambda unused:[]) for i,uid in enumerate(('one','two'))}
        scope=dict(api=Obj(axes=lambda *args:None,read_stamp=lambda unused:{},id_value=lambda eid:eid.Value),owned_registered=lambda *args:True)
        measure,node=function('rt_materials.py','measure',scope)
        parent=dict(anchor={},settings=dict(name='Deck',clip_mode='Schematic solids'))
        record=dict(items=[dict(unique_id=uid,item=dict(role='CLIP')) for uid in elements])
        rows,volumes,warnings,cuts=measure(Obj(GetElement=elements.get),parent,record,set())
        self.assertEqual(len({r['type_name'] for r in rows}),1); self.assertEqual(len(rows),2)

    def test_manually_rotated_board_is_excluded_from_stock_estimate_with_warning(self):
        element=Obj(Name='Board',Id=Obj(Value=1),GetMaterialIds=lambda unused:[])
        points=[Vector(x,y,z) for x in (0,12) for y in (0,5.5/12) for z in (0,.94/12)]
        scope=dict(DB=Obj(XYZ=Vector),api=Obj(axes=lambda *args:(Vector(0,0,0),Vector(1,0,0),Vector(0,1,0)),
                   read_stamp=lambda unused:{},id_value=lambda eid:eid.Value,vertices=lambda unused:points),owned_registered=lambda *args:True)
        measure,node=function('rt_materials.py','measure',scope)
        parent=dict(anchor={},settings=dict(name='Deck',board_thickness_in=.94,board_width_in=5.5))
        record=dict(items=[dict(unique_id='board',item=dict(role='BOARD',axis='B',width_in=5.5))])
        rows,volumes,warnings,cuts=measure(Obj(GetElement=lambda uid:element),parent,record,set())
        self.assertFalse(rows[0]['stock_eligible']); self.assertFalse(cuts)
        self.assertIn('orientation/width changed',warnings[0]); self.assertFalse(grouped_stock(rows,20))


if __name__=='__main__': unittest.main()
