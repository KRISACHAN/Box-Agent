"""Compatibility import for the renamed read-only image inspection tool."""

from box_agent.tools.image_inspection_tool import (
    _IMAGE_INSPECTION_TIMEOUT,
    _MAX_LONG_EDGE_PX,
    ImageInspectionTool,
)

VisionReviewTool = ImageInspectionTool

__all__ = [
    "ImageInspectionTool",
    "VisionReviewTool",
    "_IMAGE_INSPECTION_TIMEOUT",
    "_MAX_LONG_EDGE_PX",
]
