"""
DXF → SketchUp Ruby Script Generator
Reads a DXF floor plan and generates a build_floorplan.rb script
that creates a complete 3D model inside SketchUp (native .skp).

Usage:
    python dxf_to_rb.py <input.dxf> [output.rb]
"""

import sys
import math
from pathlib import Path
import ezdxf

# ── Fixture mapping: DXF block name → (Asset filename, base_rotation_offset_deg)
# base_rotation_offset corrects for each fixture's internal SketchUp orientation.
# Final rotation applied = DXF_rotation + base_rotation_offset
FIXTURE_MAP = {
    "FINANCE_DESK":  ("FINANCE DESK#2.skp",      -90),  # purple: was 0, needs -90
    "MOBILE":        ("MOBILE WALL GRAY.skp",    +90),  # confirmed OK
    "ACCESSORIES":   ("ACCESSORIES#6.skp",        -90),  # canonical front = east: dxf90+(-90)=0 → right wall faces room; dxf-90+(-90)=-180 → left wall faces room
    "CARE":          ("care logo.skp",             90),  # face right side
    "TV_WALL":       ("SMART TV#3.skp",             0),  # confirmed OK
    "AC_WALL":       ("AIR CONDITIONETR.skp",       0),  # flip front/back: was 180 → 0
    "CASH_COUNTER":  ("cash counter 210#1.skp",    90),  # total = DXF90+90 = 180
    "COUNTER":       ("MOBILW OWN COUNTER.skp",     0),  # confirmed OK
    "APPLE":         ("apple#3.skp",                0),  # confirmed OK
    "SAMSUNG":       ("SAMSUNG COUNTER.skp",       -90),  # fix position: was 90 → -90
    "LAPTOP":        ("LAP TABLE.skp",            180),  # confirmed OK
    "VIVO":          ("MOBILE WALL GRAY.skp",     270),  # confirmed OK
    "OPPO":          ("MOBILE WALL GRAY.skp",     270),  # confirmed OK
    "XIAOMI":        ("MOBILE WALL GRAY.skp",     270),  # confirmed OK
}

ASSETS_DIR = "C:/Users/athul/Documents/3d_gen/Assets"
WALL_HEIGHT = 3000    # mm — standard retail ceiling
WALL_THICKNESS = 150  # mm

# ── Per-fixture local center offsets (inches in component's LOCAL space).
# Computed from SketchUp bounds diagnostic: inverse-rotate (ctr - ins) back to local.
# Applied as rotation-aware correction so visual center lands on DXF INSERT point.
LOCAL_CENTERS = {
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


# ── DXF Parsing ────────────────────────────────────────────────────────────

def parse_dxf(filepath):
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()

    outer_walls = []    # LINE entities → outer boundary segments
    partitions  = []    # LWPOLYLINE closed → room dividers
    inserts     = []    # INSERT entities → fixture placements

    for e in msp:
        if e.dxftype() == "LINE":
            outer_walls.append({
                "x1": e.dxf.start.x, "y1": e.dxf.start.y,
                "x2": e.dxf.end.x,   "y2": e.dxf.end.y,
            })
        elif e.dxftype() == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points()]
            if e.closed and len(pts) >= 3:
                partitions.append(pts)
        elif e.dxftype() == "INSERT":
            # Strip trailing _1, _2, _N suffix so "MOBILE_1" matches "MOBILE" in FIXTURE_MAP
            import re as _re
            name = _re.sub(r'_\d+$', '', e.dxf.name)
            inserts.append({
                "name":   name,
                "x":      e.dxf.insert.x,
                "y":      e.dxf.insert.y,
                "z":      e.dxf.insert.z,
                "rot":    e.dxf.get("rotation", 0.0),
                "xscale": e.dxf.get("xscale", 1.0),
                "yscale": e.dxf.get("yscale", 1.0),
                "zscale": e.dxf.get("zscale", 1.0),
            })

    print(f"  Outer wall segments : {len(outer_walls)}")
    print(f"  Partition polylines : {len(partitions)}")
    print(f"  Fixture inserts     : {len(inserts)}")
    return outer_walls, partitions, inserts


