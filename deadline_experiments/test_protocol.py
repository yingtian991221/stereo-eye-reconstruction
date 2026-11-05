"""CPU checks for metric overflow, causal policy and fixed-clock plans."""
import math
import tempfile
import unittest
from pathlib import Path
import numpy as np
from prepare import select


class ProtocolTests(unittest.TestCase):
    def test_float_error(self):
        a=np.array([0,255],np.uint8);b=np.array([255,0],np.uint8)
        mse=np.mean((a.astype(np.float64)-b.astype(np.float64))**2)
        self.assertEqual(mse,65025)
        self.assertEqual(10*math.log10(65025/mse),0)
    def test_half_is_eligible_and_not_size_ranked(self):
        e=[dict(config='Full',cost_ms=8,whole_score=22),dict(config='Half',cost_ms=3,whole_score=24),dict(config='FOV',cost_ms=5,whole_score=23)]
        self.assertEqual(select(e,10),'Half')
        self.assertEqual(select(e,2),'Half')
    def test_selector_has_no_future_or_actual_time_argument(self):
        import inspect
        self.assertEqual(list(inspect.signature(select).parameters),['estimates','budget','quality'])
    def test_deadlines_do_not_follow_release(self):
        deadline=[i*1000/90+19 for i in range(8)]
        for budget in [2,5,10]:
            release=[d-budget for d in deadline]
            self.assertEqual(deadline[5],5*1000/90+19)
            self.assertAlmostEqual(release[5]+budget,deadline[5])
    def test_optimized_regions_match_pixel_mask(self):
        rng=np.random.default_rng(20261104);h,w=540,960
        a=rng.integers(0,256,(h,w,3),dtype=np.uint8)
        b=rng.integers(0,256,(h,w,3),dtype=np.uint8)
        e=(a.astype(np.float64)-b.astype(np.float64))**2
        x0,x1,y0,y1=w*3//8,w*5//8,h*3//8,h*5//8
        yy,xx=np.mgrid[:h,:w]
        mask=(xx>=x0-4)&(xx<x1+4)&(yy>=y0-4)&(yy<y1+4)
        mask&=~((xx>=x0+4)&(xx<x1-4)&(yy>=y0+4)&(yy<y1-4))
        total=e[y0-4:y1+4,x0-4:x1+4].sum()-e[y0+4:y1-4,x0+4:x1-4].sum()
        count=3*((x1-x0+8)*(y1-y0+8)-(x1-x0-8)*(y1-y0-8))
        self.assertEqual(total/count,e[mask].mean())


if __name__=='__main__': unittest.main()
