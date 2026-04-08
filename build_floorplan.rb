# Auto-generated SketchUp Floor Plan Builder
# Run: Window > Ruby Console, then: load 'C:/path/to/build_floorplan.rb'

_build = proc do
  model = Sketchup.active_model
  model.start_operation('Build Floor Plan', true)
  ents  = model.active_entities
  ents.clear!
  model.definitions.purge_unused

  wall_h = 118.110236  # wall height (inches)
  wall_t = 5.905512  # wall thickness (inches)

  wall_mat = model.materials.add('wall')
  wall_mat.color = [215, 208, 198]
  build_wall = lambda do |x1, y1, x2, y2, nx, ny|
    pts = [
      Geom::Point3d.new(x1,             y1,             0),
      Geom::Point3d.new(x2,             y2,             0),
      Geom::Point3d.new(x2 + nx*wall_t, y2 + ny*wall_t, 0),
      Geom::Point3d.new(x1 + nx*wall_t, y1 + ny*wall_t, 0),
    ]
    face = ents.add_face(pts)
    if face.is_a?(Sketchup::Face)
      # Walls going in +Y direction create a CCW face (normal = +Z).
      # pushpull(-wall_h) on a +Z face goes DOWN. Reverse so it always goes UP.
      face.reverse! if face.normal.z > 0
      face.material = wall_mat
      face.pushpull(-wall_h)
    end
  end

  # --- Floor ---
  floor_mat = model.materials.add('floor')
  floor_mat.color = [200, 195, 185]
  floor_face = ents.add_face([Geom::Point3d.new(236.220472, 0.000000, 0), Geom::Point3d.new(708.661417, 0.000000, 0), Geom::Point3d.new(708.661417, 393.700787, 0), Geom::Point3d.new(944.881890, 393.700787, 0), Geom::Point3d.new(944.881890, 708.661417, 0), Geom::Point3d.new(0.000000, 708.661417, 0), Geom::Point3d.new(0.000000, 393.700787, 0), Geom::Point3d.new(236.220472, 393.700787, 0)])
  floor_face.material = floor_mat if floor_face.is_a?(Sketchup::Face)

  # --- Outer walls ---
  build_wall.call(236.220472, 0.000000, 708.661417, 0.000000, -0.0000, 1.0000)
  build_wall.call(708.661417, 0.000000, 708.661417, 393.700787, -1.0000, 0.0000)
  build_wall.call(708.661417, 393.700787, 944.881890, 393.700787, -0.0000, 1.0000)
  build_wall.call(944.881890, 393.700787, 944.881890, 708.661417, -1.0000, 0.0000)
  build_wall.call(944.881890, 708.661417, 0.000000, 708.661417, -0.0000, -1.0000)
  build_wall.call(0.000000, 708.661417, 0.000000, 393.700787, 1.0000, 0.0000)
  build_wall.call(0.000000, 393.700787, 236.220472, 393.700787, -0.0000, 1.0000)
  build_wall.call(236.220472, 393.700787, 236.220472, 0.000000, 1.0000, 0.0000)

  # --- Internal partition walls ---
  build_wall.call(0.000000, 590.551181, 0.000000, 708.661417, 1.0000, -0.0000)
  build_wall.call(0.000000, 708.661417, 472.440945, 708.661417, 0.0000, -1.0000)
  build_wall.call(472.440945, 708.661417, 472.440945, 590.551181, -1.0000, -0.0000)
  build_wall.call(472.440945, 590.551181, 0.000000, 590.551181, 0.0000, 1.0000)
  build_wall.call(944.881890, 590.551181, 472.440945, 590.551181, 0.0000, 1.0000)
  build_wall.call(472.440945, 708.661417, 944.881890, 708.661417, 0.0000, -1.0000)
  build_wall.call(944.881890, 708.661417, 944.881890, 590.551181, -1.0000, -0.0000)
  build_wall.call(236.220472, 0.000000, 236.220472, 59.055118, 1.0000, -0.0000)
  build_wall.call(236.220472, 59.055118, 708.661417, 59.055118, 0.0000, -1.0000)
  build_wall.call(708.661417, 59.055118, 708.661417, 0.000000, -1.0000, -0.0000)

  # --- Fixture map ---
  assets_dir  = 'C:/Users/athul/Documents/3d_gen/Assets'
  fixture_map = {
    'FINANCE_DESK' => ['FINANCE DESK#2.skp', -90],
    'MOBILE' => ['MOBILE WALL GRAY.skp', 90],
    'ACCESSORIES' => ['ACCESSORIES#6.skp', -90],
    'CARE' => ['care logo.skp', 90],
    'TV_WALL' => ['SMART TV#3.skp', 0],
    'AC_WALL' => ['AIR CONDITIONETR.skp', 0],
    'CASH_COUNTER' => ['cash counter 210#1.skp', 90],
    'COUNTER' => ['MOBILW OWN COUNTER.skp', 0],
    'APPLE' => ['apple#3.skp', 0],
    'SAMSUNG' => ['SAMSUNG COUNTER.skp', -90],
    'LAPTOP' => ['LAP TABLE.skp', 180],
    'VIVO' => ['MOBILE WALL GRAY.skp', 270],
    'OPPO' => ['MOBILE WALL GRAY.skp', 270],
    'XIAOMI' => ['MOBILE WALL GRAY.skp', 270],
  }

  place_fixture = lambda do |dxf_name, x_in, y_in, dxf_rot, xs, ys, zs|
    entry = fixture_map[dxf_name]
    next unless entry
    skp_file, base_rot = entry
    path = File.join(assets_dir, skp_file)
    next unless File.exist?(path)
    defn = model.definitions.load(path)
    next unless defn
    # Correct transform order:
    #   1. Scale at component origin
    #   2. Rotate around world origin
    #   3. Translate to DXF insertion point
    # Applied right-to-left in SketchUp: scale -> rotate -> translate
    total_rad = (dxf_rot + base_rot) * Math::PI / 180.0
    t_scale  = Geom::Transformation.scaling(ORIGIN, xs, ys, zs)
    t_rotate = Geom::Transformation.rotation(ORIGIN, Z_AXIS, total_rad)
    t_move   = Geom::Transformation.translation(Geom::Vector3d.new(x_in, y_in, 0))
    ents.add_instance(defn, t_move * t_rotate * t_scale)
  end

  # --- Fixture placements (x, y in inches from DXF mm coords) ---
  place_fixture.call('FINANCE_DESK', 36.316079, 584.122598, 0.00, 1.000, 1.000, 1.000)  # DXF rot=0 + base=-90 = -90 deg
  place_fixture.call('MOBILE', 703.844646, 247.904976, 90.00, 1.000, 1.000, 1.000)  # DXF rot=90 + base=90 = 180 deg
  place_fixture.call('MOBILE', 703.844646, 301.448283, 90.00, 1.000, 1.000, 1.000)  # DXF rot=90 + base=90 = 180 deg
  place_fixture.call('MOBILE', 703.844646, 355.385291, 90.00, 1.000, 1.000, 1.000)  # DXF rot=90 + base=90 = 180 deg
  place_fixture.call('MOBILE', 755.149071, 398.517559, 0.00, 1.000, 1.000, 1.000)  # DXF rot=0 + base=90 = 90 deg
  place_fixture.call('MOBILE', 808.692378, 398.517559, 0.00, 1.000, 1.000, 1.000)  # DXF rot=0 + base=90 = 90 deg
  place_fixture.call('MOBILE', 862.235685, 398.517559, 0.00, 1.000, 1.000, 1.000)  # DXF rot=0 + base=90 = 90 deg
  place_fixture.call('MOBILE', 915.778992, 398.517559, 0.00, 1.000, 1.000, 1.000)  # DXF rot=0 + base=90 = 90 deg
  place_fixture.call('MOBILE', 940.065118, 440.188441, 90.00, 1.000, 1.000, 1.000)  # DXF rot=90 + base=90 = 180 deg
  place_fixture.call('ACCESSORIES', 940.954118, 449.638748, 90.00, 1.000, 1.000, 1.000)  # DXF rot=90 + base=-90 = 0 deg
  place_fixture.call('ACCESSORIES', 940.954118, 503.182055, 90.00, 1.000, 1.000, 1.000)  # DXF rot=90 + base=-90 = 0 deg
  place_fixture.call('ACCESSORIES', 3.927772, 499.180150, -90.00, 1.000, 1.000, 1.000)  # DXF rot=-90 + base=-90 = -180 deg
  place_fixture.call('ACCESSORIES', 3.927772, 445.636843, -90.00, 1.000, 1.000, 1.000)  # DXF rot=-90 + base=-90 = -180 deg
  place_fixture.call('ACCESSORIES', 22.079693, 397.628559, 0.00, 1.000, 1.000, 1.000)  # DXF rot=0 + base=-90 = -90 deg
  place_fixture.call('CARE', 112.471000, 386.584559, 0.00, 1.000, 1.000, 1.000)  # DXF rot=0 + base=90 = 90 deg
  place_fixture.call('CARE', 166.014307, 386.584559, 0.00, 1.000, 1.000, 1.000)  # DXF rot=0 + base=90 = 90 deg
  place_fixture.call('CARE', 219.557614, 386.584559, 0.00, 1.000, 1.000, 1.000)  # DXF rot=0 + base=90 = 90 deg
  place_fixture.call('TV_WALL', 248.203000, 98.269874, -90.00, 1.000, 1.000, 1.000)  # DXF rot=-90 + base=0 = -90 deg
  place_fixture.call('TV_WALL', 248.203000, 145.513969, -90.00, 1.000, 1.000, 1.000)  # DXF rot=-90 + base=0 = -90 deg
  place_fixture.call('TV_WALL', 248.203000, 192.758063, -90.00, 1.000, 1.000, 1.000)  # DXF rot=-90 + base=0 = -90 deg
  place_fixture.call('TV_WALL', 248.203000, 240.002157, -90.00, 1.000, 1.000, 1.000)  # DXF rot=-90 + base=0 = -90 deg
  place_fixture.call('AC_WALL', 238.308000, 301.222252, -90.00, 1.000, 1.000, 1.000)  # DXF rot=-90 + base=0 = -90 deg
  place_fixture.call('AC_WALL', 238.308000, 348.466346, -90.00, 1.000, 1.000, 1.000)  # DXF rot=-90 + base=0 = -90 deg
  place_fixture.call('CASH_COUNTER', 656.004260, 144.330425, 90.00, 1.000, 1.000, 1.000)  # DXF rot=90 + base=90 = 180 deg
  place_fixture.call('COUNTER', 639.763260, 210.866701, 90.00, 1.000, 1.000, 1.000)  # DXF rot=90 + base=0 = 90 deg
  place_fixture.call('COUNTER', 639.763260, 289.606858, 90.00, 1.000, 1.000, 1.000)  # DXF rot=90 + base=0 = 90 deg
  place_fixture.call('APPLE', 450.787945, 66.929197, 0.00, 1.000, 1.000, 1.000)  # DXF rot=0 + base=0 = 0 deg
  place_fixture.call('SAMSUNG', 435.641945, 215.932394, 0.00, 1.000, 1.000, 1.000)  # DXF rot=0 + base=-90 = -90 deg
  place_fixture.call('LAPTOP', 491.660031, 358.533126, 90.00, 1.000, 1.000, 1.000)  # DXF rot=90 + base=180 = 270 deg
  place_fixture.call('LAPTOP', 405.045858, 358.533126, 90.00, 1.000, 1.000, 1.000)  # DXF rot=90 + base=180 = 270 deg
  place_fixture.call('VIVO', 519.654079, 395.773780, 0.00, 1.000, 1.000, 1.000)  # DXF rot=0 + base=270 = 270 deg
  place_fixture.call('OPPO', 452.724945, 395.773780, 0.00, 1.000, 1.000, 1.000)  # DXF rot=0 + base=270 = 270 deg
  place_fixture.call('XIAOMI', 385.795811, 395.773780, 0.00, 1.000, 1.000, 1.000)  # DXF rot=0 + base=270 = 270 deg

  entity_count = ents.length
  model.commit_operation
  model.save("C:/Users/athul/Documents/3d_gen/build_floorplan.skp")
  UI.messagebox("Floor plan built and saved!  " + entity_count.to_s + " entities.\nSaved to: C:/Users/athul/Documents/3d_gen/build_floorplan.skp")
end

_build.call