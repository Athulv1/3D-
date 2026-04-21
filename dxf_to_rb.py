"""
DXF -> SketchUp Ruby Script Generator (Universal Edition)
Reads a DXF floor plan and generates a build_floorplan.rb script
that creates a complete 3D model inside SketchUp (native .skp).

Usage:
    python dxf_to_rb.py <input.dxf> [output.rb]
    python dxf_to_rb.py --project-dir <project_dir>
"""

import sys
import json
import math
from pathlib import Path
import ezdxf

# ── Default fixture mapping (backward compat — used when no project config) ───
DEFAULT_FIXTURE_MAP = {
    "FINANCE_DESK":  ("FINANCE DESK#2.skp",      -90),
    "MOBILE":        ("MOBILE WALL GRAY.skp",    +90),
    "ACCESSORIES":   ("ACCESSORIES#6.skp",        -90),
    "CARE":          ("care logo.skp",             90),
    "TV_WALL":       ("SMART TV#3.skp",             0),
    "AC_WALL":       ("AIR CONDITIONETR.skp",       0),
    "CASH_COUNTER":  ("cash counter 210#1.skp",    90),
    "COUNTER":       ("MOBILW OWN COUNTER.skp",     0),
    "APPLE":         ("apple#3.skp",                0),
    "SAMSUNG":       ("SAMSUNG COUNTER.skp",       -90),
    "LAPTOP":        ("LAP TABLE.skp",            180),
    "VIVO":          ("MOBILE WALL GRAY.skp",     270),
    "OPPO":          ("MOBILE WALL GRAY.skp",     270),
    "XIAOMI":        ("MOBILE WALL GRAY.skp",     270),
}
DEFAULT_ASSETS_DIR = "C:/Users/athul/Documents/3d_gen/Assets"
DEFAULT_WALL_HEIGHT = 3000
DEFAULT_WALL_THICKNESS = 150
DEFAULT_LOCAL_CENTERS = {
    "FINANCE_DESK":  ( 34.910,  3.054),
    "MOBILE":        (  6.010, 19.716),
    "ACCESSORIES":   ( -6.899, 24.377),
    "CARE":          ( 17.943, 12.471),
    "TV_WALL":       ( 11.262,  1.797),
    "AC_WALL":       ( 25.238, 11.692),
    "CASH_COUNTER":  ( 26.083, 41.732),
    "COUNTER":       ( 29.527,  9.842),
    "APPLE":         ( 21.653, 31.496),
    "SAMSUNG":       ( 19.082, 36.799),
    "LAPTOP":        ( 45.541, 24.088),
    "VIVO":          (  6.010, 19.716),
    "OPPO":          (  6.010, 19.716),
    "XIAOMI":        (  6.010, 19.716),
}


# ── DXF Parsing ────────────────────────────────────────────────────

