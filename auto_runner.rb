# AutoRunner Plugin for SketchUp
# Watches for a trigger file and auto-executes Ruby scripts sequentially.
# Trigger file may contain ONE or TWO script paths (one per line).
# If two scripts: runs script1 immediately, then script2 after a 6-second delay
# (giving SketchUp time to finish the first operation and save the .skp).
#
# INSTALL ONCE:
#   Copy this file to your SketchUp Plugins folder:
#   C:\Users\athul\AppData\Roaming\SketchUp\SketchUp 2026\SketchUp\Plugins\
#   Then restart SketchUp.

module AutoRunnerPlugin
  TRIGGER = 'C:/Users/athul/Documents/3d/run_trigger.txt'
  WALKTHROUGH_DELAY = 8.0  # seconds to wait before running script2

  def self.run_script(path, label)
    if path.nil? || path.empty? || !path.end_with?('.rb')
      puts "AutoRunner: invalid script path (#{label}): '#{path}'"
      return
    end
    unless File.exist?(path)
      UI.messagebox("AutoRunner: script not found (#{label}):\n#{path}")
      return
    end
    puts "AutoRunner: loading #{label} -> #{path}"
    begin
      load path
    rescue => e
      UI.messagebox("AutoRunner error (#{label}):\n#{e.message}\n\n#{e.backtrace.first(3).join("\n")}")
    end
  end

  def self.start
    # Clean up stale trigger from previous session
    if File.exist?(TRIGGER)
      lines = File.readlines(TRIGGER).map(&:strip).reject(&:empty?) rescue []
      valid = lines.all? { |l| l.end_with?('.rb') && File.exist?(l) }
      unless valid
        File.delete(TRIGGER) rescue nil
        puts "AutoRunner: deleted stale trigger"
      end
    end

    UI.start_timer(2.0, true) do
      if File.exist?(TRIGGER)
        lines = File.readlines(TRIGGER).map(&:strip).reject(&:empty?) rescue []
        File.delete(TRIGGER) rescue nil
        puts "AutoRunner: trigger detected — #{lines.size} script(s)"

        script1 = lines[0]
        script2 = lines[1]

        # Run first script immediately (floor plan build)
        run_script(script1, "script1") if script1

        # Run second script after delay (walkthrough — needs skp saved first)
        if script2
          puts "AutoRunner: scheduling walkthrough in #{WALKTHROUGH_DELAY}s..."
          UI.start_timer(WALKTHROUGH_DELAY, false) do
            run_script(script2, "walkthrough")
          end
        end
      end
    end

    puts "AutoRunner loaded — watching for trigger file."
  end
end

AutoRunnerPlugin.start unless defined?(AutoRunnerPlugin::STARTED)
AutoRunnerPlugin::STARTED = true
