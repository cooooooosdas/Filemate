"""Export existing brand artwork with Pillow and vtracer 0.6.15."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps
from PIL import __version__ as pillow_version

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "filemate/web/src/assets"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def file_record(source: Path, output: Path) -> dict[str, Any]:
    """Record reproducible asset sizes and identities without machine paths."""
    return {
        "source": source.name,
        "source_bytes": source.stat().st_size,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output": output.name,
        "output_bytes": output.stat().st_size,
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }


def export_raster(
    source: Path, output: Path, size: tuple[int, int], quality: int
) -> dict[str, Any]:
    """Preserve transparency and aspect ratio inside an explicit image canvas."""
    with Image.open(source) as original:
        fitted = ImageOps.contain(original.convert("RGBA"), size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", size)
        canvas.alpha_composite(
            fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2)
        )
        if output.suffix == ".webp":
            canvas.save(output, "WEBP", quality=quality, method=6, exact=True)
        else:
            canvas.save(output, "PNG", optimize=True)
    return file_record(source, output) | {"dimensions": list(size), "quality": quality}


def export_logo(output: Path) -> dict[str, Any]:
    """Trace the original lettering and folder into independent vector paths."""
    import vtracer

    source = SOURCES / "filemate-brand-lockup.png"
    scratch = ROOT / "_working/final-web-20261105"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".png", dir=scratch, delete=False) as temporary:
        trace_input = Path(temporary.name)
    try:
        with Image.open(source) as original:
            original.resize((934, 263), Image.Resampling.LANCZOS).save(trace_input)
        vtracer.convert_image_to_svg_py(
            str(trace_input),
            str(output),
            colormode="color",
            hierarchical="stacked",
            mode="spline",
            filter_speckle=12,
            color_precision=4,
            layer_difference=32,
            corner_threshold=60,
            length_threshold=4,
            max_iterations=10,
            splice_threshold=45,
            path_precision=2,
        )
    finally:
        trace_input.unlink(missing_ok=True)
    ET.register_namespace("", SVG_NAMESPACE)
    tree = ET.parse(output)
    svg = tree.getroot()
    svg.set("viewBox", "0 0 1867 526")
    svg.set("width", "1867")
    svg.set("height", "526")
    group = ET.Element(f"{{{SVG_NAMESPACE}}}g", {"transform": "scale(1.998929336 2)"})
    for element in list(svg):
        svg.remove(element)
        if element.tag != f"{{{SVG_NAMESPACE}}}path" or element.get("d", "").strip():
            group.append(element)
    svg.append(group)
    ET.indent(tree, space="  ")
    tree.write(output, encoding="utf-8", xml_declaration=False)
    output.write_bytes(output.read_bytes().replace(b"\r\n", b"\n"))
    return file_record(source, output) | {"dimensions": [1867, 526], "format": "vector_paths"}


def export_assets(output: Path) -> dict[str, Any]:
    """Create a new derivative directory while preserving original artwork."""
    output.mkdir(parents=True, exist_ok=False)
    records = [export_logo(output / "filemate-brand-lockup.svg")]
    for original, name, size, quality in (
        ("filemate-mascot.png", "filemate-mascot-home.webp", (220, 294), 92),
        ("filemate-mascot.png", "filemate-mascot-home.png", (220, 294), 100),
        ("filemate-mascot.png", "filemate-mascot-tutor.webp", (560, 746), 92),
        ("filemate-mascot-expressions.png", "filemate-mascot-expressions.webp", (1040, 780), 80),
        (
            "filemate-mascot-expressions.png",
            "filemate-mascot-expressions-tutor.webp",
            (1448, 1086),
            90,
        ),
        ("filemate-app-icon-light.png", "filemate-app-icon-light.webp", (128, 128), 92),
    ):
        records.append(export_raster(SOURCES / original, output / name, size, quality))
    report = {
        "source_artwork": "Existing FileMate originals; no new generated illustration.",
        "tools": {"pillow": pillow_version, "vtracer": "0.6.15"},
        "assets": records,
    }
    (output / "manifest.json").write_bytes(
        (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    return report


def main() -> int:
    """Export into a new directory and report file instead of overwriting assets."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.report.exists():
        parser.error("Choose a new output directory and report file.")
    report = export_assets(args.output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8", newline="\n") as destination:
        json.dump(report, destination, ensure_ascii=False, indent=2)
    print(json.dumps({"assets": len(report["assets"]), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
