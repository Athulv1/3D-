# walkthrough_controls.rb
# Floating navigation panel for walkthrough scenes.
#
# INSTALL ONCE:
#   Copy to SketchUp Plugins folder:
#   C:\Users\athul\AppData\Roaming\SketchUp\SketchUp 2026\SketchUp\Plugins\
#   Then restart SketchUp.
#
# OPEN PANEL:
#   Extensions -> Walkthrough Controls
#   (also auto-opens after create_walkthrough.rb runs)

module WalkthroughControls
  PANEL_W = 320
  PANEL_H = 130

  HTML = <<~HTML
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body {
        background: #12121f;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 100vh;
        font-family: 'Segoe UI', Arial, sans-serif;
        user-select: none;
      }
      #scene-label {
        color: #888;
        font-size: 11px;
        letter-spacing: 1px;
        text-transform: uppercase;
        margin-bottom: 10px;
      }
      #scene-name {
        color: #ddd;
        font-size: 13px;
        font-weight: 500;
        margin-bottom: 14px;
        max-width: 280px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .controls {
        display: flex;
        gap: 12px;
        align-items: center;
      }
      .btn {
        background: #1e1e35;
        color: #ccc;
        border: 1px solid #333;
        border-radius: 10px;
        width: 52px;
        height: 44px;
        font-size: 18px;
        cursor: pointer;
        transition: background 0.15s, transform 0.1s;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .btn:hover  { background: #2a2a4a; border-color: #555; }
      .btn:active { transform: scale(0.93); }
      .btn-play {
        background: #5c6bc0;
        border-color: #5c6bc0;
        color: #fff;
        width: 64px;
        height: 52px;
        font-size: 22px;
        border-radius: 12px;
      }
      .btn-play:hover  { background: #3f51b5; border-color: #3f51b5; }
      .btn-play.paused { background: #e53935; border-color: #e53935; }
      .btn-play.paused:hover { background: #c62828; }
    </style>
    </head>
    <body>
      <div id="scene-label">Walkthrough</div>
      <div id="scene-name">—</div>
      <div class="controls">
        <button class="btn" id="btn-prev" title="Previous scene" onclick="goTo(-1)">&#9664;</button>
        <button class="btn btn-play" id="btn-play" title="Play / Pause" onclick="togglePlay()">&#9654;</button>
        <button class="btn" id="btn-next" title="Next scene" onclick="goTo(1)">&#9654;&#9654;</button>
      </div>
      <script>
        var playing = false;

        function goTo(dir) {
          if (dir < 0) sketchup.prevScene();
          else         sketchup.nextScene();
        }

        function togglePlay() {
          playing = !playing;
          var btn = document.getElementById('btn-play');
          if (playing) {
            btn.innerHTML = '&#9646;&#9646;';
            btn.classList.add('paused');
          } else {
            btn.innerHTML = '&#9654;';
            btn.classList.remove('paused');
          }
          sketchup.togglePlay();
        }

        function setPlaying(val) {
          playing = val;
          var btn = document.getElementById('btn-play');
          if (playing) {
            btn.innerHTML = '&#9646;&#9646;';
            btn.classList.add('paused');
          } else {
            btn.innerHTML = '&#9654;';
            btn.classList.remove('paused');
          }
        }

        function updateScene(name, index, total) {
          document.getElementById('scene-name').textContent =
            name + '  (' + index + ' / ' + total + ')';
        }
      </script>
    </body>
    </html>
  HTML

  def self.open_panel
    if @dialog && @dialog.visible?
      @dialog.bring_to_front
      return
    end

    @dialog = UI::HtmlDialog.new(
      dialog_title:    "Walkthrough Controls",
      preferences_key: "WalkthroughControlsPanel",
      width:           PANEL_W,
      height:          PANEL_H,
      min_width:       PANEL_W,
      min_height:      PANEL_H,
      resizable:       false
    )

    @dialog.set_html(HTML)
    @playing = false

    @dialog.add_action_callback("prevScene") { |_|
      Sketchup.send_action("previousPage:")
      update_scene_label
    }

    @dialog.add_action_callback("nextScene") { |_|
      Sketchup.send_action("nextPage:")
      update_scene_label
    }

    @dialog.add_action_callback("togglePlay") { |_|
      @playing = !@playing
      Sketchup.send_action("playpauseAnimation:")
    }

    # Update label whenever the active scene changes
    @observer = WalkthroughPageObserver.new(@dialog)
    Sketchup.active_model.pages.add_observer(@observer)

    @dialog.set_on_closed {
      Sketchup.active_model.pages.remove_observer(@observer) rescue nil
    }

    @dialog.show
    update_scene_label
  end

  def self.update_scene_label
    return unless @dialog && @dialog.visible?
    model = Sketchup.active_model
    pages = model.pages.select { |p| p.name.start_with?("Walkthrough_") }
    sel   = model.pages.selected
    return unless sel
    idx   = pages.index(sel)
    return unless idx
    @dialog.execute_script(
      "updateScene('#{sel.name}', #{idx + 1}, #{pages.size})"
    )
  end

  # Observer to sync the label when SketchUp changes scenes during animation
  class WalkthroughPageObserver < Sketchup::PagesObserver
    def initialize(dialog)
      @dialog = dialog
    end
    def onContentsModified(pages)
      WalkthroughControls.update_scene_label rescue nil
    end
  end

  # ── Menu entry ──────────────────────────────────────────────────────────────
  unless file_loaded?(__FILE__)
    menu = UI.menu("Extensions")
    menu.add_item("Walkthrough Controls") { WalkthroughControls.open_panel }
    file_loaded(__FILE__)
  end
end
