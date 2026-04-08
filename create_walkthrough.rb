# create_walkthrough.rb
# Reads walkthrough_waypoints.json and adds camera scenes to the current model.
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
  transition_time = (data["transition_time"] || 2.0).to_f
  delay_time      = (data["delay_time"]      || 0.5).to_f

  if waypoints.empty?
    UI.messagebox("No waypoints found in #{json_path}")
    next
  end

  puts "Walkthrough: loading #{waypoints.size} waypoints from #{json_path}"

  # Remove any previously generated walkthrough scenes
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
      cam.fov = 60.0

      view.camera = cam

      scene_name = wp["name"] || "Walkthrough_#{(i + 1).to_s.rjust(3, '0')}"
      scene = model.pages.add(scene_name)
      scene.use_camera      = true
      scene.transition_time = transition_time
      scene.delay_time      = delay_time

      puts "  Scene #{i + 1}/#{waypoints.size}: #{scene_name}"
    end

    model.commit_operation
    model.save(model.path)
    puts "Walkthrough: saved #{waypoints.size} scenes to #{model.path}"
    UI.messagebox("Walkthrough ready!  #{waypoints.size} scenes created.\n\nPlay: View -> Animation -> Play")

  rescue => e
    model.abort_operation
    UI.messagebox("Walkthrough error:\n#{e.message}\n\n#{e.backtrace.first(3).join("\n")}")
  end
end

_walkthrough.call
