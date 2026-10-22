"""Machine-readable conditions and reference values from thesis Chapter 5."""

from dataclasses import dataclass
from typing import Optional


METHOD_ALPHA = {
    "ALW": 1,
    "ACT": 2,
    "SPD20": 3,
    "SPD40": 4,
    "UTF": 5,
    "TIVte": 6,
    "TIVtep": 7,
}


@dataclass(frozen=True)
class Condition:
    inflows: tuple
    references: tuple


@dataclass(frozen=True)
class Evaluation:
    scenario: str
    bus_share: float
    route_mode: Optional[str]
    methods: tuple
    conditions: tuple
    default_seeds: tuple


EVALUATIONS = {
    "eval1": Evaluation(
        "junction/junction_three_agree.py",
        0.0,
        "eval1",
        ("ALW", "ACT", "SPD40", "UTF", "TIVte"),
        (
            Condition((660, 180, 660), (11.1658, 8.6829, 11.2717, 11.1541, 11.7161)),
            Condition((630, 240, 630), (9.5198, 7.7905, 10.2397, 10.1473, 11.0795)),
            Condition((600, 300, 600), (9.0798, 7.2777, 9.3689, 8.7589, 10.1818)),
            Condition((570, 360, 570), (7.4911, 6.2621, 8.0755, 8.1436, 9.2596)),
            Condition((540, 420, 540), (7.1264, 5.6751, 6.5737, 7.5179, 8.8924)),
        ),
        (1, 2, 3, 4, 5),
    ),
    "eval2": Evaluation(
        "junction/junction_three_agree.py",
        0.0,
        "random",
        ("ALW", "ACT", "SPD20", "UTF", "TIVte"),
        (
            Condition((400, 400, 400), (7.1926, 7.2162, 7.8629, 7.5538, 7.8222)),
            Condition((500, 500, 500), (4.0510, 5.6945, 6.5408, 5.6555, 7.2766)),
            Condition((600, 600, 600), (2.6919, 3.4965, 3.7923, 3.3530, 3.7233)),
        ),
        (1, 2, 3, 4, 5),
    ),
    "eval3": Evaluation(
        "junction/junction_three_agree.py",
        0.25,
        "random",
        ("ALW", "ACT", "SPD40", "UTF", "TIVte", "TIVtep"),
        (
            Condition((400, 400, 400), (6.6075, 6.6722, 7.3775, 6.8242, 7.3584, 7.4159)),
            Condition((500, 500, 500), (4.6017, 4.8419, 5.9591, 5.5058, 6.1898, 6.4955)),
            # Table 5.3 defines 600/600/600, but Chapter 5 has no result table.
            Condition((600, 600, 600), (None, None, None, None, None, None)),
        ),
        (1, 2, 3, 4, 5),
    ),
    "eval4": Evaluation(
        "junction/junction_four_agree.py",
        0.0,
        None,
        ("ALW", "ACT", "SPD40", "UTF", "TIVte"),
        (
            Condition((300, 300, 300, 300), (5.8631, 6.5145, 6.8127, 6.8077, 7.2485)),
            Condition((400, 400, 400, 400), (3.6997, 4.1850, 4.5090, 4.3336, 4.5560)),
        ),
        (1, 3, 5, 6, 7),
    ),
    "eval5": Evaluation(
        "junction/junction_four_agree.py",
        0.25,
        None,
        ("ALW", "ACT", "SPD20", "UTF", "TIVte", "TIVtep"),
        (Condition((300, 300, 300, 300), (5.3037, 5.6246, 5.5534, 5.8622, 6.2789, 6.4420)),),
        (1, 2, 3, 4, 5),
    ),
    "eval6": Evaluation(
        "merge/merge_agree2512.py",
        0.0,
        None,
        ("ALW", "ACT", "SPD40", "UTF", "TIVte"),
        (
            # Merge arguments are requesting first, accepting second.
            Condition((800, 1200), (4.0606, 3.9883, 4.2267, 4.5430, 4.4439)),
            Condition((1000, 1000), (4.1118, 3.7198, 3.8212, 4.3100, 4.8032)),
            Condition((1200, 800), (4.7338, 3.4712, 3.8368, 4.7447, 4.6601)),
        ),
        (1, 2, 3, 6, 8),
    ),
    "eval7": Evaluation(
        "merge/merge_agree2512.py",
        0.25,
        None,
        ("ALW", "ACT", "SPD40", "UTF", "TIVte", "TIVtep"),
        (Condition((1000, 1000), (4.2685, 3.3895, 3.6235, 4.3664, 4.2724, 4.2084)),),
        (1, 2, 3, 7, 11),
    ),
}