def parse_dxf(filepath):
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()

    outer_walls = []
    partitions  = []
    inserts     = []

    # Track furniture bounds to isolate the active plan
    furn_xs, furn_ys = [], []

    for e in msp:
        layer = e.dxf.layer.lower()
        if layer.startswith("pdf_"):
            continue

        if e.dxftype() == "LINE":
            # Use structural walls AND openings (doors/windows) so the floor outline remains a continuous closed polygon.
            if layer == "0walls" or layer == "0wall":
                outer_walls.append({
                    "x1": e.dxf.start.x, "y1": e.dxf.start.y,
                    "x2": e.dxf.end.x,   "y2": e.dxf.end.y,
                    "is_opening": False
                })
            elif "windor" in layer:
                outer_walls.append({
                    "x1": e.dxf.start.x, "y1": e.dxf.start.y,
                    "x2": e.dxf.end.x,   "y2": e.dxf.end.y,
                    "is_opening": True
                })
        elif e.dxftype() == "LWPOLYLINE":
            if "windor" in layer:
                # Parse door/window frame polylines — keep wall-parallel
                # edges as openings, skip short jamb-depth edges.
                wpts = [(p[0], p[1]) for p in e.get_points()]
                wn = len(wpts)
                wrng = range(wn) if e.closed else range(wn - 1)
                wedges = []
                for wi in wrng:
                    wp1 = wpts[wi]
                    wp2 = wpts[(wi + 1) % wn]
                    wlen = math.hypot(wp2[0] - wp1[0], wp2[1] - wp1[1])
                    wedges.append((wp1, wp2, wlen))
                if wedges:
                    max_len = max(we[2] for we in wedges)
                    for wp1, wp2, wlen in wedges:
                        if wlen >= max_len * 0.5:  # skip short jamb edges
                            outer_walls.append({
                                "x1": wp1[0], "y1": wp1[1],
                                "x2": wp2[0], "y2": wp2[1],
                                "is_opening": True
                            })
                continue
            pts = [(p[0], p[1]) for p in e.get_points()]
            if e.closed and len(pts) >= 3:
                # LWPOLYLINE on the wall layer → convert edges to wall segments
                if layer == "0walls" or layer == "0wall":
                    for i in range(len(pts)):
                        p1 = pts[i]
                        p2 = pts[(i + 1) % len(pts)]
                        outer_walls.append({
                            "x1": p1[0], "y1": p1[1],
                            "x2": p2[0], "y2": p2[1],
                            "is_opening": False
                        })
                    continue
                # Geometric Abstraction: Treat closed polylines on furniture layer as virtual blocks
                elif "furn" in layer:
                    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                    minx, maxx = min(xs), max(xs)
                    miny, maxy = min(ys), max(ys)
                    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
                    w, d = maxx - minx, maxy - miny
                    dim_max = round(max(w, d))
                    dim_min = round(min(w, d))
                    rot = 90.0 if d > w else 0.0
                    inserts.append({
                        "name":   f"Shape_{dim_max}x{dim_min}",
                        "x": cx, "y": cy, "z": 0.0,
                        "rot": rot, "xscale": 1.0, "yscale": 1.0, "zscale": 1.0,
                    })
                    furn_xs.extend(xs)
                    furn_ys.extend(ys)
                else:
                    partitions.append(pts)
        elif e.dxftype() == "CIRCLE":
            if "furn" in layer:
                r = e.dxf.radius
                diam = round(r * 2)
                cx, cy = e.dxf.center.x, e.dxf.center.y
                inserts.append({
                    "name":   f"Shape_Circle_{diam}",
                    "x": cx, "y": cy, "z": 0.0,
                    "rot": 0.0, "xscale": 1.0, "yscale": 1.0, "zscale": 1.0,
                })
                furn_xs.extend([cx - r, cx + r])
                furn_ys.extend([cy - r, cy + r])
        elif e.dxftype() == "INSERT":
            import re as _re
            name = _re.sub(r'_\d+$', '', e.dxf.name)
            inserts.append({
                "name":   name,
                "x":      e.dxf.insert.x,
                "y":      e.dxf.insert.y,
                "z":      getattr(e.dxf.insert, 'z', 0.0),
                "rot":    e.dxf.get("rotation", 0.0),
                "xscale": e.dxf.get("xscale", 1.0),
                "yscale": e.dxf.get("yscale", 1.0),
                "zscale": e.dxf.get("zscale", 1.0),
            })
            furn_xs.append(e.dxf.insert.x)
            furn_ys.append(e.dxf.insert.y)

    # --- Dual-Plan Isolation ---
    # Crop walls to only the region that contains furniture (plus a 1000mm padding)
    if furn_xs and furn_ys:
        margin = 10.0
        min_x, max_x = min(furn_xs) - margin, max(furn_xs) + margin
        min_y, max_y = min(furn_ys) - margin, max(furn_ys) + margin

        def in_bounds(x, y):
            return min_x <= x <= max_x and min_y <= y <= max_y

        outer_walls = [w for w in outer_walls if in_bounds(w["x1"], w["y1"]) or in_bounds(w["x2"], w["y2"])]
        partitions = [p for p in partitions if any(in_bounds(pt[0], pt[1]) for pt in p)]

    # --- Auto-Detect Units (Centimeters to Millimeters correction) ---
    # Most floor plans are > 5000mm. If the span is small, it was likely drawn in cm or inches.
    dxf_span = 0
    if outer_walls:
        all_x = [w["x1"] for w in outer_walls] + [w["x2"] for w in outer_walls]
        dxf_span = max(all_x) - min(all_x)
        
    dxf_multiplier = 1.0
    if 100 < dxf_span < 4000:
        print("  WARNING: DXF span is extremely small. Auto-detecting units as CENTIMETERS (x10).")
        dxf_multiplier = 10.0
        
    if dxf_multiplier != 1.0:
        for w in outer_walls:
            w["x1"] *= dxf_multiplier; w["y1"] *= dxf_multiplier
            w["x2"] *= dxf_multiplier; w["y2"] *= dxf_multiplier
        partitions = [[(pt[0]*dxf_multiplier, pt[1]*dxf_multiplier) for pt in p] for p in partitions]
        for ins in inserts:
            ins["x"] *= dxf_multiplier
            ins["y"] *= dxf_multiplier

    # --- Close wall gaps ---
    # DXF wall segments often don't perfectly connect at corners or
    # junctions.  Find dangling endpoints and add short connecting
    # segments to close gaps up to max_gap mm.
    from collections import Counter as _Counter
    max_gap = 600  # mm (after unit scaling)
    ep_list = []
    for w in outer_walls:
        ep_list.append((round(w["x1"]), round(w["y1"])))
        ep_list.append((round(w["x2"]), round(w["y2"])))
    ep_counts = _Counter(ep_list)
    dangling = {pt for pt, c in ep_counts.items() if c == 1}

    # Map rounded → exact coordinates
    exact = {}
    for w in outer_walls:
        rp1 = (round(w["x1"]), round(w["y1"]))
        rp2 = (round(w["x2"]), round(w["y2"]))
        if rp1 in dangling:
            exact[rp1] = (w["x1"], w["y1"])
        if rp2 in dangling:
            exact[rp2] = (w["x2"], w["y2"])

    used = set()
    gap_fills = []
    for p1 in sorted(dangling):
        if p1 in used:
            continue
        best_d, best_p = max_gap + 1, None
        for p2 in dangling:
            if p2 == p1 or p2 in used:
                continue
            d = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            if d < best_d:
                best_d, best_p = d, p2
        if best_p and best_d <= max_gap:
            e1, e2 = exact[p1], exact[best_p]
            gap_fills.append({
                "x1": e1[0], "y1": e1[1],
                "x2": e2[0], "y2": e2[1],
                "is_opening": False
            })
            used.add(p1)
            used.add(best_p)

    if gap_fills:
        outer_walls.extend(gap_fills)
        print(f"  Auto-closed {len(gap_fills)} wall gaps")

    print(f"  Outer wall segments : {len(outer_walls)}")
    print(f"  Partition polylines : {len(partitions)}")
    print(f"  Fixture inserts     : {len(inserts)}")
    return outer_walls, partitions, inserts


