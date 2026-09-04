from __future__ import annotations


def should_use_compact_layout(window_width: int, screen_height: int, logical_dpi: float) -> bool:
    """Choose laptop/HiDPI layout from Qt logical geometry, not physical pixels."""
    return window_width < 1420 or screen_height < 900 or logical_dpi > 110.0
