"""Builds static/map-style.json: bikıyak's "minimal grey + yellow roads" map theme.

Starts from OpenFreeMap's Positron style (tiles, glyphs and sprites stay on OpenFreeMap) and
recolours it: white land, light-grey blocks, cool-grey water, main roads in brand yellow, bold
navy labels, local (Turkish) place names first. Rerun when OpenFreeMap changes its style:

    python3 deploy/build_map_style.py
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

SOURCE = "https://tiles.openfreemap.org/styles/positron"
TARGET = Path(__file__).resolve().parent.parent / "static" / "map-style.json"

INK, INK_2, YELLOW, YELLOW_DARK, YELLOW_SOFT = "#0B1433", "#525C78", "#FFC933", "#E9AE12", "#FFE08A"


def arterial(yellow: str, grey: str) -> list:
    """Only arterials (primary, trunk) are yellow; secondary and tertiary streets stay grey, or the
    whole city turns yellow at city scale."""
    return ["match", ["get", "class"], ["primary", "trunk"], yellow, grey]


# layer id -> {paint property: colour}
COLOURS = {
    "background": {"background-color": "#FFFFFF"},
    "park": {"fill-color": "#EEF3EF"},
    "water": {"fill-color": "#DDE3EC"},
    "landuse_residential": {"fill-color": "#FAFAFB"},
    "landcover_wood": {"fill-color": "#EFF2EF"},
    "waterway": {"line-color": "#CBD4E1"},
    "building": {"fill-color": "#F1F2F5", "fill-outline-color": "#E4E6EC"},
    "tunnel_motorway_casing": {"line-color": "#ECEEF2"},
    "tunnel_motorway_inner": {"line-color": "#F7F8FA"},
    "aeroway-taxiway": {"line-color": "#E9ECF1"},
    "aeroway-runway-casing": {"line-color": "#E9ECF1"},
    "aeroway-area": {"fill-color": "#F4F5F8"},
    "aeroway-runway": {"line-color": "#FFFFFF"},
    "road_area_pier": {"fill-color": "#FFFFFF"},
    "road_pier": {"line-color": "#FFFFFF"},
    "highway_path": {"line-color": "#ECEEF3"},
    "highway_minor": {"line-color": "#E1E5EC"},
    "highway_major_casing": {"line-color": arterial(YELLOW_DARK, "#DADEE6")},
    "highway_major_inner": {"line-color": arterial(YELLOW, "#FFFFFF")},
    "highway_major_subtle": {"line-color": arterial(YELLOW_SOFT, "#E3E7EE")},
    "highway_motorway_casing": {"line-color": YELLOW_DARK},
    "highway_motorway_inner": {"line-color": YELLOW},
    "highway_motorway_subtle": {"line-color": YELLOW_SOFT},
    "highway_motorway_bridge_casing": {"line-color": YELLOW_DARK},
    "highway_motorway_bridge_inner": {"line-color": YELLOW},
    "railway_transit": {"line-color": "#D6DAE3"}, "railway_service": {"line-color": "#D6DAE3"},
    "railway": {"line-color": "#D6DAE3"},
    "boundary_3": {"line-color": "#C6CBD6"}, "boundary_2": {"line-color": "#C6CBD6"},
    "boundary_disputed": {"line-color": "#C6CBD6"},
    "waterway_line_label": {"text-color": "#6B7A99", "text-halo-color": "#FFFFFF"},
    "water_name_point_label": {"text-color": "#5B6B8C", "text-halo-color": "#FFFFFF"},
    "water_name_line_label": {"text-color": "#5B6B8C", "text-halo-color": "#FFFFFF"},
    "highway-name-path": {"text-color": INK_2, "text-halo-color": "#FFFFFF"},
    "highway-name-minor": {"text-color": INK_2, "text-halo-color": "#FFFFFF"},
    "highway-name-major": {"text-color": INK, "text-halo-color": "#FFFFFF"},
    "airport": {"text-color": INK_2, "text-halo-color": "#FFFFFF"},
}
PLACE_LABELS = ("label_other", "label_village", "label_town", "label_state", "label_city", "label_city_capital",
                "label_country_3", "label_country_2", "label_country_1")
LOCAL_NAME = ["coalesce", ["get", "name"], ["get", "name_en"]]


def local_names(value):
    """Swap Positron's English-first names for the local name ("İstanbul", not "Istanbul")."""
    if value == ["coalesce", ["get", "name_en"], ["get", "name"]]:
        return LOCAL_NAME
    if isinstance(value, list):
        return [local_names(item) for item in value]
    return value


def main() -> None:
    with urllib.request.urlopen(urllib.request.Request(SOURCE, headers={"User-Agent": "bikiyak-style/1.0"}), timeout=20) as r:
        style = json.load(r)
    style["name"] = "bikıyak minimal"
    style["sources"].pop("ne2_shaded", None)  # shaded relief is unused by these layers
    for layer in style["layers"]:
        layer.setdefault("paint", {}).update(COLOURS.get(layer["id"], {}))
        if layer["id"] in PLACE_LABELS:
            layer["paint"].update({"text-color": INK, "text-halo-color": "#FFFFFF", "text-halo-width": 1.4})
            layer.setdefault("layout", {})["text-font"] = ["Noto Sans Bold"]
        if "text-field" in layer.get("layout", {}):
            layer["layout"]["text-field"] = local_names(layer["layout"]["text-field"])
        if layer["id"] == "highway_motorway_inner":
            # Motorways read better slightly wider than Positron's hairlines (the casing is wider still).
            width = layer["paint"].get("line-width")
            if isinstance(width, dict) and "stops" in width:
                width["stops"] = [[z, round(w * 1.25, 2)] for z, w in width["stops"]]
            elif isinstance(width, list) and width[:1] == ["interpolate"]:
                # ["interpolate", curve, ["zoom"], z1, w1, z2, w2, ...]: widen every output.
                layer["paint"]["line-width"] = width[:3] + [v if i % 2 == 0 else round(v * 1.25, 2)
                                                            for i, v in enumerate(width[3:])]
    missing = sorted(set(COLOURS) - {layer["id"] for layer in style["layers"]})
    if missing:
        print("OpenFreeMap style no longer has:", ", ".join(missing))
    TARGET.write_text(json.dumps(style, ensure_ascii=False, separators=(",", ":")))
    print(f"{TARGET} ({TARGET.stat().st_size // 1024} KB, {len(style['layers'])} layers)")


if __name__ == "__main__":
    main()
