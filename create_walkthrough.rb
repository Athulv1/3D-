# create_walkthrough.rb
# Reads walkthrough_waypoints.json and adds smooth camera scenes to the current model.
# Dense waypoints (25in spacing) + 0.3s transitions = smooth continuous video feel.
# Auto-triggered by auto_runner.rb after build_floorplan.rb completes.

require 'json'

_walkthrough = proc do
  model = Sketchup.active_model

  json_path = File.join(File.dirname(model.path), "walkthrough_waypoints.json")

  unless File.exist?(json_path)
    UI.messagebox("Walkthrough JSON not found:\n#{json_path}")
    next
  end

  data            = JSON.parse(File.read(json_path))
  waypoints       = data["waypoints"]       || []
  transition_time = (data["transition_time"] || 0.3).to_f
  delay_time      = (data["delay_time"]      || 0.0).to_f

  if waypoints.empty?
    UI.messagebox("No waypoints found in #{json_path}")
    next
  end

  puts "Walkthrough: loading #{waypoints.size} waypoints..."

  # Remove previously generated walkthrough scenes for clean rebuild
  to_delete = model.pages.select { |p| p.name.start_with?("Walkthrough_") }
  to_delete.each { |p| model.pages.erase(p) }

  model.start_operation("Create Walkthrough", true)

  begin
    view = model.active_view

    waypoints.each_with_index do |wp, i|
      eye    = wp["eye"]
      target = wp["target"]
      up     = wp["up"]

      cam = Sketchup::Camera.new(
        Geom::Point3d.new(eye["x"],    eye["y"],    eye["z"]),
        Geom::Point3d.new(target["x"], target["y"], target["z"]),
        Geom::Vector3d.new(up["x"],    up["y"],     up["z"])
      )
      cam.fov         = 75.0   # wide angle for immersive walkthrough
      cam.perspective = true

      view.camera = cam

      scene_name = wp["name"] || "Walkthrough_#{(i + 1).to_s.rjust(3, '0')}"
      scene = model.pages.add(scene_name)
      scene.use_camera      = true
      scene.transition_time = transition_time
      scene.delay_time      = delay_time

      # Only save camera — hide all other scene properties to keep it clean
      scene.use_hidden_layers    = false
      scene.use_rendering_options = false
      scene.use_shadow_info      = false
      scene.use_style            = false
    end

    model.commit_operation

    # Show the Scenes panel and Animation toolbar
    Sketchup.send_action("showSceneManager:")

    model.save(model.path)

    total_time = (waypoints.size * transition_time).round(1)
    puts "Walkthrough: #{waypoints.size} scenes, ~#{total_time}s total"

    # Open the navigation control panel
    WalkthroughControls.open_panel rescue nil

    UI.messagebox(
      "Walkthrough ready!\n\n" \
      "  Scenes   : #{waypoints.size}\n" \
      "  Duration : ~#{total_time} seconds\n\n" \
      "Use the Walkthrough Controls panel to Play / Pause / Navigate.\n\n" \
      "TO EXPORT AS VIDEO:\n" \
      "  File -> Export -> Animation -> .mp4"
    )

  rescue => e
    model.abort_operation
    UI.messagebox("Walkthrough error:\n#{e.message}\n\n#{e.backtrace.first(3).join("\n")}")
  end
end

_walkthrough.call
