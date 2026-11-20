#!/usr/bin/env python3
"""Plot the completed 1000/1000, 600-second fine lambda sweep."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import shutil
import subprocess


WIDTH, HEIGHT = 1500, 1100
LEFT, RIGHT = 145, 1440
REUSED = {0.50, 0.60, 0.70}


def text(
    value: str,
    x: float,
    y: float,
    *,
    size: int = 22,
    anchor: str = "start",
    weight: int = 400,
    fill: str = "#2F3742",
    rotate: int | None = None,
) -> str:
    transform = f' transform="rotate({rotate} {x:.1f} {y:.1f})"' if rotate else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" '
        f'text-anchor="{anchor}" font-weight="{weight}" fill="{fill}"{transform}>'
        f"{html.escape(value)}</text>"
    )


def x_pos(value: float) -> float:
    return LEFT + (value - 0.50) / 0.20 * (RIGHT - LEFT)


def y_pos(value: float, low: float, high: float, top: float, bottom: float) -> float:
    return bottom - (value - low) / (high - low) * (bottom - top)


def polyline(points: list[tuple[float, float]], color: str) -> str:
    encoded = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return (
        f'<polyline points="{encoded}" fill="none" stroke="{color}" '
        'stroke-width="4" stroke-linejoin="round" stroke-linecap="round"/>'
    )


def axes(
    parts: list[str],
    *,
    top: float,
    bottom: float,
    y_ticks: list[float],
    y_low: float,
    y_high: float,
    x_labels: bool,
) -> None:
    parts.append(
        f'<line x1="{LEFT}" y1="{bottom}" x2="{RIGHT}" y2="{bottom}" '
        'stroke="#6B7280" stroke-width="2"/>'
    )
    parts.append(
        f'<line x1="{LEFT}" y1="{top}" x2="{LEFT}" y2="{bottom}" '
        'stroke="#6B7280" stroke-width="2"/>'
    )
    for tick in y_ticks:
        y = y_pos(tick, y_low, y_high, top, bottom)
        parts.append(
            f'<line x1="{LEFT}" y1="{y:.1f}" x2="{RIGHT}" y2="{y:.1f}" '
            'stroke="#D7DCE2" stroke-width="1.5"/>'
        )
        parts.append(text(f"{tick:g}", LEFT - 18, y + 7, anchor="end", fill="#5B6573"))
    for index in range(9):
        value = 0.50 + index * 0.025
        x = x_pos(value)
        parts.append(
            f'<line x1="{x:.1f}" y1="{bottom}" x2="{x:.1f}" y2="{bottom + 8}" '
            'stroke="#6B7280" stroke-width="2"/>'
        )
        if x_labels:
            parts.append(text(f"{value:.3f}".rstrip("0"), x, bottom + 35, size=18, anchor="middle", fill="#5B6573"))


def render(summary: dict[str, object]) -> str:
    aggregates = {
        float(key): value for key, value in summary["aggregates"].items()  # type: ignore[union-attr]
    }
    lambdas = sorted(aggregates)
    best = float(summary["best_lambda_by_all_speed"])
    blue, green, purple, red, orange = "#1769AA", "#00796B", "#7B1FA2", "#C62828", "#D46B08"
    top_a, bottom_a = 125.0, 475.0
    top_b, bottom_b = 635.0, 970.0
    a_low, a_high = 3.80, 5.15
    b_low, b_high = 2.2, 9.2
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#FFFFFF"/>',
        '<g font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif">',
        text("Fine λ sweep at 1000/1000 veh/h", WIDTH / 2, 48, size=31, anchor="middle", weight=700),
        text("(a) Overall traffic speed", LEFT, 92, size=25, weight=700),
    ]
    axes(parts, top=top_a, bottom=bottom_a, y_ticks=[4.0, 4.4, 4.8], y_low=a_low, y_high=a_high, x_labels=False)
    parts.append(text("Mean speed [m/s]", 45, (top_a + bottom_a) / 2, anchor="middle", rotate=-90))
    overall = [
        (x_pos(value), y_pos(float(aggregates[value]["all_speed_mean_mps"]), a_low, a_high, top_a, bottom_a))
        for value in lambdas
    ]
    parts.append(polyline(overall, blue))
    for value, (x, y) in zip(lambdas, overall, strict=True):
        mean = float(aggregates[value]["all_speed_mean_mps"])
        sd = float(aggregates[value]["all_speed_sample_sd_mps"])
        y1 = y_pos(mean + sd, a_low, a_high, top_a, bottom_a)
        y2 = y_pos(mean - sd, a_low, a_high, top_a, bottom_a)
        parts.append(f'<line x1="{x:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y2:.1f}" stroke="{blue}" stroke-width="2"/>')
        parts.append(f'<line x1="{x-7:.1f}" y1="{y1:.1f}" x2="{x+7:.1f}" y2="{y1:.1f}" stroke="{blue}" stroke-width="2"/>')
        parts.append(f'<line x1="{x-7:.1f}" y1="{y2:.1f}" x2="{x+7:.1f}" y2="{y2:.1f}" stroke="{blue}" stroke-width="2"/>')
        fill = "white" if value in REUSED else blue
        stroke = orange if value in REUSED else "white"
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="{fill}" stroke="{stroke}" stroke-width="3"/>')
    bx, by = overall[lambdas.index(best)]
    parts.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="14" fill="none" stroke="{red}" stroke-width="4"/>')
    parts.append(text(f"nominal best: λ={best:.3f}, 4.7192 m/s", bx + 30, by - 22, size=19, weight=600, fill=red))
    parts.append(text("Error bars: sample SD across seeds 33–42", LEFT + 18, bottom_a - 20, size=18, fill="#5B6573"))
    parts.append(text("Orange outline: reused coarse-sweep result", LEFT + 440, bottom_a - 20, size=18, fill="#5B6573"))

    parts.append(text("(b) Speed trade-off between traffic streams", LEFT, 600, size=25, weight=700))
    axes(parts, top=top_b, bottom=bottom_b, y_ticks=[3, 5, 7, 9], y_low=b_low, y_high=b_high, x_labels=True)
    parts.append(text("Mean speed [m/s]", 45, (top_b + bottom_b) / 2, anchor="middle", rotate=-90))
    parts.append(text("Convex weight λ", (LEFT + RIGHT) / 2, bottom_b + 75, size=23, anchor="middle"))
    merge = [(x_pos(value), y_pos(float(aggregates[value]["requesting_speed_mean_mps"]), b_low, b_high, top_b, bottom_b)) for value in lambdas]
    main = [(x_pos(value), y_pos(float(aggregates[value]["accepting_speed_mean_mps"]), b_low, b_high, top_b, bottom_b)) for value in lambdas]
    parts.extend((polyline(merge, green), polyline(main, purple)))
    for x, y in merge:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{green}" stroke="white" stroke-width="2"/>')
    for x, y in main:
        parts.append(f'<rect x="{x-6:.1f}" y="{y-6:.1f}" width="12" height="12" fill="{purple}" stroke="white" stroke-width="2"/>')
    parts.append(text("Merging side", RIGHT - 310, top_b + 165, size=19, fill=green, weight=600))
    parts.append(text("Mainline side", RIGHT - 150, top_b + 165, size=19, fill=purple, weight=600))
    parts.append(text("Eval.7 · 600 s · n=10 per λ · no physical collisions", WIDTH / 2, 1080, size=18, anchor="middle", fill="#5B6573"))
    parts.extend(("</g>", "</svg>"))
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(summary), encoding="utf-8")
    png = args.output.with_suffix(".png")
    if shutil.which("sips"):
        subprocess.run(
            ["sips", "-s", "format", "png", str(args.output), "--out", str(png)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    print(args.output)
    if png.is_file():
        print(png)


if __name__ == "__main__":
    main()
