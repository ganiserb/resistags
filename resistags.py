"""
Generate resistor cabinet sticker SVG from tag_template.svg.
Uses the resistors library; one sticker per value, 5-band 1% tolerance.
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from resistors import Resistor

# Color name -> fill hex (6 digits for SVG)
COLOR_HEX = {
    "black": "000000",
    "brown": "784421",
    "red": "ff0000",
    "orange": "ff6600",
    "yellow": "ffff00",
    "green": "00c400",
    "blue": "0055d4",
    "violet": "8f37c8",
    "grey": "828282",
    "white": "dbdbdb",
    "gold": "decd87",
    "silver": "c0c0c0",
}

INSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
SVG_NS = "http://www.w3.org/2000/svg"

ET.register_namespace("inkscape", INSCAPE_NS)
ET.register_namespace("", SVG_NS)
ET.register_namespace("sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd")

# Grid layout: columns per row (rows calculated automatically)
COLS = 5
STICKER_W = 23.0  # In millimeters
STICKER_H = 12.0  # In millimeters
# Spacing between stickers (can be different from sticker size for gaps/overlap)
SPACING_X = STICKER_W + 3  # Horizontal spacing (default: same as STICKER_W)
SPACING_Y = STICKER_H + 3  # Vertical spacing (default: same as STICKER_H)
# Margins for left and top edges
MARGIN_LEFT = 0.0  # Left margin in millimeters
MARGIN_TOP = 0.0   # Top margin in millimeters


def format_value(ohms: float) -> str:
    if ohms >= 1_000_000:
        if ohms == 1_000_000:
            return "1 MΩ"
        return f"{ohms / 1_000_000:.1f} MΩ".replace(".0 ", " ")
    if ohms >= 1_000:
        if ohms % 1_000 == 0:
            return f"{int(ohms // 1_000)} kΩ"
        return f"{ohms / 1_000:.1f} kΩ".replace(".0 ", " ")
    if ohms < 1:
        return f"{ohms} Ω"
    if ohms == int(ohms):
        return f"{int(ohms)} Ω"
    return f"{ohms} Ω"


def get_subohm_colors(ohms: float, tolerance: float, num_bands: int) -> list[str]:
    """Manually construct color bands for sub-ohm and low-ohm values.
    
    For values < 1 ohm: uses leading black (0), then significant digits, silver (0.01x) multiplier.
    For values like 1.58: uses standard encoding with appropriate multiplier.
    """
    # Tolerance color mapping
    tolerance_colors = {1.0: "brown", 5.0: "gold", 10.0: "silver"}
    tolerance_color = tolerance_colors.get(tolerance, "brown")
    
    digit_colors = ["black", "brown", "red", "orange", "yellow", "green", "blue", "violet", "grey", "white"]
    
    if ohms < 10:
        # For values < 10 ohms: use centiohms encoding with silver or grey multiplier
        # Examples:
        # 0.1 = 10 * 0.01 = black(0), brown(1), black(0), silver, brown
        # 0.33 = 33 * 0.01 = black(0), orange(3), orange(3), silver, brown
        # 0.5 = 50 * 0.01 = black(0), green(5), black(0), silver, brown
        # 1.0 = 100 * 0.01 = brown(1), black(0), black(0), silver, brown
        # 1.5 = 150 * 0.01 = brown(1), green(5), black(0), grey, brown
        # 2.0 = 200 * 0.01 = red(2), black(0), black(0), silver, brown
        
        # Convert to centiohms (multiply by 100) to get the significant digits
        centiohms = int(round(ohms * 100))
        digits = [int(d) for d in str(centiohms)]
        
        # Determine multiplier: grey for values with one decimal place (like 1.5), silver for others
        if ohms < 1:
            multiplier = "silver"  # 0.01x for sub-ohm values
        elif ohms == int(ohms):
            multiplier = "silver"  # 0.01x for integer values like 1.0, 2.0
        else:
            multiplier = "grey"  # 0.01x for decimal values like 1.5
        
        if num_bands == 5:
            # Pad to 3 digits with leading zeros
            while len(digits) < 3:
                digits.insert(0, 0)
            return [
                digit_colors[digits[0]],
                digit_colors[digits[1]],
                digit_colors[digits[2]],
                multiplier,
                tolerance_color,
            ]
        else:
            # 4-band: pad to 2 digits
            while len(digits) < 2:
                digits.insert(0, 0)
            return [
                digit_colors[digits[0]],
                digit_colors[digits[1]],
                multiplier,
                tolerance_color,
            ]
    else:
        # For values >= 10, use standard library
        r = Resistor.with_resistance(int(ohms), tolerance, num_bands)
        return r.get_colors()


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


def parse_path_bounding_box(d_path: str) -> tuple[float, float, float, float]:
    """Parse SVG path to get bounding box (min_x, min_y, width, height).
    
    For the template, we know the approximate dimensions, but we calculate
    from the path to be robust to template changes.
    """
    import re
    # For now, use a simpler approach: find all coordinate pairs in the path
    # This works for the template which uses mostly absolute coordinates
    all_numbers = [float(n) for n in re.findall(r'-?[\d.]+', d_path)]
    
    # The template path has coordinates in pairs (x, y) or single values for H/V
    # We'll collect all x and y values separately
    # Pattern: after M or L, we get pairs; after H we get x; after V we get y
    x_vals = []
    y_vals = []
    i = 0
    in_pair = False
    
    # Simple state machine: track if we're reading x or y
    parts = re.findall(r'([MLHVmlhvzZ])([^MLHVmlhvzZ]*)', d_path)
    current_x = 0.0
    current_y = 0.0
    
    for cmd, args_str in parts:
        if cmd.upper() == 'Z':
            continue
        numbers = [float(n) for n in re.findall(r'-?[\d.]+', args_str)]
        
        if cmd.upper() == 'M' or cmd.upper() == 'L':
            if len(numbers) >= 2:
                current_x = numbers[0]
                current_y = numbers[1]
                x_vals.append(current_x)
                y_vals.append(current_y)
        elif cmd.upper() == 'H':
            if numbers:
                current_x = numbers[0]
                x_vals.append(current_x)
                y_vals.append(current_y)
        elif cmd.upper() == 'V':
            if numbers:
                current_y = numbers[0]
                x_vals.append(current_x)
                y_vals.append(current_y)
        elif cmd == 'h':
            if numbers:
                current_x += numbers[0]
                x_vals.append(current_x)
                y_vals.append(current_y)
        elif cmd == 'v':
            if numbers:
                current_y += numbers[0]
                x_vals.append(current_x)
                y_vals.append(current_y)
    
    if not x_vals:
        return (0, 0, 0, 0)
    
    return (min(x_vals), min(y_vals), max(x_vals) - min(x_vals), max(y_vals) - min(y_vals))


def extract_template_metrics(layer: ET.Element) -> dict:
    """Extract dimensions and positions from template elements."""
    metrics = {}
    
    # Find t_tag path to get sticker bounding box
    # The template path is a rectangle, so we can extract dimensions more reliably
    for el in layer.iter():
        label = get_label(el)
        if label == "t_tag" and el.tag.endswith("path"):
            d = el.get("d", "")
            # For the template rectangle path, extract key coordinates
            # Pattern: M x1,y1 V y2 H x2 V y3 ... 
            import re
            # Get the initial M coordinates
            m_match = re.search(r'M\s+([\d.]+),([\d.]+)', d)
            if m_match:
                start_x = float(m_match.group(1))
                start_y = float(m_match.group(2))
                
                # Find all absolute H and V coordinates
                h_coords = [float(x) for x in re.findall(r'H\s+([\d.]+)', d)]
                v_coords = [float(y) for y in re.findall(r'V\s+([\d.]+)', d)]
                
                if h_coords and v_coords:
                    # The rectangle is defined by the min/max of these coordinates
                    all_x = [start_x] + h_coords
                    all_y = [start_y] + v_coords
                    min_x = min(all_x)
                    max_x = max(all_x)
                    min_y = min(all_y)
                    max_y = max(all_y)
                    
                    metrics["template_w"] = max_x - min_x
                    metrics["template_h"] = max_y - min_y
                    metrics["template_min_x"] = min_x
                    metrics["template_min_y"] = min_y
                    break
    
    # Find t_color_tolerance rect to get its position and width
    for el in layer.iter():
        label = get_label(el)
        if label == "t_color_tolerance" and el.tag.endswith("rect"):
            x = float(el.get("x", "0"))
            w = float(el.get("width", "0"))
            metrics["tolerance_rect_x"] = x
            metrics["tolerance_rect_w"] = w
            metrics["value_right_x"] = x + w
            break
    
    # Find t_value text to get its x position (as fallback)
    for el in layer.iter():
        label = get_label(el)
        if label == "t_value" and el.tag.endswith("text"):
            x = el.get("x")
            if x:
                metrics["value_text_x"] = float(x)
            # Also check tspan
            for tspan in el.iter(f"{{{SVG_NS}}}tspan"):
                x = tspan.get("x")
                if x:
                    metrics["value_text_x"] = float(x)
                    break
            break
    
    return metrics


def generate_stickers(resistance_ohms: list[float | int], output_filename: str, tolerance: float = 1.0) -> Path:
    """Generate sticker SVG for a list of resistance values.
    
    Args:
        resistance_ohms: List of resistance values in ohms (can be decimal for values < 1)
        output_filename: Output filename (e.g., "resistags_output.svg")
        tolerance: Tolerance percentage (e.g., 1.0 for 1%, 5.0 for 5%)
    
    Returns:
        Path to the generated file
    """
    template_path = Path(__file__).resolve().parent / "tag_template.svg"
    out_path = template_path.parent / output_filename

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
    
    # Extract template metrics before clearing the layer
    template_metrics = extract_template_metrics(layer)
    template_w = template_metrics.get("template_w", 21.0)
    template_h = template_metrics.get("template_h", 11.5)
    template_min_x = template_metrics.get("template_min_x", 8.4605201)
    template_min_y = template_metrics.get("template_min_y", 9.2461907)
    value_right_x = template_metrics.get("value_right_x", 28.1810686)
    
    layer.clear()
    layer.set("id", "stickers")
    set_label(layer, "Stickers")

    scale_x = STICKER_W / template_w
    scale_y = STICKER_H / template_h

    # Determine number of bands based on tolerance (5 bands for 1%, 4 bands for others)
    num_bands = 5 if tolerance == 1.0 else 4

    for idx, ohms in enumerate(resistance_ohms):
        row = idx // COLS
        col = idx % COLS
        tx = MARGIN_LEFT + col * SPACING_X
        ty = MARGIN_TOP + row * SPACING_Y

        # Handle values < 10 ohms manually (library doesn't support sub-ohm and low values properly)
        if ohms < 10:
            colors = get_subohm_colors(ohms, tolerance, num_bands)
        else:
            r = Resistor.with_resistance(int(ohms), tolerance, num_bands)
            colors = r.get_colors()
        hexes = [COLOR_HEX.get(c.lower(), "000000") for c in colors]
        value_text = format_value(ohms).strip()

        group = ET.SubElement(layer, f"{{{SVG_NS}}}g")
        group.set("id", f"sticker_{idx}")
        # Transform: translate to position, accounting for template origin offset after scaling
        # Formula: translate(tx - template_min_x * scale_x, ty - template_min_y * scale_y) scale(sx, sy)
        adjusted_tx = tx - template_min_x * scale_x
        adjusted_ty = ty - template_min_y * scale_y
        group.set("transform", f"translate({adjusted_tx},{adjusted_ty}) scale({scale_x},{scale_y})")
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
                if num_bands == 4:
                    # Skip t_color_4 for 4-band resistors (tolerance is the 4th band)
                    continue
                if node.get("style") is not None:
                    node.set("style", set_rect_fill(node.get("style", ""), hexes[3]))
            elif label == "t_color_tolerance":
                if num_bands == 4:
                    # For 4-band resistors, tolerance is the 4th band (index 3)
                    if len(hexes) > 3 and node.get("style") is not None:
                        node.set("style", set_rect_fill(node.get("style", ""), hexes[3]))
                else:
                    # For 5-band resistors, tolerance is the 5th band (index 4)
                    if len(hexes) > 4 and node.get("style") is not None:
                        node.set("style", set_rect_fill(node.get("style", ""), hexes[4]))
            elif label == "t_tolerance":
                tolerance_text = f"±{int(tolerance)}" if tolerance == int(tolerance) else f"±{tolerance}"
                for tspan in node.iter(f"{{{SVG_NS}}}tspan"):
                    if tspan.text:
                        tspan.text = tolerance_text
                        break
            elif label == "t_value":
                # Use the x position from template (value_right_x is already scaled in template coordinates)
                node.set("x", str(value_right_x))
                for tspan in node.iter(f"{{{SVG_NS}}}tspan"):
                    if "x" in tspan.attrib:
                        tspan.set("x", str(value_right_x))
                    if tspan.text and re.match(r"^[\d.]+$", tspan.text.strip()):
                        tspan.text = value_text
                        tspan.tail = ""
                        break
                    for sub in tspan:
                        if "x" in sub.attrib:
                            sub.set("x", str(value_right_x))
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
    return out_path


if __name__ == "__main__":
    # Define resistance groups
    values_0_25_watt_1percent = [
        10, 22, 47, 100, 150, 200, 220, 270, 330, 470, 510, 680,
        1000, 2000, 2200, 3300, 4700, 5100, 6800, 10_000, 20_000, 47_000,
        51_000, 68_000, 100_000, 220_000, 300_000, 470_000, 680_000, 1_000_000,
    ]
    
    values_1_watt_1percent_low = [
        0.1, 0.33, 0.5, 1, 1.5, 2, 2.7, 3.3, 3.9, 4.7, 5.6, 7.5, 10,
        15, 20, 27, 33, 39, 47, 56, 75, 100, 150, 200, 270, 330, 390, 470, 560, 750
    ]

    values_1_watt_1percent_high = [
        1000, 1500, 2000, 2700, 3300, 3900, 4700, 5600, 7500, 8200, 10_000,
        15_000, 20_000, 27_000, 33_000, 39_000, 47_000, 56_000, 75_000, 82_000,
        100_000, 150_000, 200_000, 270_000, 330_000, 390_000, 470_000, 560_000, 750_000, 820_000
    ]
    # Generate sticker files for each group
    generate_stickers(values_0_25_watt_1percent, "resistags_0_25_watt_1percent.svg", tolerance=1.0)
    generate_stickers(values_1_watt_1percent_low, "resistags_1_watt_1percent_low.svg", tolerance=1.0)
    generate_stickers(values_1_watt_1percent_high, "resistags_1_watt_1percent_high.svg", tolerance=1.0)
