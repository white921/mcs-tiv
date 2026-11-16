"""Pure scenario helpers for the thesis evaluation routes."""


T_JUNCTION_RANDOM_ROUTES = {
    "left": ("LR", "LB"),
    "bottom": ("BR", "BL"),
    "right": ("RL", "RB"),
}

T_JUNCTION_EVAL1_ROUTES = {
    "left": ("LR",),
    "bottom": ("BR", "BL"),
    "right": ("RL",),
}


def choose_t_junction_route(approach, route_mode, chooser):
    """Choose a T-junction route under Eval.1 or unrestricted conditions."""
    if route_mode == "eval1":
        routes = T_JUNCTION_EVAL1_ROUTES[approach]
    elif route_mode == "random":
        routes = T_JUNCTION_RANDOM_ROUTES[approach]
    else:
        raise ValueError(f"unknown T-junction route mode: {route_mode}")
    if len(routes) == 1:
        return routes[0]
    return chooser(routes)
