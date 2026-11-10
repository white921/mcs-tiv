"""Avoid a millimetre deadband when replanning at the paper's 0.1 s interval."""
import os


def position(value):
    if os.environ.get("MCS_TIV_IMPLEMENTATION", "thesis") == "legacy-local":
        return round(value, 3)
    return float(value)