# ── Wall height detection from DXF ────────────────────────────────

def detect_wall_height(filepath):
    """Try to detect wall height from DXF metadata. Returns mm or None."""
    try:
        doc = ezdxf.readfile(filepath)
        # Check header for thickness
        try:
            thickness = doc.header.get("$THICKNESS", 0)
            if thickness and float(thickness) > 100:
                return float(thickness)
        except Exception:
            pass
        # Check for non-zero Z in 3D entities
        msp = doc.modelspace()
        max_z = 0
        for e in msp:
            try:
                if hasattr(e.dxf, 'start') and e.dxf.start.z > max_z:
                    max_z = e.dxf.start.z
                if hasattr(e.dxf, 'end') and e.dxf.end.z > max_z:
                    max_z = e.dxf.end.z
            except Exception:
                pass
        if 2000 <= max_z <= 8000:
            return max_z
        elif max_z > 8000:
            # If it's something crazy like 40000, ignore it and let it fall back to default
            print(f"  WARNING: Detected wall height {max_z} is unreasonably high. Using default.")
            return None
    except Exception:
        pass
    return None


# ── Hardcoded SSK CEI LAB design-rule mappings (always applied first) ──
HARDCODED_FIXTURE_MAP = {
    "Shape_120x120":  "Component_5.skp",
    "Shape_275x60":   "Component_6.skp",
    "Shape_90x10":    "tool board#1.skp",
    "Shape_90x45":    "shelf#1.skp",
    "Shape_Circle_50": "Wooden Stool.skp",
}


# ── Auto-mapping: DXF block names → extracted asset filenames ─────

