# walkthrough_controls.rb
# Street View-style navigation panel for SketchUp walkthrough scenes.
#
# INSTALL: Copy to SketchUp Plugins folder and restart SketchUp.
# OPEN:    Extensions -> Walkthrough Controls

module WalkthroughControls

  HTML = <<~HTML
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }
      html, body {
        background: #1a1a2e;
        width: 100%; height: 100%;
        overflow: hidden;
        font-family: 'Segoe UI', Arial, sans-serif;
      }
      .overlay {
        position: fixed;
        bottom: 16px; left: 50%;
        transform: translateX(-50%);
        display: flex; flex-direction: column;
        align-items: center; gap: 8px;
      }
      .scene-pill {
        background: rgba(255,255,255,0.08);
        color: #bbb; font-size: 11px;
        letter-spacing: 0.5px;
        padding: 4px 14px; border-radius: 20px;
        white-space: nowrap;
      }
      .row { display: flex; gap: 12px; align-items: center; }
      .btn {
        background: #252545;
        border: 2px solid #3a3a6a;
        border-radius: 50%;
        color: #fff; cursor: pointer;
        display: flex; align-items: center; justify-content: center;
        transition: background 0.15s, transform 0.1s;
      }
      .btn:hover  { background: #5c6bc0; border-color: #7986cb; }
      .btn:active { transform: scale(0.90); }
      .btn-fwd {
        width: 68px; height: 68px;
        background: #5c6bc0; border-color: #7986cb;
        box-shadow: 0 4px 16px rgba(0,0,0,0.5);
      }
      .btn-fwd:hover { background: #3f51b5; }
      .btn-side { width: 50px; height: 50px; }
      .btn-play {
        background: #252545; border: 2px solid #3a3a6a;
        border-radius: 22px; color: #fff;
        cursor: pointer; font-size: 12px;
        letter-spacing: 1px; padding: 8px 18px;
        transition: background 0.15s;
        white-space: nowrap;
      }
      .btn-play:hover { background: #5c6bc0; }
      .btn-play:active { transform: scale(0.95); }
      .btn-play.on { background: #c62828; border-color: #e53935; }
      .btn-play.on:hover { background: #b71c1c; }
      svg { pointer-events: none; }
    </style>
    </head>
    <body>
      <div class="overlay">
        <div class="scene-pill" id="pill">Loading...</div>

        <div class="btn btn-fwd" onclick="sk('nextScene')" title="Forward">
          <svg width="30" height="30" viewBox="0 0 24 24" fill="white">
            <path d="M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z"/>
          </svg>
        </div>

        <div class="row">
          <div class="btn btn-side" onclick="sk('prevScene')" title="Previous">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="white">
              <path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/>
            </svg>
          </div>

          <div class="btn-play" id="playbtn" onclick="sk('togglePlay')">&#9654; PLAY</div>

          <div class="btn btn-side" onclick="sk('nextScene')" title="Next">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="white">
              <path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/>
            </svg>
          </div>
        </div>
      </div>

      <script>
        function sk(cb) {
          if (typeof sketchup !== 'undefined') sketchup[cb]();
        }
        function setPlaying(on) {
          var b = document.getElementById('playbtn');
          if (on) { b.innerHTML = '&#9646;&#9646; PAUSE'; b.classList.add('on'); }
          else     { b.innerHTML = '&#9654; PLAY';        b.classList.remove('on'); }
        }
        function setScene(name, i, total) {
          document.getElementById('pill').textContent = name + '  \u2022  ' + i + ' / ' + total;
        }
      </script>
    </body>
    </html>
  HTML

  # ── Public API ────────────────────────────────────────────────────────────

  def self.open_panel
    if @dialog && @dialog.visible?
      @dialog.bring_to_front
      return
    end

    @playing  = false
    @timer_id = nil

    @dialog = UI::HtmlDialog.new(
      dialog_title:    "Walkthrough",
      preferences_key: "WalkthroughNav2",
      width:  320,
      height: 210,
      resizable: false
    )
    @dialog.set_html(HTML)

    @dialog.add_action_callback("nextScene")   { |_| manual_next  }
    @dialog.add_action_callback("prevScene")   { |_| manual_prev  }
    @dialog.add_action_callback("togglePlay")  { |_| toggle_play  }

    @dialog.set_on_closed { stop_timer }

    @dialog.show

    # Delay label update slightly so dialog HTML is fully loaded
    UI.start_timer(0.5, false) { update_label }
  end

  # ── Navigation ────────────────────────────────────────────────────────────

  def self.pages
    Sketchup.active_model.pages.select { |p| p.name.start_with?("Walkthrough_") }
  end

  def self.current_index
    sel = Sketchup.active_model.pages.selected
    idx = pages.index(sel)
    idx || 0
  end

  def self.go_to(idx)
    list = pages
    return if list.empty?
    idx = idx % list.size
    Sketchup.active_model.pages.selected = list[idx]
    # Force the view to update to the new scene
    Sketchup.active_model.active_view.invalidate
    update_label
  end

  def self.manual_next
    stop_timer
    go_to(current_index + 1)
  end

  def self.manual_prev
    stop_timer
    go_to(current_index - 1)
  end

  # ── Playback ──────────────────────────────────────────────────────────────

  def self.toggle_play
    @playing ? stop_timer : start_timer
  end

  def self.start_timer
    return if @playing
    list = pages
    return if list.empty?
    @playing = true
    @dialog.execute_script("setPlaying(true)") rescue nil
    interval = [list.first.transition_time.to_f, 0.4].max
    @timer_id = UI.start_timer(interval, true) do
      go_to(current_index + 1) if @playing
    end
  end

  def self.stop_timer
    return unless @playing
    @playing = false
    UI.stop_timer(@timer_id) rescue nil
    @timer_id = nil
    @dialog.execute_script("setPlaying(false)") rescue nil
  end

  # ── Scene label ───────────────────────────────────────────────────────────

  def self.update_label
    return unless @dialog && @dialog.visible?
    list = pages
    return if list.empty?
    sel = Sketchup.active_model.pages.selected
    idx = list.index(sel) || 0
    name = list[idx].name
    @dialog.execute_script("setScene('#{name}', #{idx + 1}, #{list.size})")
  rescue => e
    puts "WalkthroughControls label error: #{e.message}"
  end

  # ── Menu ──────────────────────────────────────────────────────────────────

  unless file_loaded?(__FILE__)
    UI.menu("Extensions").add_item("Walkthrough Controls") { WalkthroughControls.open_panel }
    file_loaded(__FILE__)
  end

end
