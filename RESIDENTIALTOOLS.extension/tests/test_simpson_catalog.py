import ast
import hashlib
import io
import json
import os
import sys
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
import rt_simpson_catalog as catalog


class SimpsonCatalogTests(unittest.TestCase):
    def test_cache_requires_matching_vendor_url_header_and_checksum(self):
        tree = ast.parse((ROOT / 'lib' / 'rt_simpson.py').read_text(encoding='utf-8'))
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name in ('checksum', 'cached_valid')]
        entry = catalog.MODELS[3]
        path = 'cached-model.rfa'
        files = {path: b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'fixture'}
        def fake_open(name, mode, **kwargs):
            value = files[name]
            return io.BytesIO(value) if 'b' in mode else io.StringIO(value)
        from types import SimpleNamespace
        scope = dict(os=SimpleNamespace(path=SimpleNamespace(isfile=lambda name: name in files)),
                     io=SimpleNamespace(open=fake_open), json=json, hashlib=hashlib, catalog=catalog)
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<simpson-cache>', 'exec'), scope)
        files[path+'.json'] = json.dumps(dict(url=entry['url'], sha256=scope['checksum'](path)))
        self.assertTrue(scope['cached_valid'](path, entry))
        files[path] += b'changed'
        self.assertFalse(scope['cached_valid'](path, entry))
        files[path+'.json'] = json.dumps(dict(url='https://example.com/wrong.rfa',
                                              sha256=scope['checksum'](path)))
        self.assertFalse(scope['cached_valid'](path, entry))

    def test_exact_actual_section_matches_single_sawn_hanger(self):
        for depth, model in ((3.5, 'LUS24'), (5.5, 'LUS26'), (7.25, 'LUS28'), (9.25, 'LUS210')):
            entries = catalog.candidates('hanger', 1.5, depth, 'pressure_treated')
            self.assertEqual([entry['model'] for entry in entries], [model])
        self.assertEqual(catalog.candidates('hanger', 3, 9.25, 'pressure_treated'), [])
        self.assertEqual(catalog.candidates('hanger', 1.5, 11.25, 'pressure_treated'), [])

    def test_engineered_or_unknown_material_never_gets_sawn_hanger_by_size_alone(self):
        for kind in ('wood_i_joist', 'LVL', 'cold_formed_steel_c_joist', 'unknown'):
            self.assertEqual(catalog.candidates('hanger', 1.5, 9.25, kind), [])
        self.assertEqual(catalog.candidates('hanger', 1.5, 9.25, 'unknown', True)[0]['model'], 'LUS210')
        self.assertEqual(catalog.candidates('hanger', 1.5, 9.25, 'LVL', True), [])

    def test_download_index_has_exact_vendor_urls_and_rejects_unsafe_content(self):
        for entry in catalog.MODELS:
            self.assertTrue(catalog.filename(entry).lower().endswith('.rfa'))
        with self.assertRaises(ValueError):
            catalog.filename(dict(url='https://example.com/family.rfa'))
        with self.assertRaises(ValueError):
            catalog.validate_rfa_header(b'<html>no')
        catalog.validate_rfa_header(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1')

    def test_hanger_lookup_must_be_repeated_after_size_or_type_changes(self):
        values = dict(joist_width_in=1.5, joist_depth_in=9.25, joist_symbol_uid='joist',
                      hanger_symbol_uid='hanger', simpson_sources=dict(hanger=dict(
                          unique_id='hanger', width_in=1.5, depth_in=9.25, joist_symbol_uid='joist')))
        catalog.validate_selections(values, 'unknown')
        for changes in (dict(joist_depth_in=7.25), dict(joist_symbol_uid='different')):
            with self.assertRaisesRegex(ValueError, 'joist changed'):
                catalog.validate_selections(dict(values, **changes))
        with self.assertRaisesRegex(ValueError, 'joist changed'):
            catalog.validate_selections(values, 'wood_i_joist')
        catalog.validate_selections(dict(values, hanger_symbol_uid='manual-type'))

    def test_online_finder_uses_verified_revit_3d_filters(self):
        query = parse_qs(urlparse(catalog.finder_url('LUS210')).query)
        self.assertEqual(query['keywordFilter'], ['LUS210'])
        self.assertEqual(query['v'], [':relevance:drawingFileType:Revit:drawingDimension:3D'])

    def test_double_2x10_lookup_uses_assembly_width_and_preserves_single_index(self):
        self.assertEqual(catalog.candidates('double_hanger', 3, 9.25, 'pressure_treated')[0]['model'], 'LUS210-2')
        self.assertEqual(catalog.candidates('double_hanger', 1.5, 9.25, 'pressure_treated'), [])
        self.assertEqual(catalog.candidates('double_hanger', 3, 9.25, 'LVL', True), [])
        values = dict(joist_width_in=1.5, joist_depth_in=9.25, joist_symbol_uid='joist',
                      double_hanger_symbol_uid='double', simpson_sources=dict(double_hanger=dict(
                          unique_id='double', width_in=3, depth_in=9.25, joist_symbol_uid='joist')))
        catalog.validate_selections(values, 'pressure_treated')
        with self.assertRaisesRegex(ValueError, 'joist changed'):
            catalog.validate_selections(dict(values, joist_width_in=1.75))
        with self.assertRaisesRegex(ValueError, 'wrong connection'):
            catalog.validate_selections(dict(values, hanger_symbol_uid='double'))


if __name__ == '__main__':
    unittest.main()