def auto_map_fixtures(dxf_block_names, asset_manifest):
    """
    Try to auto-match DXF block names to extracted assets.
    Returns {"matched": {name: {asset_file, rotation_offset, local_center}}, "unmatched": [...]}
    """
    HARDCODED = HARDCODED_FIXTURE_MAP

    matched = {}
    unmatched = []

    # Index manifest by filename for local_center lookups
    asset_by_file = {}
    for asset in asset_manifest:
        asset_by_file[asset["filename"]] = asset

    # Apply hardcoded mappings first
    for dxf_name in list(dxf_block_names):
        if dxf_name in HARDCODED:
            skp = HARDCODED[dxf_name]
            a = asset_by_file.get(skp, {})
            matched[dxf_name] = {
                "asset_file": skp,
                "rotation_offset": 0,
                "local_center": [a.get("local_center_x", 0), a.get("local_center_y", 0)],
            }

    # Build lookup from asset manifest
    asset_by_lower = {}
    for asset in asset_manifest:
        key = asset["name"].lower().replace(" ", "_").replace("#", "")
        asset_by_lower[key] = asset
        # Also index by filename stem
        stem = Path(asset["filename"]).stem.lower().replace(" ", "_").replace("#", "")
        asset_by_lower[stem] = asset

    for dxf_name in dxf_block_names:
        if dxf_name in matched:
            continue  # already handled by hardcoded mapping
        dxf_lower = dxf_name.lower().replace(" ", "_").replace("#", "")

        # 1. Exact match
        if dxf_lower in asset_by_lower:
            a = asset_by_lower[dxf_lower]
            matched[dxf_name] = {
                "asset_file": a["filename"],
                "rotation_offset": 0,
                "local_center": [a.get("local_center_x", 0), a.get("local_center_y", 0)],
            }
            continue

        # 2. Substring match (either direction)
        best = None
        best_len = 0
        for akey, asset in asset_by_lower.items():
            if dxf_lower in akey or akey in dxf_lower:
                overlap = len(dxf_lower) if dxf_lower in akey else len(akey)
                if overlap > best_len:
                    best_len = overlap
                    best = asset

        if best and best_len >= 3:
            matched[dxf_name] = {
                "asset_file": best["filename"],
                "rotation_offset": 0,
                "local_center": [best.get("local_center_x", 0), best.get("local_center_y", 0)],
            }
        else:
            unmatched.append(dxf_name)

    return {"matched": matched, "unmatched": unmatched}


# ── Inward normal calculation ──────────────────────────────────────

def compute_centroid(segments):
    xs = [s["x1"] for s in segments] + [s["x2"] for s in segments]
    ys = [s["y1"] for s in segments] + [s["y2"] for s in segments]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def inward_normal(x1, y1, x2, y2, floor_polygon, test_dist=200):
    from shapely.geometry import Point
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 0.0, 0.0
    nx1, ny1 =  dy / length, -dx / length
    nx2, ny2 = -dy / length,  dx / length
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    test1 = Point(mx + nx1 * test_dist, my + ny1 * test_dist)
    if floor_polygon.contains(test1):
        return nx1, ny1
    return nx2, ny2


# ── Partition wall edges ───────────────────────────────────────────

def partition_edges(partitions, outer_walls, tolerance=20.0):
    outer_set = set()
    for s in outer_walls:
        key = tuple(sorted([(round(s["x1"]), round(s["y1"])),
                             (round(s["x2"]), round(s["y2"]))]))
        outer_set.add(key)

    internal = []
    for poly in partitions:
        n = len(poly)
        for i in range(n):
            p1 = poly[i]
            p2 = poly[(i + 1) % n]
            key = tuple(sorted([(round(p1[0]), round(p1[1])),
                                  (round(p2[0]), round(p2[1]))]))
            if key not in outer_set:
                internal.append((p1[0], p1[1], p2[0], p2[1]))

    seen = set()
    unique = []
    for e in internal:
        if abs(e[0] - e[2]) < 1 and abs(e[1] - e[3]) < 1:
            continue
        k = tuple(sorted([(round(e[0]), round(e[1])), (round(e[2]), round(e[3]))]))
        if k not in seen:
            seen.add(k)
            unique.append(e)
    print(f"  Internal partition edges: {len(unique)}")
    return unique


