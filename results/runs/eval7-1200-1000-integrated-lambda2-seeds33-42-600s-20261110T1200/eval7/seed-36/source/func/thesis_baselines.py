"""Shared negotiation rules for the thesis baseline methods."""


STRAIGHT_ROUTES = frozenset({"LR", "RL", "BT", "TB"})


def act_utility(route, priority_approaches=("L", "R")):
    """Return the ACT utility used by the accepting vehicle.

    The thesis gives priority to a vehicle that is on the priority road or
    travels straight.  Horizontal approaches (A/C, represented by L/R route
    prefixes) are the priority road in the intersection scenarios.
    """
    if route in STRAIGHT_ROUTES or route[:1] in priority_approaches:
        return 0.0
    return 1.0


def accepts_utility(alpha, utility, threshold=0.0):
    """Apply the acceptance boundary stated for each baseline method.

    SPD accepts a speed-change rate *at most* 20 or 40 percent, so equality
    at its zero-utility boundary must be accepted.  The other legacy utility
    methods retain their strictly-positive boundary.
    """
    if int(alpha) in (3, 4):
        return utility >= threshold
    return utility > threshold
