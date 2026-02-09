"""
Generate resistor cabinet sticker SVG from tag_template.svg.
Uses the resistors library; one sticker per value, 5-band 1% tolerance.
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from resistors import Resistor

# Resistor values in ohms (order preserved for layout)
RESISTANCE_OHMS = [
    10, 20, 47, 100, 150, 200, 220, 270, 330, 470, 510, 680,
    1000, 2000, 2200, 3300, 4700, 5100, 6800, 10_000, 20_000, 47_000,
    51_000, 68_000, 100_000, 220_000, 300_000, 470_000, 680_000, 1_000_000,
]

# Color name -> fill hex (6 digits for SVG)
COLOR_HEX = {
    "black": "000000",
    "brown": "b24000",
    "red": "ff0000",
    "orange": "ff8000",
    "yellow": "ffff00",
    "green": "00c400",
    "blue": "002bff",
    "violet": "dc2bff",
    "grey": "828282",
    "white": "dbdbdb",
    "gold": "fbb839",
    "silver": "c0c0c0",
}

INSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
SVG_NS = "http://www.w3.org/2000/svg"

ET.register_namespace("inkscape", INSCAPE_NS)
ET.register_namespace("", SVG_NS)
ET.register_namespace("sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd")

# 6 rows x 5 columns; tight spacing for cutting (sticker size from template)
COLS = 5
ROWS = 6
STICKER_W = 21.0
STICKER_H = 11.5

# t_color_tolerance right edge: align value text to this x (text-anchor:end)
TOLERANCE_RECT_X = 25.002619
TOLERANCE_RECT_W = 3.1784496
VALUE_RIGHT_X = TOLERANCE_RECT_X + TOLERANCE_RECT_W


def format_value(ohms: int) -> str:
    if ohms >= 1_000_000:
        if ohms == 1_000_000:
            return "1 MΩ"
        return f"{ohms / 1_000_000:.1f} MΩ".replace(".0 ", " ")
    if ohms >= 1_000:
        if ohms % 1_000 == 0:
            return f"{ohms // 1_000} kΩ"
        return f"{ohms / 1_000:.1f} kΩ".replace(".0 ", " ")
    return f"{ohms} Ω"


def set_rect_fill(style_attr: str, hex_fill: str) -> str:
    return re.sub(r"fill:#[0-9a-fA-F]+", f"fill:#{hex_fill}", style_attr, count=1)


def get_label(el: ET.Element) -> str | None:
    return el.get(f"{{{INSCAPE_NS}}}label")


def set_label(el: ET.Element, label: str) -> None:
    el.set(f"{{{INSCAPE_NS}}}label", label)


def deep_copy_element(el: ET.Element) -> ET.Element:
    new = ET.Element(el.tag, attrib=dict(el.attrib))
    new.text = el.text
    new.tail = el.tail
    for child in el:
        new.append(deep_copy_element(child))
    return new


def uniquify_ids(parent: ET.Element, prefix: str) -> None:
    for i, child in enumerate(parent):
        old_id = child.get("id")
        if old_id:
            child.set("id", f"{prefix}_{i}_{old_id}")
        uniquify_ids(child, prefix)


def main() -> None:
    template_path = Path(__file__).resolve().parent / "tag_template.svg"
    out_path = template_path.parent / "resistags_output.svg"

    tree = ET.parse(template_path)
    root = tree.getroot()
    layer = None
    for el in root.iter():
        if el.get("id") == "layer1":
            layer = el
            break
    if layer is None:
        raise SystemExit("Template SVG: layer with id 'layer1' not found.")

    sticker_children = list(layer)
    layer.clear()
    layer.set("id", "stickers")
    set_label(layer, "Stickers")

    for idx, ohms in enumerate(RESISTANCE_OHMS):
        row = idx // COLS
        col = idx % COLS
        tx = col * STICKER_W
        ty = row * STICKER_H

        r = Resistor.with_resistance(ohms, 1, 5)
        colors = r.get_colors()
        hexes = [COLOR_HEX.get(c.lower(), "000000") for c in colors]
        value_text = format_value(ohms).strip()

        group = ET.SubElement(layer, f"{{{SVG_NS}}}g")
        group.set("id", f"sticker_{idx}")
        group.set("transform", f"translate({tx},{ty})")
        set_label(group, value_text)

        prefix = f"sticker{idx}"
        for child in sticker_children:
            node = deep_copy_element(child)
            label = get_label(node)
            if label in ("t_color_1", "r_color_1") and len(hexes) > 0:
                if node.get("style") is not None:
                    node.set("style", set_rect_fill(node.get("style", ""), hexes[0]))
            elif label == "t_color_2" and len(hexes) > 1:
                if node.get("style") is not None:
                    node.set("style", set_rect_fill(node.get("style", ""), hexes[1]))
            elif label == "t_color_3" and len(hexes) > 2:
                if node.get("style") is not None:
                    node.set("style", set_rect_fill(node.get("style", ""), hexes[2]))
            elif label == "t_color_4" and len(hexes) > 3:
                if node.get("style") is not None:
                    node.set("style", set_rect_fill(node.get("style", ""), hexes[3]))
            elif label == "t_color_tolerance" and len(hexes) > 4:
                if node.get("style") is not None:
                    node.set("style", set_rect_fill(node.get("style", ""), hexes[4]))
            elif label == "t_value":
                node.set("x", str(VALUE_RIGHT_X))
                for tspan in node.iter(f"{{{SVG_NS}}}tspan"):
                    if "x" in tspan.attrib:
                        tspan.set("x", str(VALUE_RIGHT_X))
                    if tspan.text and re.match(r"^[\d.]+$", tspan.text.strip()):
                        tspan.text = value_text
                        tspan.tail = ""
                        break
                    for sub in tspan:
                        if "x" in sub.attrib:
                            sub.set("x", str(VALUE_RIGHT_X))
                        if sub.text and re.match(r"^[\d.]+$", (sub.text or "").strip()):
                            sub.text = value_text
                            if sub.tail:
                                sub.tail = ""
                            break

            uniquify_ids(node, prefix)
            group.append(node)

    # Do not use ET.indent() - it adds whitespace that becomes part of text content (xml:space="preserve")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n')
        f.write("<!-- Generated by resistags.py -->\n")
        tree.write(f, encoding="unicode", default_namespace="", method="xml")
    print(out_path)


if __name__ == "__main__":
    main()
