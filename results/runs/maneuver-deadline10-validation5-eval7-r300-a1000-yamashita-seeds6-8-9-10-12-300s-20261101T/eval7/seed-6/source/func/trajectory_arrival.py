"""Shared trajectory arrival-time helpers.

This module is intentionally independent of TraCI and the negotiation
implementation so both the Yamashita TIV and the active proposal use exactly
the same conflict-point arrival definition.
"""
from __future__ import annotations

import math


def arrival_delay(path, point, now):
    """Return seconds until the nearest conflict-point sample.

    A trajectory whose finite horizon settles away from the conflict point is
    treated as unable to reach it and returns ``math.inf``.
    """
    indices = [i for i, moment in enumerate(path.t)
               if moment >= now - 1e-6]
    if not indices:
        return math.inf
    distances = [(path.x[i] - point[0]) ** 2 +
                 (path.y[i] - point[1]) ** 2 for i in indices]
    nearest = min(range(len(indices)), key=distances.__getitem__)
    index = indices[nearest]
    if distances[nearest] > .9 ** 2 and all(
        abs(path.x[k] - path.x[index]) < 1e-5 and
        abs(path.y[k] - path.y[index]) < 1e-5 for k in indices[nearest:]
    ):
        return math.inf
    return max(0.0, float(path.t[index]) - now)
