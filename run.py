"""
run.py — One-command pipeline: DXF → Ruby script → SketchUp auto-executes it.

Usage:
    python run.py [input.dxf]

If no DXF file is given, uses output_t_shape_store.dxf by default.

Requirements:
    1. SketchUp must be open.
    2. auto_runner.rb must be installed in SketchUp's Plugins folder.
       (Copy it once, restart SketchUp — done.)
"""

import sys
import os
import subprocess
import time

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DXF    = os.path.join(BASE_DIR, "output_t_shape_store.dxf")
OUTPUT_RB      = os.path.join(BASE_DIR, "build_floorplan.rb")
WALKTHROUGH_RB = os.path.join(BASE_DIR, "create_walkthrough.rb")
TRIGGER_FILE   = os.path.join(BASE_DIR, "run_trigger.txt")
GENERATOR      = os.path.join(BASE_DIR, "dxf_to_rb.py")

# ── Helpers ───────────────────────────────────────────────────────────────────
def banner(msg):
    print(f"\n{'='*55}")
    print(f"  {msg}")
    print(f"{'='*55}")

def step(n, msg):
    print(f"\n[{n}] {msg}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    dxf_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DXF

    if not os.path.exists(dxf_path):
        print(f"ERROR: DXF file not found: {dxf_path}")
        sys.exit(1)

    banner("DXF -> SketchUp Auto Pipeline")

    # Step 1: Generate the Ruby script from DXF
    step(1, f"Generating Ruby script from: {os.path.basename(dxf_path)}")
    result = subprocess.run(
        [sys.executable, GENERATOR, dxf_path, OUTPUT_RB],
        capture_output=False
    )
    if result.returncode != 0:
        print("ERROR: Ruby script generation failed.")
        sys.exit(1)

    if not os.path.exists(OUTPUT_RB):
        print(f"ERROR: Expected output not found: {OUTPUT_RB}")
        sys.exit(1)

    # Step 2: Drop the trigger file — SketchUp picks this up within 2 seconds
    step(2, "Dropping trigger file for SketchUp...")
    rb1 = OUTPUT_RB.replace("\\", "/")
    rb2 = WALKTHROUGH_RB.replace("\\", "/")
    with open(TRIGGER_FILE, "w") as f:
        f.write(f"{rb1}\n{rb2}")

    print(f"  Trigger written: {TRIGGER_FILE}")
    print(f"  Script 1: {rb1}")
    print(f"  Script 2: {rb2}")
    print("\n  SketchUp will build floor plan, then add walkthrough scenes (~10s total).")
    print("  Make sure SketchUp is open with auto_runner.rb installed.\n")

    banner("Done — check SketchUp for floor plan + walkthrough.")

if __name__ == "__main__":
    main()
