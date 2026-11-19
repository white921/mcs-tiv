#!/usr/bin/env python3
"""Plot the 1000/1000, 600-second lambda screening recorded in the ledger."""

from __future__ import annotations

import argparse
import html
import math
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECORD = ROOT / "docs/experiments/2026-11-17-normalized-convex-lambda-wide-sweep-600s-development.md"
DEFAULT_OUTPUT = ROOT / "docs/experiments/figures/2026-11-17-normalized-convex-lambda-wide-sweep-600s"
REUSED_LAMBDAS = {0.90, 0.95}
WIDTH, HEIGHT = 1600, 1260
LEFT, RIGHT = 150, 1540


def read_rows(record: Path) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for raw_line in record.read_text(encoding="utf-8").splitlines():
        line = raw_line.replace("**", "")
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) < 4:
            continue
        try:
            lambda_value = float(cells[0].replace("※", ""))
        except ValueError:
            continue
        speed_match = re.fullmatch(r"([0-9.]+)\s*±\s*([0-9.]+)", cells[1])
        if speed_match is None:
            continue
        rows.append(
            {
                "lambda": lambda_value,
                "overall": float(speed_match.group(1)),
                "overall_sd": float(speed_match.group(2)),
                "merge": float(cells[2]),
                "mainline": float(cells[3]),
            }
        )
    rows.sort(key=lambda row: row["lambda"])
    expected = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]
    actual = [row["lambda"] for row in rows]
    if actual != expected:
        raise ValueError(f"unexpected lambda rows in {record}: {actual}")
    return rows


def x_position(value: float) -> float:
    return LEFT + value * (RIGHT - LEFT)


def y_position(value: float, low: float, high: float, top: float, bottom: float) -> float:
    return bottom - (value - low) / (high - low) * (bottom - top)


def svg_text(
    value: str,
    x: float,
    y: float,
    *,
    size: int = 24,
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


def polyline(values: list[tuple[float, float]], color: str, width: float = 4) -> str:
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in values)
    return (
        f'<polyline points="{points}" fill="none" stroke="{color}" '
        f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>'
    )


def star_points(cx: float, cy: float, outer: float = 17, inner: float = 7) -> str:
    points = []
    for index in range(10):
        angle = -math.pi / 2 + index * math.pi / 5
        radius = outer if index % 2 == 0 else inner
        points.append(f"{cx + radius * math.cos(angle):.1f},{cy + radius * math.sin(angle):.1f}")
    return " ".join(points)


def draw_axes(
    parts: list[str],
    *,
    top: float,
    bottom: float,
    y_ticks: list[float],
    y_low: float,
    y_high: float,
    show_x_labels: bool,
) -> None:
    parts.append(f'<line x1="{LEFT}" y1="{bottom}" x2="{RIGHT}" y2="{bottom}" stroke="#6B7280" stroke-width="2"/>')
    parts.append(f'<line x1="{LEFT}" y1="{top}" x2="{LEFT}" y2="{bottom}" stroke="#6B7280" stroke-width="2"/>')
    for tick in y_ticks:
        y = y_position(tick, y_low, y_high, top, bottom)
        parts.append(f'<line x1="{LEFT}" y1="{y:.1f}" x2="{RIGHT}" y2="{y:.1f}" stroke="#D7DCE2" stroke-width="1.5"/>')
        parts.append(svg_text(f"{tick:g}", LEFT - 18, y + 8, size=22, anchor="end", fill="#5B6573"))
    for index in range(11):
        value = index / 10
        x = x_position(value)
        parts.append(f'<line x1="{x:.1f}" y1="{bottom}" x2="{x:.1f}" y2="{bottom + 9}" stroke="#6B7280" stroke-width="2"/>')
        if show_x_labels:
            parts.append(svg_text(f"{value:.1f}", x, bottom + 39, size=22, anchor="middle", fill="#5B6573"))


