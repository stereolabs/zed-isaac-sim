# SPDX-FileCopyrightText: Copyright (c) 2024 Stereolabs. All rights reserved.
# SPDX-License-Identifier: MIT
"""ZED camera extension package.

Inside Isaac Sim the extension manager imports this package and finds
:class:`SlSensorCameraExtension` (streaming OGN nodes, ZED depth capture).

The package is also importable without a Kit app (e.g. Isaac Lab standalone
scripts, unit tests): the Kit-bound import below fails and only the
Kit-free modules remain available - ``utils`` (camera specs, prim paths)
and ``isaaclab_utils`` (Isaac Lab script helpers).

NOTE: if you need the streaming nodes, enable the extension before importing
this package. Importing it first in utilities-only mode caches the module
without the extension class, and a later enable would find no IExt subclass.
"""

try:
    from .extension import SlSensorCameraExtension  # full Kit app (Isaac Sim)
except ImportError as _exc:
    # Utilities-only mode: Kit extensions unavailable (Isaac Lab standalone,
    # pure-python tests). utils / isaaclab_utils stay importable.
    import logging

    logging.getLogger(__name__).info(
        "sl.sensor.camera imported in utilities-only mode (no Kit): %s", _exc
    )
    SlSensorCameraExtension = None