# ── Floor outline ──────────────────────────────────────────────────

def floor_outline(outer_walls):
    if not outer_walls:
        return []

    xs = [s["x1"] for s in outer_walls] + [s["x2"] for s in outer_walls]
    ys = [s["y1"] for s in outer_walls] + [s["y2"] for s in outer_walls]

    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)

    return [
        (minx, miny),
        (maxx, miny),
        (maxx, maxy),
        (minx, maxy)
    ]


# ── Walkthrough JSON generation ───────────────────────────────────

def generate_walkthrough_json(floor_pts_mm, save_path,
                               eye_height_in=66.0, inset_in=60.0, spacing_in=25.0):
    import json as _json
    from shapely.geometry import Polygon

    pts_in = [(x / 25.4, y / 25.4) for x, y in floor_pts_mm]
    poly   = Polygon(pts_in)
    inner  = poly.buffer(-inset_in)

    if inner.is_empty or inner.area < 1:
        print("  WARNING: inset too large, using original outline for walkthrough")
        inner = poly

    from shapely.geometry import MultiPolygon
    if isinstance(inner, MultiPolygon):
        inner = max(inner.geoms, key=lambda g: g.area)

    ring         = inner.exterior
    total_length = ring.length
    n_points     = max(6, int(total_length / spacing_in))

    waypoints = []
    for i in range(n_points):
        d      = (i / n_points) * total_length
        d_next = ((i + 1) / n_points) * total_length
        pt     = ring.interpolate(d)
        pt_nxt = ring.interpolate(d_next)
        waypoints.append({
            "name":   f"Walkthrough_{str(i + 1).zfill(3)}",
            "eye":    {"x": round(pt.x, 4),     "y": round(pt.y, 4),     "z": eye_height_in},
            "target": {"x": round(pt_nxt.x, 4), "y": round(pt_nxt.y, 4), "z": eye_height_in},
            "up":     {"x": 0, "y": 0, "z": 1},
        })

    data = {
        "transition_time": 0.3,
        "delay_time":      0.0,
        "waypoints":       waypoints,
    }
    Path(save_path).write_text(_json.dumps(data, indent=2), encoding="utf-8")
    print(f"  Walkthrough waypoints: {len(waypoints)} points -> {Path(save_path).name}")
    return save_path


# ── Ruby code generation ───────────────────────────────────────────

def mm_to_in(v):
    return f"{v / 25.4:.6f}"


def rb_point(x_mm, y_mm, z_mm=0):
    return f"Geom::Point3d.new({mm_to_in(x_mm)}, {mm_to_in(y_mm)}, {mm_to_in(z_mm)})"


