# SPDX-FileCopyrightText: Copyright (c) 2024 Stereolabs. All rights reserved.
# SPDX-License-Identifier: MIT
"""GUI-only helpers for the sl.sensor.camera extension.

Import this package lazily and guard against ImportError: it pulls in omni.ui /
omni.kit.menu widgets that are unavailable in headless sessions (Isaac Lab,
--no-window), where the streaming extension must still load.
"""

from .lens_panel import ZedLensPanel  # noqa: F401
