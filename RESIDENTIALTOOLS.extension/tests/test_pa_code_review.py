"""Measured geometry and basic PA inputs; not structural capacity verification."""
import math
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lib'))
import rt_code_review as code
from rt_layout import DEFAULTS,plan
from rt_accessory_layout import straight_stair


class PACodeReviewTests(unittest.TestCase):
    def test_two_beam_measurements_survive_decking_coordinate_rotation(self):
        for angle in (0,30,45):
            result=code.review(plan(dict(DEFAULTS,supports_enabled=True,board_angle_deg=angle)))
            self.assertTrue(all(abs(j['beam_center_span_ft']-8)<1.e-7 for j in result['joists']))
            self.assertTrue(all(abs(span-5.5)<1.e-7 for b in result['beams'] for span in b['post_center_spans_ft']))
            self.assertIn('CAPACITY NOT CHECKED',result['status'])
            self.assertEqual(result['post_heights_ft'],[6]*6)

    def test_missing_beams_does_not_report_a_verified_span(self):
        result=code.review(plan(DEFAULTS))
        self.assertTrue(all('beam_center_span_ft' not in j for j in result['joists']))
        self.assertFalse(result['beams']); self.assertIn('Deferred',result['house_connections'])

    def test_basic_pa_stair_dimensions_boundaries_and_invalid_inputs(self):
        code.validate_stair_dimensions(straight_stair(8.25*12/12,3,12,9))
        for height,width,risers,tread in ((9,3,12,11),(7,2.99,12,11),(7,3,12,8.99)):
            with self.assertRaises(ValueError): code.validate_stair_dimensions(straight_stair(height,width,risers,tread))


if __name__=='__main__': unittest.main()