def generate_ruby(outer_walls, internal_edges, inserts, floor_pts,
                  wall_height, wall_thickness, fixture_map, assets_dir,
                  position_offsets=None, save_path=None):
    from shapely.geometry import Polygon as ShapelyPolygon
    floor_polygon = ShapelyPolygon(floor_pts) if floor_pts else None
    wall_h = mm_to_in(wall_height)
    wall_t = mm_to_in(wall_thickness)
    lines = []

    lines.append("# Auto-generated SketchUp Floor Plan Builder")
    lines.append("# Run: Window > Ruby Console, then: load 'C:/path/to/build_floorplan.rb'")
    lines.append("")

    lines.append("_build = proc do")
    lines.append("  model = Sketchup.active_model")
    lines.append("  model.start_operation('Build Floor Plan', true)")
    lines.append("  ents  = model.active_entities")
    lines.append("  ents.clear!")
    lines.append("  model.definitions.purge_unused")
    lines.append("")

    lines.append(f"  wall_h = {wall_h}  # wall height (inches)")
    lines.append(f"  wall_t = {wall_t}  # wall thickness (inches)")
    lines.append("")

    # Use unique material names based on timestamp to evade SketchUp's material collision checking
    lines.append("  unique_ts = Time.now.to_i.to_s")
    lines.append("  wall_mat = model.materials.add('wall_' + unique_ts)")
    lines.append("  wall_mat.color = [215, 208, 198]")
    lines.append("  build_wall = lambda do |x1, y1, x2, y2, nx, ny|")
    lines.append("    pts = [")
    lines.append("      Geom::Point3d.new(x1,             y1,             0),")
    lines.append("      Geom::Point3d.new(x2,             y2,             0),")
    lines.append("      Geom::Point3d.new(x2 + nx*wall_t, y2 + ny*wall_t, 0),")
    lines.append("      Geom::Point3d.new(x1 + nx*wall_t, y1 + ny*wall_t, 0),")
    lines.append("    ]")
    lines.append("    face = ents.add_face(pts)")
    lines.append("    if face.is_a?(Sketchup::Face)")
    lines.append("      face.reverse! if face.normal.z > 0")
    lines.append("      face.material = wall_mat")
    lines.append("      face.pushpull(-wall_h)")
    lines.append("    end")
    lines.append("  end")
    lines.append("")
    # Header wall builder for door/window openings — fills the gap above opening height
    lines.append("  opening_h = wall_h * 0.75  # door/window height = 75% of wall")
    lines.append("  build_opening_header = lambda do |x1, y1, x2, y2, nx, ny|")
    lines.append("    pts = [")
    lines.append("      Geom::Point3d.new(x1,             y1,             opening_h),")
    lines.append("      Geom::Point3d.new(x2,             y2,             opening_h),")
    lines.append("      Geom::Point3d.new(x2 + nx*wall_t, y2 + ny*wall_t, opening_h),")
    lines.append("      Geom::Point3d.new(x1 + nx*wall_t, y1 + ny*wall_t, opening_h),")
    lines.append("    ]")
    lines.append("    face = ents.add_face(pts)")
    lines.append("    if face.is_a?(Sketchup::Face)")
    lines.append("      face.reverse! if face.normal.z > 0")
    lines.append("      face.material = wall_mat")
    lines.append("      face.pushpull(-(wall_h - opening_h))")
    lines.append("    end")
    lines.append("  end")
    lines.append("")

    if floor_pts:
        lines.append("  # --- Floor ---")
        pts_rb = ", ".join(
            f"Geom::Point3d.new({mm_to_in(x)}, {mm_to_in(y)}, 0)"
            for x, y in floor_pts
        )
        lines.append("  floor_mat = model.materials.add('floor_' + unique_ts)")
        lines.append("  floor_mat.color = [200, 195, 185]")
        lines.append(f"  floor_face = ents.add_face([{pts_rb}])")
        lines.append("  floor_face.material = floor_mat if floor_face.is_a?(Sketchup::Face)")
        lines.append("")

    lines.append("  # --- Outer walls ---")
    for s in outer_walls:
        x1, y1, x2, y2 = s["x1"], s["y1"], s["x2"], s["y2"]
        if math.hypot(x2 - x1, y2 - y1) < 1:
            continue
        nx, ny = inward_normal(x1, y1, x2, y2, floor_polygon)
        if s.get("is_opening"):
            # Door/window: build header wall above opening height (no gap at top)
            lines.append(
                f"  build_opening_header.call({mm_to_in(x1)}, {mm_to_in(y1)}, "
                f"{mm_to_in(x2)}, {mm_to_in(y2)}, {nx:.4f}, {ny:.4f})"
            )
        else:
            lines.append(
                f"  build_wall.call({mm_to_in(x1)}, {mm_to_in(y1)}, "
                f"{mm_to_in(x2)}, {mm_to_in(y2)}, {nx:.4f}, {ny:.4f})"
            )
    lines.append("")

    if internal_edges:
        lines.append("  # --- Internal partition walls ---")
        for x1, y1, x2, y2 in internal_edges:
            if math.hypot(x2 - x1, y2 - y1) < 1:
                continue
            nx, ny = inward_normal(x1, y1, x2, y2, floor_polygon)
            lines.append(
                f"  build_wall.call({mm_to_in(x1)}, {mm_to_in(y1)}, "
                f"{mm_to_in(x2)}, {mm_to_in(y2)}, {nx:.4f}, {ny:.4f})"
            )
        lines.append("")

    lines.append("  # --- Fixture map ---")
    lines.append("  assets_dir  = '" + assets_dir.replace("'", "\\'") + "'")
    lines.append("  fixture_map = {")
    for dxf_name, (skp_file, base_rot) in fixture_map.items():
        lines.append(f"    '{dxf_name}' => ['{skp_file}', {base_rot}],")
    lines.append("  }")
    lines.append("")

    lines.append("  place_fixture = lambda do |dxf_name, x_in, y_in, dxf_rot, xs, ys, zs|")
    lines.append("    entry = fixture_map[dxf_name]")
    lines.append("    next unless entry")
    lines.append("    skp_file, base_rot = entry")
    lines.append("    path = File.join(assets_dir, skp_file)")
    lines.append("    next unless File.exist?(path)")
    lines.append("    defn = model.definitions.load(path)")
    lines.append("    next unless defn")
    lines.append("    total_rad = (dxf_rot + base_rot) * Math::PI / 180.0")
    lines.append("    t_scale  = Geom::Transformation.scaling(ORIGIN, xs, ys, zs)")
    lines.append("    t_rotate = Geom::Transformation.rotation(ORIGIN, Z_AXIS, total_rad)")
    lines.append("    t_move   = Geom::Transformation.translation(Geom::Vector3d.new(x_in, y_in, 0))")
    lines.append("    ents.add_instance(defn, t_move * t_rotate * t_scale)")
    lines.append("  end")
    lines.append("")

    lines.append("  # --- Fixture placements ---")
    mapped   = [i for i in inserts if i["name"] in fixture_map]
    unmapped = [i for i in inserts if i["name"] not in fixture_map]

    local_centers = position_offsets or {}
    for ins in mapped:
        x_in = ins["x"] / 25.4
        y_in = ins["y"] / 25.4
        skp_file, base_rot = fixture_map[ins["name"]]
        lc = local_centers.get(ins["name"])
        if lc:
            cx, cy = lc
            total_rad = math.radians(ins["rot"] + base_rot)
            rot_cx = math.cos(total_rad) * cx - math.sin(total_rad) * cy
            rot_cy = math.sin(total_rad) * cx + math.cos(total_rad) * cy
            x_in -= rot_cx
            y_in -= rot_cy
        lines.append(
            f"  place_fixture.call('{ins['name']}', "
            f"{x_in:.6f}, {y_in:.6f}, {ins['rot']:.2f}, "
            f"{ins['xscale']:.3f}, {ins['yscale']:.3f}, {ins['zscale']:.3f})"
            f"  # DXF rot={ins['rot']:.0f} + base={base_rot} = {ins['rot']+base_rot:.0f} deg"
        )

    if unmapped:
        lines.append("")
        lines.append("  # Unmapped blocks (no fixture file assigned):")
        for ins in unmapped:
            lines.append(f"  # UNMAPPED: {ins['name']}  at ({ins['x']:.0f}, {ins['y']:.0f})")

    lines.append("")
    if save_path:
        save_path_rb = save_path.replace("\\", "/")
        lines.append('  entity_count = ents.length')
        lines.append('  model.commit_operation')
        lines.append(f'  model.save("{save_path_rb}")')
        lines.append('  UI.messagebox("Floor plan built and saved!  " + entity_count.to_s + " entities.\\nSaved to: ' + save_path_rb + '")')
    else:
        lines.append('  model.commit_operation')
        lines.append('  UI.messagebox("Floor plan built!  " + ents.length.to_s + " entities created.")')

    lines.append("end")
    lines.append("")
    lines.append("_build.call")

    return "\n".join(lines)