def render_svg(rows: list[dict[str, float]]) -> str:
    top_a, bottom_a = 145.0, 570.0
    top_b, bottom_b = 720.0, 1120.0
    y_a_low, y_a_high = 3.75, 5.40
    y_b_low, y_b_high = 0.8, 11.2
    blue, orange, green, purple, red = "#1769AA", "#D46B08", "#00796B", "#7B1FA2", "#C62828"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        f'<rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="#FFFFFF"/>',
        '<g font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif">',
        svg_text("Normalized convex weighting: λ sweep at 1000/1000 veh/h", WIDTH / 2, 52, size=32, anchor="middle", weight=700),
        svg_text("(a) Overall traffic speed", LEFT, 105, size=26, weight=700),
    ]
    band_x = x_position(0.5)
    parts.append(f'<rect x="{band_x:.1f}" y="{top_a}" width="{x_position(0.8) - band_x:.1f}" height="{bottom_a - top_a:.1f}" fill="#E8F1FA" opacity="0.85"/>')
    draw_axes(parts, top=top_a, bottom=bottom_a, y_ticks=[4.0, 4.5, 5.0], y_low=y_a_low, y_high=y_a_high, show_x_labels=False)
    parts.append(svg_text("Mean speed [m/s]", 48, (top_a + bottom_a) / 2, size=23, anchor="middle", rotate=-90))

    overall_points = [(x_position(row["lambda"]), y_position(row["overall"], y_a_low, y_a_high, top_a, bottom_a)) for row in rows]
    parts.append(polyline(overall_points, blue))
    for row, (x, y) in zip(rows, overall_points, strict=True):
        y_top = y_position(row["overall"] + row["overall_sd"], y_a_low, y_a_high, top_a, bottom_a)
        y_bottom = y_position(row["overall"] - row["overall_sd"], y_a_low, y_a_high, top_a, bottom_a)
        parts.append(f'<line x1="{x:.1f}" y1="{y_top:.1f}" x2="{x:.1f}" y2="{y_bottom:.1f}" stroke="{blue}" stroke-width="2"/>')
        parts.append(f'<line x1="{x - 8:.1f}" y1="{y_top:.1f}" x2="{x + 8:.1f}" y2="{y_top:.1f}" stroke="{blue}" stroke-width="2"/>')
        parts.append(f'<line x1="{x - 8:.1f}" y1="{y_bottom:.1f}" x2="{x + 8:.1f}" y2="{y_bottom:.1f}" stroke="{blue}" stroke-width="2"/>')
        fill = "white" if row["lambda"] in REUSED_LAMBDAS else blue
        stroke = orange if row["lambda"] in REUSED_LAMBDAS else "white"
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="{fill}" stroke="{stroke}" stroke-width="3"/>')

    best = next(row for row in rows if row["lambda"] == 0.60)
    best_x = x_position(best["lambda"])
    best_y = y_position(best["overall"], y_a_low, y_a_high, top_a, bottom_a)
    parts.append(f'<polygon points="{star_points(best_x, best_y)}" fill="{red}" stroke="white" stroke-width="2"/>')
    label_x = x_position(0.43)
    label_y = y_position(5.17, y_a_low, y_a_high, top_a, bottom_a)
    parts.append(f'<line x1="{label_x + 74:.1f}" y1="{label_y + 15:.1f}" x2="{best_x - 9:.1f}" y2="{best_y - 14:.1f}" stroke="#5B6573" stroke-width="2"/>')
    parts.append(svg_text("coarse-grid best", label_x, label_y, size=22, anchor="middle", weight=600))
    parts.append(svg_text("λ = 0.60, 4.6835 m/s", label_x, label_y + 27, size=20, anchor="middle"))

    legend_y = 540
    parts.append(f'<line x1="{LEFT + 22}" y1="{legend_y}" x2="{LEFT + 82}" y2="{legend_y}" stroke="{blue}" stroke-width="4"/>')
    parts.append(f'<circle cx="{LEFT + 52}" cy="{legend_y}" r="7" fill="{blue}"/>')
    parts.append(svg_text("Overall mean ± sample SD", LEFT + 96, legend_y + 7, size=19))
    parts.append(f'<circle cx="{LEFT + 430}" cy="{legend_y}" r="8" fill="white" stroke="{orange}" stroke-width="3"/>')
    parts.append(svg_text("Reused completed runs", LEFT + 450, legend_y + 7, size=19))

    parts.append(svg_text("(b) Speed trade-off between traffic streams", LEFT, 675, size=26, weight=700))
    draw_axes(parts, top=top_b, bottom=bottom_b, y_ticks=[2, 4, 6, 8, 10], y_low=y_b_low, y_high=y_b_high, show_x_labels=True)
    parts.append(svg_text("Mean speed [m/s]", 48, (top_b + bottom_b) / 2, size=23, anchor="middle", rotate=-90))
    parts.append(svg_text("Convex weight λ", (LEFT + RIGHT) / 2, bottom_b + 82, size=24, anchor="middle"))
    parts.append(f'<line x1="{best_x:.1f}" y1="{top_b}" x2="{best_x:.1f}" y2="{bottom_b}" stroke="{red}" stroke-width="2" stroke-dasharray="10 8" opacity="0.8"/>')

    merge_points = [(x_position(row["lambda"]), y_position(row["merge"], y_b_low, y_b_high, top_b, bottom_b)) for row in rows]
    mainline_points = [(x_position(row["lambda"]), y_position(row["mainline"], y_b_low, y_b_high, top_b, bottom_b)) for row in rows]
    parts.extend([polyline(merge_points, green), polyline(mainline_points, purple)])
    for x, y in merge_points:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{green}" stroke="white" stroke-width="2"/>')
    for x, y in mainline_points:
        parts.append(f'<rect x="{x - 6.5:.1f}" y="{y - 6.5:.1f}" width="13" height="13" fill="{purple}" stroke="white" stroke-width="2"/>')

    parts.append(f'<line x1="{LEFT + 22}" y1="{top_b + 30}" x2="{LEFT + 82}" y2="{top_b + 30}" stroke="{green}" stroke-width="4"/>')
    parts.append(f'<circle cx="{LEFT + 52}" cy="{top_b + 30}" r="7" fill="{green}"/>')
    parts.append(svg_text("Merging side (main_0)", LEFT + 96, top_b + 37, size=19))
    parts.append(f'<line x1="{LEFT + 390}" y1="{top_b + 30}" x2="{LEFT + 450}" y2="{top_b + 30}" stroke="{purple}" stroke-width="4"/>')
    parts.append(f'<rect x="{LEFT + 413.5}" y="{top_b + 23.5}" width="13" height="13" fill="{purple}"/>')
    parts.append(svg_text("Mainline side (main_1)", LEFT + 464, top_b + 37, size=19))
    parts.append(svg_text("Eval.7 · 600 s · seeds 33–42 · n = 10 per λ · no physical collisions", WIDTH / 2, 1235, size=19, anchor="middle", fill="#5B6573"))
    parts.extend(["</g>", "</svg>"])
    return "\n".join(parts) + "\n"


def render_png(svg_path: Path, png_path: Path) -> None:
    sips = shutil.which("sips")
    if sips is None:
        return
    subprocess.run(
        [sips, "-s", "format", "png", str(svg_path), "--out", str(png_path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, default=DEFAULT_RECORD)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    rows = read_rows(args.record)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    svg_path = args.output.with_suffix(".svg")
    png_path = args.output.with_suffix(".png")
    svg_path.write_text(render_svg(rows), encoding="utf-8")
    render_png(svg_path, png_path)
    print(svg_path)
    if png_path.is_file():
        print(png_path)


if __name__ == "__main__":
    main()
