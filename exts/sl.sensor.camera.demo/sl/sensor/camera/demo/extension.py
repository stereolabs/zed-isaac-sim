"""Registers the Stereolabs ZED demos in the Isaac Examples browser.

Three turnkey scenes, each streaming a ZED X to the ZED SDK: a Franka pick-place cell
(`pickplace.py`), a Unitree H1 humanoid (`humanoid.py`), and an Idealworks iw.hub AMR (`amr.py`).
"""
from __future__ import annotations

import omni.ext

from isaacsim.examples.browser import get_instance as get_browser_instance
from .pickplace import ZedPickPlaceDemo
from .humanoid import ZedHumanoidDemo
from .amr import ZedAmrDemo

EXAMPLE_NAME = "ZED Pick-Place Integration"
HUMANOID_NAME = "ZED Humanoid Integration"
AMR_NAME = "ZED AMR Integration"
CATEGORY = "Stereolabs"


class ZedDemoExtension(omni.ext.IExt):
    """Registers the ZED demos (Franka pick-place + H1 humanoid + iw.hub AMR) in the Isaac Examples browser."""

    def on_startup(self, ext_id: str) -> None:
        self._demo = ZedPickPlaceDemo()
        get_browser_instance().register_example(
            name=EXAMPLE_NAME, category=CATEGORY, ui_hook=self._demo.build_ui)
        self._humanoid = ZedHumanoidDemo()
        get_browser_instance().register_example(
            name=HUMANOID_NAME, category=CATEGORY, ui_hook=self._humanoid.build_ui)
        self._amr = ZedAmrDemo()
        get_browser_instance().register_example(
            name=AMR_NAME, category=CATEGORY, ui_hook=self._amr.build_ui)
        # the demos are mutually exclusive (each rebuilds the stage): loading one must stop the
        # others, else a stale physics-step subscription fires against removed prims ("Instance is
        # not valid"). Each demo stops its siblings at the top of its load.
        demos = [self._demo, self._humanoid, self._amr]
        for d in demos:
            d._siblings = [x for x in demos if x is not d]

    def on_shutdown(self) -> None:
        for demo in (getattr(self, "_demo", None), getattr(self, "_humanoid", None),
                     getattr(self, "_amr", None)):
            try:
                if demo is not None: demo.stop()
            except Exception:
                pass
        get_browser_instance().deregister_example(name=EXAMPLE_NAME, category=CATEGORY)
        get_browser_instance().deregister_example(name=HUMANOID_NAME, category=CATEGORY)
        get_browser_instance().deregister_example(name=AMR_NAME, category=CATEGORY)
