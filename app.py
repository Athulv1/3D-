"""
app.py — Universal 3D Floor Plan Generator
Multi-project web interface: SKP extraction -> DXF mapping -> 3D generation
Run: python app.py
Open: http://localhost:5001
"""

import os
import json
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename

BASE_DIR       = Path(__file__).parent
PROJECTS_DIR   = BASE_DIR / "projects"
TRIGGER_FILE   = BASE_DIR / "run_trigger.txt"
WALKTHROUGH_RB = BASE_DIR / "create_walkthrough.rb"

PROJECTS_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB


# ── Helpers ──────────────────────────────────────────────────────────

def get_project(project_id):
    config_path = PROJECTS_DIR / project_id / "project.json"
    if not config_path.exists():
        return None
    return json.loads(config_path.read_text(encoding="utf-8"))


def save_project(project_id, config):
    config_path = PROJECTS_DIR / project_id / "project.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def list_projects():
    projects = []
    if PROJECTS_DIR.exists():
        for d in sorted(PROJECTS_DIR.iterdir(), reverse=True):
            if d.is_dir() and (d / "project.json").exists():
                try:
                    projects.append(get_project(d.name))
                except Exception:
                    pass
    return projects


def get_asset_manifest(project_id):
    manifest_path = PROJECTS_DIR / project_id / "assets_manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return []


# ── Page Routes ──────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    return render_template("dashboard.html", projects=list_projects())


@app.route("/project/<project_id>")
def project_detail(project_id):
    config = get_project(project_id)
    if not config:
        return "Project not found", 404
    return render_template("project.html", project=config)


# ── API: Project CRUD ────────────────────────────────────────────────

@app.route("/api/projects", methods=["POST"])
def api_create_project():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Project name is required."})

    project_id = str(uuid.uuid4())[:8]
    project_dir = PROJECTS_DIR / project_id
    project_dir.mkdir(parents=True)
    (project_dir / "assets").mkdir()
    (project_dir / "output").mkdir()

    config = {
        "id": project_id,
        "name": name,
        "status": "created",
        "created_at": datetime.now().isoformat(),
        "wall_height": 3000,
        "wall_thickness": 150,
        "fixture_mapping": {},
        "skp_uploaded": False,
        "dxf_uploaded": False,
        "extraction_done": False,
        "dxf_blocks": [],
    }
    save_project(project_id, config)
    return jsonify({"ok": True, "id": project_id})


@app.route("/api/projects/<project_id>", methods=["GET"])
def api_get_project(project_id):
    config = get_project(project_id)
    if not config:
        return jsonify({"ok": False, "error": "Not found"}), 404
    config["assets"] = get_asset_manifest(project_id)
    return jsonify({"ok": True, "project": config})


@app.route("/api/projects/<project_id>", methods=["DELETE"])
def api_delete_project(project_id):
    project_dir = PROJECTS_DIR / project_id
    if project_dir.exists():
        shutil.rmtree(project_dir)
    return jsonify({"ok": True})


# ── API: SKP Upload & Extraction ─────────────────────────────────────

