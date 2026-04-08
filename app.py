"""
app.py — Web interface for DXF -> SketchUp floor plan generator.
Run: py app.py
Open: http://localhost:5000
"""

import os
import subprocess
import sys
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR     = os.path.join(BASE_DIR, "uploads")
GENERATOR      = os.path.join(BASE_DIR, "dxf_to_rb.py")
OUTPUT_RB      = os.path.join(BASE_DIR, "build_floorplan.rb")
WALKTHROUGH_RB = os.path.join(BASE_DIR, "create_walkthrough.rb")
TRIGGER_FILE   = os.path.join(BASE_DIR, "run_trigger.txt")

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB max upload


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    if "dxf" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded."})

    f = request.files["dxf"]
    if not f.filename.lower().endswith((".dxf", ".dwg")):
        return jsonify({"ok": False, "error": "Only .dxf files are supported."})

    filename  = secure_filename(f.filename)
    dxf_path  = os.path.join(UPLOAD_DIR, filename)
    f.save(dxf_path)

    # Always generate to the fixed build_floorplan.rb so SketchUp always finds it
    result = subprocess.run(
        [sys.executable, GENERATOR, dxf_path, OUTPUT_RB],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        return jsonify({"ok": False, "error": result.stderr or "Generator failed."})

    # Drop trigger file with both script paths (floor plan + walkthrough)
    rb1 = OUTPUT_RB.replace("\\", "/")
    rb2 = WALKTHROUGH_RB.replace("\\", "/")
    print(f"[app] Writing trigger: '{rb1}' + '{rb2}'")
    with open(TRIGGER_FILE, "w") as t:
        t.write(f"{rb1}\n{rb2}")
    print(f"[app] Trigger file written.")


    # Count walls and fixtures from output
    walls    = result.stdout.count("build_wall.call") if "build_wall" in result.stdout else "?"
    fixtures = next(
        (line.split(":")[1].strip().split(" ")[0]
         for line in result.stdout.splitlines() if "Fixtures:" in line),
        "?"
    )

    return jsonify({
        "ok": True,
        "message": "Script generated and sent to SketchUp.",
        "file": filename,
        "details": result.stdout.strip().split("\n")[-6:]
    })


if __name__ == "__main__":
    print("\n  Floor Plan Generator")
    print("  Open http://localhost:5000 in your browser\n")
    app.run(debug=False, port=5001)
