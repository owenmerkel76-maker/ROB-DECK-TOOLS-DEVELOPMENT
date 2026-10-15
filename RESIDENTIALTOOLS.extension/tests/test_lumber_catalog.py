"""Local section tests; these do not validate Revit RFAs."""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'RESIDENTIALTOOLS.tab' / 'Framing.panel' / 'Lumber Library.pushbutton'
sys.path.insert(0, str(BUNDLE / 'lib'))
from lumber_catalog import PROTOTYPES, SUPPORTED_CATEGORIES, area_inches, rectangles


class CatalogTests(unittest.TestCase):
    def test_actual_dimensional_lumber_and_separate_identities(self):
        untreated, treated = PROTOTYPES[:2]
        for section in (untreated, treated):
            self.assertEqual((section['width'], section['depth']), (1.5, 9.25))
            self.assertEqual(area_inches(section), 13.875)
        self.assertNotEqual(untreated['family'], treated['family'])
        self.assertNotEqual(untreated['material_id'], treated['material_id'])
        self.assertNotEqual(untreated['type_name'], treated['type_name'])

    def test_i_section_voids_web_and_flange_materials(self):
        section = PROTOTYPES[2]
        pieces = rectangles(section)
        self.assertEqual(len(pieces), 3)
        self.assertEqual([r[4] for r in pieces], [0, 0, 1])
        self.assertAlmostEqual(area_inches(section), 10.828125)
        self.assertLess(area_inches(section), section['width'] * section['depth'])
        self.assertEqual(pieces[2][2] - pieces[2][0], 0.375)
        self.assertEqual(pieces[2][3] - pieces[2][1], 8.875)
        for i, a in enumerate(pieces):
            for b in pieces[i + 1:]:
                overlap_y = max(0, min(a[2], b[2]) - max(a[0], b[0]))
                overlap_z = max(0, min(a[3], b[3]) - max(a[1], b[1]))
                self.assertEqual(overlap_y * overlap_z, 0)

    def test_invalid_profiles_are_rejected(self):
        for change in ({'width': 0}, {'flange_thickness': 6},
                       {'web_thickness': 3}, {'profile': 'c_section'}):
            section = dict(PROTOTYPES[2])
            section.update(change)
            with self.assertRaises(ValueError):
                rectangles(section)

    def test_registry_does_not_misrepresent_implemented_sections(self):
        self.assertEqual(len(SUPPORTED_CATEGORIES), 7)
        self.assertEqual(len(PROTOTYPES), 3)
        self.assertEqual(len(set(s['family'] for s in PROTOTYPES)), 3)

    def test_large_element_ids_are_preserved(self):
        # Execute just the pure helper without pretending to emulate Revit.
        source = (BUNDLE / 'lib' / 'lumber_generator.py').read_text(encoding='utf-8')
        node = next(n for n in ast.parse(source).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'id_value')
        scope = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<id-helper>', 'exec'), scope)
        class LargeId:
            Value = 2 ** 40 + 123
            @property
            def IntegerValue(self):
                raise AssertionError('Deprecated 32-bit access')
        self.assertEqual(scope['id_value'](LargeId()), 2 ** 40 + 123)


if __name__ == '__main__':
    unittest.main()