# ── Project-based generation ───────────────────────────────────────

def generate_from_project(project_dir):
    """
    Generate floor plan from project configuration.
    Called by app.py for multi-project workflows.
    Returns a dict with build details.
    """
    project_dir = Path(project_dir)
    config = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))

    dxf_path   = str(project_dir / "source.dxf")
    assets_dir = str(project_dir / "assets").replace("\\", "/")
    output_dir = project_dir / "output"
    output_dir.mkdir(exist_ok=True)

    rb_path       = str(output_dir / "build_floorplan.rb")
    skp_save_path = str(output_dir / "build_floorplan.skp")
    json_path     = str(output_dir / "walkthrough_waypoints.json")

    # Load manifest for local centers
    manifest_path = project_dir / "assets_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []

    # Build fixture_map and local_centers from project config
    fixture_map   = {}
    local_centers = {}
    for dxf_name, entry in config.get("fixture_mapping", {}).items():
        fixture_map[dxf_name] = (entry["asset_file"], entry.get("rotation_offset", 0))
        lc = entry.get("local_center")
        if lc and len(lc) == 2:
            local_centers[dxf_name] = (lc[0], lc[1])

    # Enforce hardcoded design-rule mappings (always override stale config)
    for dxf_name, skp_file in HARDCODED_FIXTURE_MAP.items():
        fixture_map[dxf_name] = (skp_file, 0)

    wall_height    = config.get("wall_height", DEFAULT_WALL_HEIGHT)
    wall_thickness = config.get("wall_thickness", DEFAULT_WALL_THICKNESS)

    print(f"\n[1/3] Parsing: {dxf_path}")
    outer_walls, partitions, inserts = parse_dxf(dxf_path)

    print(f"\n[2/3] Building geometry data...")
    floor_pts      = floor_outline(outer_walls)
    internal_edges = partition_edges(partitions, outer_walls)
    print(f"  Floor outline points: {len(floor_pts)}")

    print(f"\n[3/3] Generating Ruby script + walkthrough...")
    rb_code = generate_ruby(
        outer_walls, internal_edges, inserts, floor_pts,
        wall_height, wall_thickness, fixture_map, assets_dir,
        local_centers, skp_save_path
    )

    Path(rb_path).write_text(rb_code, encoding="utf-8")
    generate_walkthrough_json(floor_pts, json_path)

    mapped   = sum(1 for i in inserts if i["name"] in fixture_map)
    unmapped = len(inserts) - mapped

    return {
        "walls": f"{len(outer_walls)} outer + {len(internal_edges)} internal",
        "fixtures": f"{mapped} mapped / {unmapped} unmapped",
        "floor_points": len(floor_pts),
        "output": rb_path,
    }