# ── Inward normal calculation ──────────────────────────────────────────────

def compute_centroid(segments):
    """Centroid of all wall segment endpoints — used to determine inward direction."""
    xs = [s["x1"] for s in segments] + [s["x2"] for s in segments]
    ys = [s["y1"] for s in segments] + [s["y2"] for s in segments]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def inward_normal(x1, y1, x2, y2, floor_polygon, test_dist=200):
    """
    Returns the unit normal (nx, ny) perpendicular to segment (x1,y1)→(x2,y2)
    pointing INTO the building interior, using a point-in-polygon test.
    Works correctly for non-convex (T-, L-, U-shaped) floor plans.
    """
    from shapely.geometry import Point
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 0.0, 0.0
    nx1, ny1 =  dy / length, -dx / length
    nx2, ny2 = -dy / length,  dx / length
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    # Test which perpendicular points inside the floor polygon
    test1 = Point(mx + nx1 * test_dist, my + ny1 * test_dist)
    if floor_polygon.contains(test1):
        return nx1, ny1
    return nx2, ny2


# ── Partition wall edges ───────────────────────────────────────────────────

def partition_edges(partitions, outer_walls, tolerance=20.0):
    """
    Extract only the truly internal edges from room-boundary polylines
    (skip edges that coincide with outer walls).
    Returns list of (x1,y1, x2,y2) tuples.
    """
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

    # Remove zero-length edges and deduplicate
    seen = set()
    unique = []
    for e in internal:
        # Skip zero-length edges
        if abs(e[0] - e[2]) < 1 and abs(e[1] - e[3]) < 1:
            continue
        k = tuple(sorted([(round(e[0]), round(e[1])), (round(e[2]), round(e[3]))]))
        if k not in seen:
            seen.add(k)
            unique.append(e)
    print(f"  Internal partition edges: {len(unique)}")
    return unique


# ── Floor outline ──────────────────────────────────────────────────────────

def floor_outline(outer_walls):
    """
    Build an ordered polygon from the outer wall LINE segments
    by walking the connected endpoints.
    """
    segments = [(s["x1"], s["y1"], s["x2"], s["y2"]) for s in outer_walls]
    if not segments:
        return []

    # Build adjacency map
    adj = {}
    for x1, y1, x2, y2 in segments:
        p1, p2 = (round(x1), round(y1)), (round(x2), round(y2))
        adj.setdefault(p1, []).append(p2)
        adj.setdefault(p2, []).append(p1)

    # Walk the boundary
    start = list(adj.keys())[0]
    path = [start]
    prev = None
    current = start
    for _ in range(len(segments)):
        neighbours = [n for n in adj[current] if n != prev]
        if not neighbours:
            break
        nxt = neighbours[0]
        if nxt == start:
            break
        path.append(nxt)
        prev, current = current, nxt
    return path


# ── Walkthrough JSON generation ───────────────────────────────────────────

def generate_walkthrough_json(floor_pts_mm, save_path,
                               eye_height_in=66.0, inset_in=60.0, spacing_in=80.0):
    """
    Generates walkthrough_waypoints.json from the floor outline.
    Path = inset polygon ring, sampled every spacing_in inches.
    Eye height = eye_height_in inches (person eye level).
    """
    import json
    from shapely.geometry import Polygon

    pts_in = [(x / 25.4, y / 25.4) for x, y in floor_pts_mm]
    poly   = Polygon(pts_in)
    inner  = poly.buffer(-inset_in)

    if inner.is_empty or inner.area < 1:
        print("  WARNING: inset too large, using original outline for walkthrough")
        inner = poly

    # Use exterior ring for single-polygon result
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
        "transition_time": 2.0,
        "delay_time":      0.5,
        "waypoints":       waypoints,
    }
    Path(save_path).write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"  Walkthrough waypoints: {len(waypoints)} points -> {Path(save_path).name}")
    return save_path


# ── Ruby code generation ───────────────────────────────────────────────────

