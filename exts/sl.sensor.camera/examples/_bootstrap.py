# SPDX-FileCopyrightText: Copyright (c) 2024 Stereolabs. All rights reserved.
# SPDX-License-Identifier: MIT
"""Make the ``sl.sensor.camera`` package importable from the example scripts.

These examples live inside the extension but run under the slim Isaac Lab app
(or Isaac Sim) where the Kit extension is not auto-enabled, so the package is
not on ``sys.path`` by default. Importing this module walks up from its own
location until it finds the extension root (the directory holding
``sl/sensor/camera/__init__.py``) and inserts it at ``sys.path[0]``.

Depth-independent: any example, at any nesting under ``examples/``, gets the
same result - nothing hard-codes how many directories up the extension root is.

Usage (identical stanza in every example script):

    import os, sys
    _d = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isfile(os.path.join(_d, "_bootstrap.py")):
        _d = os.path.dirname(_d)
    sys.path.insert(0, _d)
    import _bootstrap  # noqa: E402,F401
"""

import os
import sys


def _ext_root(start: str) -> str:
    """Return the extension root above ``start`` (dir with sl/sensor/camera/__init__.py)."""
    d = os.path.abspath(start)
    while not os.path.isfile(os.path.join(d, "sl", "sensor", "camera", "__init__.py")):
        parent = os.path.dirname(d)
        if parent == d:
            raise RuntimeError("sl.sensor.camera extension root not found above examples/")
        d = parent
    return d


sys.path.insert(0, _ext_root(__file__))
