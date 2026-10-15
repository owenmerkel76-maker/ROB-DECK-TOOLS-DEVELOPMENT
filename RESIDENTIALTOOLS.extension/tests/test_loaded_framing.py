import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lib'))
from rt_layout import DEFAULTS,settings,plan


def function(path, name, scope):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec'), scope)
    return scope[name]


def length(value, spec='length'):
    return SimpleNamespace(HasValue=True, StorageType='double', AsDouble=lambda: value / 12.0,
                           Definition=SimpleNamespace(GetDataType=lambda:
                               SimpleNamespace(Equals=lambda other: other == spec)))


class LoadedFramingTests(unittest.TestCase):
    def test_hardware_lookup_preserves_unbuildable_breaker_outline_and_build_still_blocks(self):
        values=dict(DEFAULTS,seam_border=True,footprint_polygon=[(0,2),(9,2),(9,0),(20,0),(20,12),(0,12)],
                    run_ft=20,span_ft=12,board_width_in=3,joist_symbol_uid='loaded-2x10')
        finish=function('lib/rt_ui.py','finish',dict(plan=plan,api=SimpleNamespace(text_type=str),Brushes=SimpleNamespace(Firebrick='red')))
        def window():
            obj=SimpleNamespace(result=None,closed=False,Status=SimpleNamespace(Text=''),Tabs=SimpleNamespace(SelectedIndex=2),
                                validate_simpson=lambda unused:None)
            obj.collect=lambda validate_layout=True:settings(values,validate_layout=validate_layout)
            obj.Close=lambda:setattr(obj,'closed',True)
            return obj
        lookup=window(); finish(lookup,'simpson_library')
        self.assertTrue(lookup.closed)
        self.assertEqual(lookup.result['action'],'simpson_library')
        self.assertTrue(lookup.result['settings']['seam_border'])
        self.assertEqual(lookup.result['settings']['joist_symbol_uid'],'loaded-2x10')
        self.assertEqual(lookup.result['settings']['joist_depth_in'],9.25)
        self.assertEqual(lookup.result['settings']['footprint_polygon'],values['footprint_polygon'])
        self.assertIsNone(lookup.result['planned'])
        build=window(); finish(build,'build')
        self.assertFalse(build.closed); self.assertIsNone(build.result)
        self.assertIn('greater than three joist widths',build.Status.Text)
        repick=window(); finish(repick,'repick'); self.assertTrue(repick.closed)

    def test_library_settings_do_not_require_enabled_deck_components(self):
        values=dict(DEFAULTS,boards_enabled=False,framing_enabled=False,clips_enabled=True,
                    joist_symbol_uid='loaded-2x10',hanger_symbol_uid='previous-hanger')
        self.assertEqual(settings(values,validate_layout=False)['joist_symbol_uid'],'loaded-2x10')
        with self.assertRaises(ValueError): plan(values)
    def test_post_section_does_not_mistake_overall_height_for_depth(self):
        db=SimpleNamespace(StorageType=SimpleNamespace(Double='double'),SpecTypeId=SimpleNamespace(Length='length'))
        dimensions=function('lib/rt_revit.py','post_dimensions',dict(DB=db))
        params=dict(Width=length(5.5),Height=length(120))
        self.assertEqual(dimensions(SimpleNamespace(LookupParameter=params.get)),dict(joist_width_in=5.5))
        params['Depth']=length(5.5)
        self.assertEqual(dimensions(SimpleNamespace(LookupParameter=params.get)),dict(joist_width_in=5.5,joist_depth_in=5.5))
    def test_standard_section_parameters_read_actual_lengths_only(self):
        db = SimpleNamespace(StorageType=SimpleNamespace(Double='double'),
                             SpecTypeId=SimpleNamespace(Length='length'))
        dimensions = function('lib/rt_revit.py', 'type_dimensions', dict(DB=db))
        params = dict(b=length(1.5), h=length(9.25), Width=length(24, 'number'))
        symbol = SimpleNamespace(LookupParameter=params.get)
        self.assertEqual(dimensions(symbol), dict(joist_width_in=1.5, joist_depth_in=9.25))
        params = dict(Width=length(24, 'number'), Depth=length(9.25))
        self.assertNotIn('joist_width_in', dimensions(SimpleNamespace(LookupParameter=params.get)))

    def test_unknown_loaded_family_uses_explicit_custom_mode(self):
        updater = function('lib/rt_ui.py', 'update_joist_identity',
                           dict(api=SimpleNamespace(type_category=lambda symbol: 'unknown')))
        window = SimpleNamespace(JoistType=SimpleNamespace(SelectedIndex=0), joists=[object()],
                                 Exposure=SimpleNamespace(SelectedIndex=0),
                                 JoistIdentity=SimpleNamespace(Text=''))
        updater(window)
        self.assertEqual(window.Exposure.SelectedIndex, 2)
        self.assertIn('Verify', window.JoistIdentity.Text)

    def test_known_untreated_family_does_not_silently_become_treated(self):
        updater = function('lib/rt_ui.py', 'update_joist_identity',
                           dict(api=SimpleNamespace(type_category=lambda symbol: 'untreated_dimensional')))
        window = SimpleNamespace(JoistType=SimpleNamespace(SelectedIndex=0), joists=[object()],
                                 Exposure=SimpleNamespace(SelectedIndex=0),
                                 JoistIdentity=SimpleNamespace(Text=''))
        updater(window)
        self.assertEqual(window.Exposure.SelectedIndex, 0)
        self.assertIn('untreated', window.JoistIdentity.Text)


if __name__ == '__main__':
    unittest.main()