def mm_to_in(v):
    """Format mm value as Ruby inches expression."""
    return f"{v / 25.4:.6f}"


def rb_point(x_mm, y_mm, z_mm=0):
    return f"Geom::Point3d.new({mm_to_in(x_mm)}, {mm_to_in(y_mm)}, {mm_to_in(z_mm)})"


def generate_ruby(outer_walls, internal_edges, inserts, floor_pts,
                  wall_height, wall_thickness, fixture_map, assets_dir,
                  position_offsets=None, save_path=None):
    from shapely.geometry import Polygon as ShapelyPolygon
    # Build floor polygon for accurate inward-normal point-in-polygon checks
    floor_polygon = ShapelyPolygon(floor_pts) if floor_pts else None
    wall_h = mm_to_in(wall_height)
    wall_t = mm_to_in(wall_thickness)
    lines = []

    # Use plain ASCII only — SketchUp Ruby parser rejects non-ASCII in source
    lines.append("# Auto-generated SketchUp Floor Plan Builder")
    lines.append("# Run: Window > Ruby Console, then: load 'C:/path/to/build_floorplan.rb'")
    lines.append("")

    # Wrap everything in a proc so all variables stay local (no constants, no def)
    lines.append("_build = proc do")
    lines.append("  model = Sketchup.active_model")
    lines.append("  model.start_operation('Build Floor Plan', true)")
    lines.append("  ents  = model.active_entities")
    lines.append("  ents.clear!")
    lines.append("  model.definitions.purge_unused")
    lines.append("")

    # ── Wall dimensions (local variables, not constants) ──────────────────
    lines.append(f"  wall_h = {wall_h}  # wall height (inches)")
    lines.append(f"  wall_t = {wall_t}  # wall thickness (inches)")
    lines.append("")

    # ── Inline wall builder lambda (closes over ents) ─────────────────────
    lines.append("  wall_mat = model.materials.add('wall')")
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
    lines.append("      # Walls going in +Y direction create a CCW face (normal = +Z).")
    lines.append("      # pushpull(-wall_h) on a +Z face goes DOWN. Reverse so it always goes UP.")
    lines.append("      face.reverse! if face.normal.z > 0")
    lines.append("      face.material = wall_mat")
    lines.append("      face.pushpull(-wall_h)")
    lines.append("    end")
    lines.append("  end")
    lines.append("")

    # ── Floor face ────────────────────────────────────────────────────────
    if floor_pts:
        lines.append("  # --- Floor ---")
        pts_rb = ", ".join(
            f"Geom::Point3d.new({mm_to_in(x)}, {mm_to_in(y)}, 0)"
            for x, y in floor_pts
        )
        lines.append("  floor_mat = model.materials.add('floor')")
        lines.append("  floor_mat.color = [200, 195, 185]")
        lines.append(f"  floor_face = ents.add_face([{pts_rb}])")
        lines.append("  floor_face.material = floor_mat if floor_face.is_a?(Sketchup::Face)")
        lines.append("")

    # ── Outer walls ───────────────────────────────────────────────────────
    lines.append("  # --- Outer walls ---")
    for s in outer_walls:
        x1, y1, x2, y2 = s["x1"], s["y1"], s["x2"], s["y2"]
        if math.hypot(x2 - x1, y2 - y1) < 1:
            continue
        nx, ny = inward_normal(x1, y1, x2, y2, floor_polygon)
        lines.append(
            f"  build_wall.call({mm_to_in(x1)}, {mm_to_in(y1)}, "
            f"{mm_to_in(x2)}, {mm_to_in(y2)}, {nx:.4f}, {ny:.4f})"
        )
    lines.append("")

    # ── Internal partition walls ──────────────────────────────────────────
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

    # ── Fixture map (local hash: name => [file, base_rot_offset]) ────────────
    lines.append("  # --- Fixture map ---")
    lines.append("  assets_dir  = '" + assets_dir.replace("'", "\\'") + "'")
    lines.append("  fixture_map = {")
    for dxf_name, (skp_file, base_rot) in fixture_map.items():
        lines.append(f"    '{dxf_name}' => ['{skp_file}', {base_rot}],")
    lines.append("  }")
    lines.append("")

    # ── Inline fixture placer lambda ──────────────────────────────────────
    lines.append("  place_fixture = lambda do |dxf_name, x_in, y_in, dxf_rot, xs, ys, zs|")
    lines.append("    entry = fixture_map[dxf_name]")
    lines.append("    next unless entry")
    lines.append("    skp_file, base_rot = entry")
    lines.append("    path = File.join(assets_dir, skp_file)")
    lines.append("    next unless File.exist?(path)")
    lines.append("    defn = model.definitions.load(path)")
    lines.append("    next unless defn")
    lines.append("    # Correct transform order:")
    lines.append("    #   1. Scale at component origin")
    lines.append("    #   2. Rotate around world origin")
    lines.append("    #   3. Translate to DXF insertion point")
    lines.append("    # Applied right-to-left in SketchUp: scale -> rotate -> translate")
    lines.append("    total_rad = (dxf_rot + base_rot) * Math::PI / 180.0")
    lines.append("    t_scale  = Geom::Transformation.scaling(ORIGIN, xs, ys, zs)")
    lines.append("    t_rotate = Geom::Transformation.rotation(ORIGIN, Z_AXIS, total_rad)")
    lines.append("    t_move   = Geom::Transformation.translation(Geom::Vector3d.new(x_in, y_in, 0))")
    lines.append("    ents.add_instance(defn, t_move * t_rotate * t_scale)")
    lines.append("  end")
    lines.append("")

    # ── Fixture placements ────────────────────────────────────────────────
    lines.append("  # --- Fixture placements (x, y in inches from DXF mm coords) ---")
    mapped   = [i for i in inserts if i["name"] in fixture_map]
    unmapped = [i for i in inserts if i["name"] not in fixture_map]

    local_centers = position_offsets or {}  # reuse param slot; now holds LOCAL_CENTERS
    for ins in mapped:
        x_in = ins["x"] / 25.4
        y_in = ins["y"] / 25.4
        skp_file, base_rot = fixture_map[ins["name"]]
        # Rotation-aware centering: shift insertion so visual center lands on DXF point
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


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        dxf_files = list(Path(".").glob("*.dxf"))
        if not dxf_files:
            print("Usage: python dxf_to_rb.py <input.dxf> [output.rb]")
            sys.exit(1)
        # Prefer the T-shape file if present
        pref = [f for f in dxf_files if "t_shape" in f.name.lower()]
        dxf_path = str(pref[0] if pref else dxf_files[0])
    else:
        dxf_path = sys.argv[1]

    rb_path = sys.argv[2] if len(sys.argv) > 2 else str(
        Path(dxf_path).with_suffix(".rb")
    )

    # Auto-save .skp next to the .rb file with same stem name
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
        WALL_HEIGHT, WALL_THICKNESS, FIXTURE_MAP, ASSETS_DIR,
        LOCAL_CENTERS, skp_save_path
    )

    Path(rb_path).write_text(rb_code, encoding="utf-8")

    # Generate walkthrough JSON next to the .rb file
    json_path = str(Path(rb_path).parent / "walkthrough_waypoints.json")
    generate_walkthrough_json(floor_pts, json_path)

    mapped   = sum(1 for i in inserts if i["name"] in FIXTURE_MAP)
    unmapped = len(inserts) - mapped

    print(f"\n{'='*55}")
    print(f"  Output : {rb_path}")
    print(f"  Walls  : {len(outer_walls)} outer + {len(internal_edges)} internal")
    print(f"  Fixtures: {mapped} mapped / {unmapped} unmapped")
    print(f"\n  HOW TO USE:")
    print(f"  1. Open SketchUp")
    print(f"  2. Open Window > Ruby Console")
    print(f"  3. Paste the contents of {Path(rb_path).name}")
    print(f"     OR: load '{rb_path.replace(chr(92), '/')}'")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