@app.route("/api/projects/<project_id>/upload-skp", methods=["POST"])
def api_upload_skp(project_id):
    config = get_project(project_id)
    if not config:
        return jsonify({"ok": False, "error": "Project not found."}), 404

    if "skp" not in request.files:
        return jsonify({"ok": False, "error": "No SKP file uploaded."})

    f = request.files["skp"]
    if not f.filename.lower().endswith(".skp"):
        return jsonify({"ok": False, "error": "Only .skp files are supported."})

    project_dir = PROJECTS_DIR / project_id
    skp_path = project_dir / "source.skp"
    f.save(str(skp_path))

    # Generate extraction Ruby script
    from extract_assets import generate_extraction_script

    assets_dir   = str(project_dir / "assets")
    manifest_path = str(project_dir / "assets_manifest.json")
    done_marker  = str(project_dir / "_extraction_done.txt")

    # Clean previous extraction artifacts (but keep manually added assets)
    for old in (project_dir / "assets").glob("*.skp"):
        old.unlink()

    # Copy hardcoded assets that won't come from SketchUp extraction
    for _extra in ["Component_5.skp", "Component_6.skp"]:
        _src = BASE_DIR / _extra
        if _src.exists():
            shutil.copy2(str(_src), str(project_dir / "assets" / _extra))
    for marker in [Path(done_marker), Path(manifest_path)]:
        if marker.exists():
            marker.unlink()

    rb_script = generate_extraction_script(
        source_skp_path=str(skp_path),
        assets_dir=assets_dir,
        manifest_path=manifest_path,
        done_marker_path=done_marker,
    )

    extraction_rb = project_dir / "extract_assets.rb"
    extraction_rb.write_text(rb_script, encoding="utf-8")

    # Write trigger for SketchUp
    rb_path = str(extraction_rb).replace("\\", "/")
    with open(str(TRIGGER_FILE), "w") as t:
        t.write(rb_path)

    config["skp_uploaded"] = True
    config["extraction_done"] = False
    config["status"] = "extracting"
    save_project(project_id, config)

    print(f"[app] SKP uploaded for project {project_id}, extraction trigger written.")
    return jsonify({"ok": True, "message": "SKP uploaded. Extraction started in SketchUp."})


@app.route("/api/projects/<project_id>/extraction-status", methods=["GET"])
def api_extraction_status(project_id):
    config = get_project(project_id)
    if not config:
        return jsonify({"ok": False, "error": "Not found"}), 404

    done_marker = PROJECTS_DIR / project_id / "_extraction_done.txt"
    manifest = get_asset_manifest(project_id)

    if done_marker.exists():
        if not config.get("extraction_done"):
            config["extraction_done"] = True
            config["status"] = "extracted"
            save_project(project_id, config)
        return jsonify({"ok": True, "done": True, "assets": manifest})

    return jsonify({"ok": True, "done": False, "assets": []})


# ── API: DXF Upload & Auto-Mapping ───────────────────────────────────

@app.route("/api/projects/<project_id>/upload-dxf", methods=["POST"])
def api_upload_dxf(project_id):
    config = get_project(project_id)
    if not config:
        return jsonify({"ok": False, "error": "Project not found."}), 404

    if "dxf" not in request.files:
        return jsonify({"ok": False, "error": "No DXF file uploaded."})

    f = request.files["dxf"]
    if not f.filename.lower().endswith((".dxf", ".dwg")):
        return jsonify({"ok": False, "error": "Only .dxf files are supported."})

    project_dir = PROJECTS_DIR / project_id
    dxf_path = project_dir / "source.dxf"
    f.save(str(dxf_path))

    from dxf_to_rb import parse_dxf, detect_wall_height, auto_map_fixtures

    try:
        outer_walls, partitions, inserts = parse_dxf(str(dxf_path))
    except Exception as e:
        return jsonify({"ok": False, "error": f"DXF parse error: {str(e)}"})

    block_names = sorted(set(ins["name"] for ins in inserts))

    # Try detecting wall height from DXF
    detected_height = detect_wall_height(str(dxf_path))
    if detected_height:
        config["wall_height"] = detected_height

    # Auto-map DXF block names to extracted assets
    manifest = get_asset_manifest(project_id)
    mapping_result = auto_map_fixtures(block_names, manifest)

    config["dxf_uploaded"] = True
    config["dxf_blocks"] = block_names
    config["status"] = "mapping"

    # Merge auto-mapping: hardcoded rules always win, fuzzy matches
    # only fill in if no existing manual edit is present.
    from dxf_to_rb import HARDCODED_FIXTURE_MAP
    for name, entry in mapping_result["matched"].items():
        if name in HARDCODED_FIXTURE_MAP:
            config["fixture_mapping"][name] = entry  # always overwrite
        elif name not in config["fixture_mapping"]:
            config["fixture_mapping"][name] = entry  # don't overwrite manual edits

    save_project(project_id, config)

    return jsonify({
        "ok": True,
        "blocks": block_names,
        "walls": len(outer_walls),
        "partitions": len(partitions),
        "fixtures": len(inserts),
        "auto_mapped": mapping_result["matched"],
        "unmatched": mapping_result["unmatched"],
        "detected_wall_height": detected_height,
    })


