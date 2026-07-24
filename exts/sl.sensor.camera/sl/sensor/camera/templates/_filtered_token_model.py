"""Combo-box model for filtered token inputs of the ZED OmniGraph nodes.

The stock OmniGraph token model shows every value in the attribute's authored
``allowedTokens`` metadata. This subclass instead shows only a restricted list
(e.g. the resolutions or lens types supported by the currently selected camera
model), by overriding ``_get_allowed_tokens``.
"""
from typing import List

from omni.graph.ui import OmniGraphTfTokenAttributeModel
from pxr import Sdf, Usd


class FilteredTokenModel(OmniGraphTfTokenAttributeModel):
    """Token model whose allowed values are restricted to ``allowed_tokens``.

    A fresh instance is created every time the property panel rebuilds, so the
    allowed list reflects the camera model selected at build time.
    """

    def __init__(
        self,
        stage: Usd.Stage,
        attribute_paths: List[Sdf.Path],
        self_refresh: bool,
        metadata: dict,
        allowed_tokens: List[str],
    ):
        # Must be set before super().__init__, which calls _get_allowed_tokens.
        self._allowed = list(allowed_tokens)
        super().__init__(stage, attribute_paths, self_refresh, metadata)

    def _get_allowed_tokens(self, attr):
        return self._allowed
