"""
extract_assets.py — Generates a Ruby script for SketchUp that:
  1. Opens a source .skp file
  2. Extracts every component definition as an individual .skp asset
  3. Computes bounding-box center offsets (for placement correction)
  4. Writes an assets_manifest.json + done marker file

Usage (called by app.py, not directly):
    from extract_assets import generate_extraction_script
    ruby_code = generate_extraction_script(source, assets_dir, manifest, done)
"""


def generate_extraction_script(source_skp_path, assets_dir, manifest_path, done_marker_path):
    """Return a Ruby script string that SketchUp will execute."""
    # Normalize all paths to forward slashes for Ruby
    src = source_skp_path.replace("\\", "/")
    adir = assets_dir.replace("\\", "/")
    mpath = manifest_path.replace("\\", "/")
    dpath = done_marker_path.replace("\\", "/")

    return f"""\
require 'json'
require 'fileutils'

_extract = proc do
  source_path   = '{src}'
  assets_dir    = '{adir}'
  manifest_path = '{mpath}'
  done_path     = '{dpath}'

  FileUtils.mkdir_p(assets_dir)

  # Yield SketchUp focus back for 0.5s before taking over the main thread
  UI.start_timer(0.5, false) do
    begin
      model = Sketchup.active_model

      # Snapshot existing definition NAMES before loading.
      # (Using names, not object_ids — SketchUp may merge definitions
      # with matching names on load, keeping the old object_id.)
      existing_names = model.definitions.map {{ |d| d.name }}

      puts "Loading source file synchronously into current model..."
      source_defn = model.definitions.load(source_path)

      unless source_defn
        UI.messagebox("Extraction error: Failed to load source SKP file.")
        File.write(done_path, "Error: load failed")
        next
      end

      # ── HYBRID EXTRACTION ────────────────────────────────────────────
      # Pass 1: Walk source_defn.entities to find placed instances &
      #         groups (handles Groups properly, recurses containers).
      # Pass 2: Scan model.definitions for any NEW definitions that the
      #         load added but that are NOT placed at the root level
      #         (e.g. "In Model" components, nested sub-components).
      # This ensures nothing is missed.

      fixture_defs = {{}}  # defn.object_id => {{ defn:, name:, count: }}

      collect_fixtures = proc do |entities, depth|
        entities.each do |ent|
          defn = nil
          instance_name = nil

          if ent.is_a?(Sketchup::ComponentInstance)
            defn = ent.definition
            instance_name = ent.name
          elsif ent.is_a?(Sketchup::Group)
            defn = ent.definition
            instance_name = ent.name

            # Check if this group is just an organisational container:
            # it has sub-instances / sub-groups but no faces of its own.
            sub_instances = defn.entities.select {{ |e|
              e.is_a?(Sketchup::ComponentInstance) || e.is_a?(Sketchup::Group)
            }}
            has_own_faces = defn.entities.any? {{ |e| e.is_a?(Sketchup::Face) }}

            if sub_instances.size > 0 && !has_own_faces && depth < 3
              # Pure container — recurse into it instead of extracting it
              puts "  Recursing into container: #{{instance_name.to_s.empty? ? defn.name : instance_name}} (depth=#{{depth}})"
              collect_fixtures.call(defn.entities, depth + 1)
              next
            end
          else
            next
          end

          next if defn.nil? || defn.image?

          oid = defn.object_id
          if fixture_defs.key?(oid)
            fixture_defs[oid][:count] += 1
            next
          end

          # ── Determine the best display name ──
          name = nil
          # 1. Prefer the component definition name if it is meaningful
          if !defn.name.empty? && !defn.name.match?(/^Group#/)
            name = defn.name
          end
          # 2. Fall back to the instance / group name set by the user
          if name.nil? && instance_name && !instance_name.empty?
            name = instance_name
          end
          # 3. Last resort: derive a name from bounding-box dimensions
          if name.nil?
            b = defn.bounds
            w = (b.max.x - b.min.x).to_i
            d = (b.max.y - b.min.y).to_i
            h = (b.max.z - b.min.z).to_i
            name = "Fixture_#{{w}}x#{{d}}x#{{h}}"
          end

          fixture_defs[oid] = {{ defn: defn, name: name, count: 1 }}
        end
      end

      collect_fixtures.call(source_defn.entities, 0)

      puts "Pass 1 (entity walk): #{{fixture_defs.size}} definitions"

      # ── Pass 2: recursively walk the ENTIRE definition tree starting
      #    from source_defn to find every nested sub-component.
      #    Unlike the old model.definitions scan, this does NOT depend
      #    on existing_ids — so definitions that already existed in
      #    the model (from a previous extraction in the same session)
      #    are still caught. ──
      walk_def_tree = proc do |parent_defn|
        parent_defn.entities.each do |ent|
          sub_defn = nil
          if ent.is_a?(Sketchup::ComponentInstance)
            sub_defn = ent.definition
          elsif ent.is_a?(Sketchup::Group)
            sub_defn = ent.definition
          end
          next unless sub_defn
          next if sub_defn.image?

          oid = sub_defn.object_id
          next if fixture_defs.key?(oid)  # already collected

          name = sub_defn.name
          if name.empty? || name.match?(/^Group#/)
            has_faces = sub_defn.entities.any? {{ |e| e.is_a?(Sketchup::Face) }}
            next unless has_faces   # skip empty anonymous groups
            b = sub_defn.bounds
            w = (b.max.x - b.min.x).to_i
            d = (b.max.y - b.min.y).to_i
            h = (b.max.z - b.min.z).to_i
            name = "Fixture_#{{w}}x#{{d}}x#{{h}}"
          end

          fixture_defs[oid] = {{ defn: sub_defn, name: name, count: 0 }}
          walk_def_tree.call(sub_defn)  # recurse deeper
        end
      end

      # Walk from source_defn AND from every definition already found by Pass 1
      walk_def_tree.call(source_defn)
      fixture_defs.values.map {{ |info| info[:defn] }}.each do |d|
        walk_def_tree.call(d)
      end

      puts "Pass 2 (recursive tree walk): #{{fixture_defs.size}} total definitions"

      # ── Pass 3: scan model.definitions for definitions with NEW names
      #    that the load introduced but that aren't reachable from the
      #    entity tree (unplaced "In Model" components). ──
      model.definitions.each do |defn|
        next if defn == source_defn
        next if defn.image?
        next if fixture_defs.key?(defn.object_id)

        # Skip definitions that existed BEFORE load (by name)
        next if existing_names.include?(defn.name)

        name = defn.name
        if name.empty? || name.match?(/^Group#/)
          has_faces = defn.entities.any? {{ |e| e.is_a?(Sketchup::Face) }}
          next unless has_faces
          b = defn.bounds
          w = (b.max.x - b.min.x).to_i
          d = (b.max.y - b.min.y).to_i
          h = (b.max.z - b.min.z).to_i
          name = "Fixture_#{{w}}x#{{d}}x#{{h}}"
        end

        fixture_defs[defn.object_id] = {{ defn: defn, name: name, count: 0 }}
      end

      puts "Pass 3 (new definitions scan): #{{fixture_defs.size}} total definitions"

      # ── Disambiguate duplicate names ──
      name_counts = Hash.new(0)
      fixture_defs.each_value {{ |info| name_counts[info[:name]] += 1 }}
      name_seen = Hash.new(0)
      fixture_defs.each_value do |info|
        if name_counts[info[:name]] > 1
          name_seen[info[:name]] += 1
          info[:name] = "#{{info[:name]}}_#{{name_seen[info[:name]]}}"
        end
      end

      # ── Save each fixture definition as an individual .skp file ──
      manifest = []

      fixture_defs.each_value do |info|
        defn  = info[:defn]
        name  = info[:name]
        count = info[:count]

        clean = name.gsub(/[\\\\\\/:"*?<>|]/, '_')
        filename = clean + '.skp'
        save_path = File.join(assets_dir, filename)

        begin
          defn.save_as(save_path)

          b  = defn.bounds
          cx = ((b.min.x + b.max.x) / 2.0).round(3)
          cy = ((b.min.y + b.max.y) / 2.0).round(3)

          manifest << {{
            'name'           => name,
            'filename'       => filename,
            'local_center_x' => cx,
            'local_center_y' => cy,
            'width'          => (b.max.x - b.min.x).round(3),
            'depth'          => (b.max.y - b.min.y).round(3),
            'height'         => (b.max.z - b.min.z).round(3),
            'instances'      => count
          }}

          puts "  Extracted: #{{name}} -> #{{filename}} (#{{count}} instances)"
        rescue => e
          puts "  FAILED: #{{name}} - #{{e.message}}"
        end
      end

      # Clean up definitions we pulled into the model
      model.definitions.purge_unused

      File.write(manifest_path, JSON.pretty_generate(manifest))
      File.write(done_path, "#{{manifest.size}} fixtures extracted at #{{Time.now}}")

      puts "Extraction complete: #{{manifest.size}} fixtures -> #{{assets_dir}}"
      UI.messagebox(
        "Extraction complete!\\n\\n" \\
        "#{{manifest.size}} fixtures extracted to:\\n" \\
        "#{{assets_dir}}"
      )
    rescue => global_err
      err_msg = "Extraction crashed: #{{global_err.message}}\\n#{{global_err.backtrace.join(\"\\n\")}}"
      puts err_msg
      File.write(done_path, "Error")
      File.write(manifest_path, JSON.pretty_generate([{{name: "ERROR", filename: global_err.message, instances: 0}}]))
      UI.messagebox("Extraction failed:\\n#{{global_err.message}}")
    end
  end
end

_extract.call
"""
