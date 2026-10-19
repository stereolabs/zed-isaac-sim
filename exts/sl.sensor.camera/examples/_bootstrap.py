# SPDX-FileCopyrightText: Copyright (c) 2024 Stereolabs. All rights reserved.
# SPDX-License-Identifier: MIT
"""Make the ``sl.sensor.camera`` packages importable from the example scripts.

These examples live inside an extension but run under the slim Isaac Lab app (or Isaac Sim)
where the Kit extensions are not auto-enabled, so the packages are not on ``sys.path`` by
default. Importing this module walks up from its own location to the ``exts/`` folder and
inserts every extension root under it that ships an ``sl/`` tree, so an example can import
``sl.sensor.camera`` and any subpackage a sibling extension contributes (e.g. ``.demo``).

Depth-independent: any example, at any nesting under ``examples/``, gets the same result -
nothing hard-codes how many directories up the extension root is.

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
    """Return the extension root above ``start`` (the dir holding ``config/extension.toml``)."""
    d = os.path.abspath(start)
    while not os.path.isfile(os.path.join(d, "config", "extension.toml")):
        parent = os.path.dirname(d)
        if parent == d:
            raise RuntimeError("extension root not found above examples/")
        d = parent
    return d


def _register_ext_roots(start: str) -> None:
    """Put every sibling extension that ships an ``sl/`` tree on ``sys.path``."""
    exts_dir = os.path.dirname(_ext_root(start))
    for name in sorted(os.listdir(exts_dir)):
        root = os.path.join(exts_dir, name)
        if os.path.isdir(os.path.join(root, "sl")) and root not in sys.path:
            sys.path.insert(0, root)


_register_ext_roots(__file__)