# ── API: Mapping ─────────────────────────────────────────────────────

@app.route("/api/projects/<project_id>/mapping", methods=["GET"])
def api_get_mapping(project_id):
    config = get_project(project_id)
    if not config:
        return jsonify({"ok": False, "error": "Not found"}), 404
    manifest = get_asset_manifest(project_id)
    return jsonify({
        "ok": True,
        "mapping": config.get("fixture_mapping", {}),
        "blocks": config.get("dxf_blocks", []),
        "assets": manifest,
    })


@app.route("/api/projects/<project_id>/mapping", methods=["PUT"])
def api_save_mapping(project_id):
    config = get_project(project_id)
    if not config:
        return jsonify({"ok": False, "error": "Not found"}), 404

    data = request.get_json() or {}
    config["fixture_mapping"] = data.get("mapping", {})
    config["status"] = "ready"
    save_project(project_id, config)
    return jsonify({"ok": True, "message": "Mapping saved."})


# ── API: Settings ────────────────────────────────────────────────────

@app.route("/api/projects/<project_id>/settings", methods=["PUT"])
def api_save_settings(project_id):
    config = get_project(project_id)
    if not config:
        return jsonify({"ok": False, "error": "Not found"}), 404

    data = request.get_json() or {}
    if "wall_height" in data:
        config["wall_height"] = int(data["wall_height"])
    if "wall_thickness" in data:
        config["wall_thickness"] = int(data["wall_thickness"])
    save_project(project_id, config)
    return jsonify({"ok": True})


# ── API: Generate 3D ─────────────────────────────────────────────────

@app.route("/api/projects/<project_id>/generate", methods=["POST"])
def api_generate(project_id):
    config = get_project(project_id)
    if not config:
        return jsonify({"ok": False, "error": "Project not found."}), 404

    project_dir = PROJECTS_DIR / project_id
    dxf_path = project_dir / "source.dxf"

    if not dxf_path.exists():
        return jsonify({"ok": False, "error": "No DXF file. Upload a DXF first."})

    from dxf_to_rb import generate_from_project

    try:
        result = generate_from_project(str(project_dir))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)})

    # Copy walkthrough script to output folder + write trigger
    output_dir = project_dir / "output"
    wt_dest = output_dir / "create_walkthrough.rb"
    if WALKTHROUGH_RB.exists():
        shutil.copy2(str(WALKTHROUGH_RB), str(wt_dest))

    output_rb = str(output_dir / "build_floorplan.rb").replace("\\", "/")
    wt_path   = str(wt_dest).replace("\\", "/")

    trigger_tmp = str(TRIGGER_FILE) + ".tmp"
    with open(trigger_tmp, "w") as t:
        t.write(f"{output_rb}\n{wt_path}")
    import os
    if os.path.exists(str(TRIGGER_FILE)):
        os.remove(str(TRIGGER_FILE))
    os.rename(trigger_tmp, str(TRIGGER_FILE))

    config["status"] = "generated"
    save_project(project_id, config)

    print(f"[app] 3D generated for project {project_id}, trigger written.")
    return jsonify({
        "ok": True,
        "message": "3D model generated and sent to SketchUp!",
        "details": result,
    })


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  3D Floor Plan Generator — Universal Edition")
    print("  Open http://localhost:5001 in your browser\n")
    app.run(debug=True, port=5001)
