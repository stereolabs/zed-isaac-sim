"""Unit tests for the fisheye lookup textures in sl.sensor.camera.fisheye_lut (numpy only, no renderer)."""
import math
import os
import tempfile
from unittest import mock

import numpy as np
import omni.kit.test

from sl.sensor.camera import fisheye_lut

# ZED X One S fisheye (spec table), and a small image to keep the tests fast
_K = [0.07, 0.0061, -0.0018, -0.00037]
_W, _H = 96, 60
_FX, _FY, _CX, _CY = 23.0, 23.5, 47.3, 29.8


def _project(directions):
    """OpenCV fisheye projection of USD camera-frame directions (x right, y up, -z forward) to pixels."""
    x, y, z = directions[..., 0], directions[..., 1], directions[..., 2]
    sin_theta = np.hypot(x, y)
    theta = np.arctan2(sin_theta, -z)
    t2 = theta * theta
    scale = theta * (1 + _K[0] * t2 + _K[1] * t2**2 + _K[2] * t2**3 + _K[3] * t2**4) / sin_theta
    return _CX + _FX * x * scale, _CY - _FY * y * scale


# NOTE: the class must be named TestOgn - ogn/tests/__init__.py auto-imports test
# modules via omni.graph.tools and only registers each module's `TestOgn` attribute.
class TestOgn(omni.kit.test.AsyncTestCase):

    def test_lens_reach_ends_where_its_polynomial_turns_over(self):
        self.assertAlmostEqual(math.degrees(fisheye_lut.theta_max(_K)), 121.98, places=1)
        self.assertEqual(fisheye_lut.theta_max([0.0, 0.0, 0.0, 0.0]), math.pi)

    def test_each_pixel_direction_projects_back_onto_that_pixel(self):
        directions = fisheye_lut.ray_directions(_W, _H, _FX, _FY, _CX, _CY, _K)
        self.assertEqual(directions.shape, (_H, _W, 3))
        self.assertTrue(np.allclose(np.linalg.norm(directions, axis=-1), 1.0, atol=1e-5))

        rows, cols = np.mgrid[0:_H, 0:_W]
        inside = directions[..., 2] < 0.999   # skip the pixels past the lens
        u, v = _project(directions[inside].astype(np.float64))
        self.assertLess(np.abs(u - cols[inside]).max(), 1e-2)
        self.assertLess(np.abs(v - rows[inside]).max(), 1e-2)

    def test_pixels_past_the_lens_point_straight_back(self):
        directions = fisheye_lut.ray_directions(_W, _H, _FX, _FY, _CX, _CY, _K)
        # the top-left corner's theta_d is 2.42 rad, past the 2.38 the lens reaches
        self.assertEqual(tuple(directions[0, 0]), (0.0, 0.0, 1.0))
        self.assertLess(directions[round(_CY), round(_CX), 2], -0.999)

    def test_optical_axis_lands_on_the_optical_center(self):
        # odd sizes put a texel on the middle of the octahedral square, which decodes to the axis
        width, height = _W + 1, _H + 1
        positions = fisheye_lut.ray_positions(width, height, _FX, _FY, _CX, _CY, _K)
        self.assertEqual(positions.shape, (height, width, 2))
        row, col = height // 2, width // 2
        # positions count from the corner of the first pixel, cx and cy from its center
        self.assertTrue(np.allclose(positions[row, col], ((_CX + 0.5) / width, (_CY + 0.5) / height), atol=1e-6))
        # +x is right and +y up in the octahedral frame; the image's y grows downward
        self.assertGreater(positions[row, col + 5, 0], positions[row, col, 0])
        self.assertLess(positions[row + 5, col, 1], positions[row, col, 1])
        # the corners of the square decode to the backward axis, out of the lens
        for corner_row, corner_col in ((0, 0), (0, -1), (-1, 0), (-1, -1)):
            self.assertEqual(tuple(positions[corner_row, corner_col]), (-1.0, -1.0))

    def test_textures_are_written_once_per_lens(self):
        with tempfile.TemporaryDirectory() as cache, mock.patch.object(fisheye_lut, "_CACHE_DIR", cache):
            paths = fisheye_lut.textures(_W, _H, _FX, _FY, _CX, _CY, _K)
            written = [os.stat(p).st_mtime_ns for p in paths]
            self.assertEqual(fisheye_lut.textures(_W, _H, _FX, _FY, _CX, _CY, _K), paths)
            self.assertEqual([os.stat(p).st_mtime_ns for p in paths], written)
            self.assertNotEqual(fisheye_lut.textures(_W, _H, _FX, _FY, _CX + 1.0, _CY, _K), paths)

            for path, channels in zip(paths, (3, 2)):
                with open(path, "rb") as f:
                    data = f.read()
                self.assertEqual(data[:4], b"\x76\x2f\x31\x01")
                # header, then one offset and one (y, size, pixels) block per row
                pixel_bytes = _H * (8 + 8 + channels * _W * 4)
                self.assertLess(len(data) - pixel_bytes, 512)
