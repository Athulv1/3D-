model = Sketchup.active_model
ents = model.active_entities
puts '%-20s %10s %10s %10s %10s %10s %10s' % ['NAME','INS_X','INS_Y','CTR_X','CTR_Y','OFF_X','OFF_Y']
puts '-'*80
ents.grep(Sketchup::ComponentInstance).each do |ci|
  name = ci.definition.name
  ins  = ci.transformation.origin
  ctr  = ci.bounds.center
  ox   = (ctr.x - ins.x).round(3)
  oy   = (ctr.y - ins.y).round(3)
  puts '%-20s %10.3f %10.3f %10.3f %10.3f %10.3f %10.3f' % [name[0..19], ins.x, ins.y, ctr.x, ctr.y, ox, oy]
end