# ── CLI Main (backward compat) ────────────────────────────────────

def main():
    # Project-dir mode
    if "--project-dir" in sys.argv:
        idx = sys.argv.index("--project-dir")
        if idx + 1 < len(sys.argv):
            result = generate_from_project(sys.argv[idx + 1])
            print(f"\n  Result: {result}")
            return

    if len(sys.argv) < 2:
        dxf_files = list(Path(".").glob("*.dxf"))
        if not dxf_files:
            print("Usage: python dxf_to_rb.py <input.dxf> [output.rb]")
            sys.exit(1)
        pref = [f for f in dxf_files if "t_shape" in f.name.lower()]
        dxf_path = str(pref[0] if pref else dxf_files[0])
    else:
        dxf_path = sys.argv[1]

    rb_path = sys.argv[2] if len(sys.argv) > 2 else str(
        Path(dxf_path).with_suffix(".rb")
    )
    skp_save_path = str(Path(rb_path).with_suffix(".skp"))

    print(f"\n{'='*55}")
    print(f"  DXF to SketchUp Ruby Generator")
    print(f"{'='*55}")
    print(f"\n[1/3] Parsing: {dxf_path}")
    outer_walls, partitions, inserts = parse_dxf(dxf_path)

    print(f"\n[2/3] Building geometry data...")
    floor_pts      = floor_outline(outer_walls)
    internal_edges = partition_edges(partitions, outer_walls)
    print(f"  Floor outline points: {len(floor_pts)}")

    print(f"\n[3/3] Generating Ruby script + walkthrough waypoints...")
    rb_code = generate_ruby(
        outer_walls, internal_edges, inserts, floor_pts,
        DEFAULT_WALL_HEIGHT, DEFAULT_WALL_THICKNESS,
        DEFAULT_FIXTURE_MAP, DEFAULT_ASSETS_DIR,
        DEFAULT_LOCAL_CENTERS, skp_save_path
    )

    Path(rb_path).write_text(rb_code, encoding="utf-8")
    json_path = str(Path(rb_path).parent / "walkthrough_waypoints.json")
    generate_walkthrough_json(floor_pts, json_path)

    mapped   = sum(1 for i in inserts if i["name"] in DEFAULT_FIXTURE_MAP)
    unmapped = len(inserts) - mapped

    print(f"\n{'='*55}")
    print(f"  Output : {rb_path}")
    print(f"  Walls  : {len(outer_walls)} outer + {len(internal_edges)} internal")
    print(f"  Fixtures: {mapped} mapped / {unmapped} unmapped")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
