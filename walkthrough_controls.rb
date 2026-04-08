# walkthrough_controls.rb
# Google Street View-style navigation overlay for SketchUp walkthrough.
# Floating transparent panel with directional arrows.
#
# INSTALL ONCE:
#   Copy to SketchUp Plugins folder:
#   C:\Users\athul\AppData\Roaming\SketchUp\SketchUp 2026\SketchUp\Plugins\
#   Then restart SketchUp.
#
# OPEN: Extensions -> Walkthrough Controls

module WalkthroughControls

  HTML = <<~HTML
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }

      html, body {
        background: transparent;
        width: 100%;
        height: 100%;
        overflow: hidden;
        font-family: 'Segoe UI', Arial, sans-serif;
      }

      /* Full-size layout — arrows pinned to bottom center */
      .overlay {
        position: fixed;
        bottom: 24px;
        left: 50%;
        transform: translateX(-50%);
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 6px;
      }

      /* Scene info pill */
      .scene-pill {
        background: rgba(0,0,0,0.55);
        color: #eee;
        font-size: 11px;
        letter-spacing: 0.5px;
        padding: 4px 14px;
        border-radius: 20px;
        margin-bottom: 4px;
        white-space: nowrap;
      }

      /* Arrow row */
      .row { display: flex; gap: 10px; align-items: center; }

      /* Base arrow button */
      .arrow {
        background: rgba(20, 20, 40, 0.72);
        border: 2px solid rgba(255,255,255,0.18);
        border-radius: 50%;
        color: #fff;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: background 0.15s, transform 0.1s, border-color 0.15s;
        backdrop-filter: blur(6px);
        -webkit-backdrop-filter: blur(6px);
      }
      .arrow:hover  {
        background: rgba(92, 107, 192, 0.85);
        border-color: rgba(255,255,255,0.5);
      }
      .arrow:active { transform: scale(0.90); }

      /* Forward — large centre arrow */
      .arrow-fwd {
        width: 72px;
        height: 72px;
        font-size: 32px;
        background: rgba(92, 107, 192, 0.80);
        border-color: rgba(255,255,255,0.35);
        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
      }
      .arrow-fwd:hover { background: rgba(63, 81, 181, 0.95); }

      /* Side — prev / next */
      .arrow-side {
        width: 52px;
        height: 52px;
        font-size: 20px;
      }

      /* Play/Pause pill */
      .play-btn {
        background: rgba(20,20,40,0.72);
        border: 2px solid rgba(255,255,255,0.18);
        border-radius: 24px;
        color: #fff;
        cursor: pointer;
        font-size: 12px;
        letter-spacing: 1px;
        padding: 7px 20px;
        margin-top: 6px;
        transition: background 0.15s;
        backdrop-filter: blur(6px);
      }
      .play-btn:hover  { background: rgba(92,107,192,0.85); }
      .play-btn:active { transform: scale(0.95); }
      .play-btn.playing { background: rgba(183,28,28,0.75); }
      .play-btn.playing:hover { background: rgba(183,28,28,0.95); }

      /* SVG arrow icons */
      svg { pointer-events: none; }
    </style>
    </head>
    <body>
      <div class="overlay">
        <div class="scene-pill" id="scene-pill">Scene — / —</div>

        <!-- Forward arrow (centre, big) -->
        <div>
          <div class="arrow arrow-fwd" onclick="goFwd()" title="Move forward">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="white">
              <path d="M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z"/>
            </svg>
          </div>
        </div>

        <!-- Left / Right -->
        <div class="row">
          <div class="arrow arrow-side" onclick="goPrev()" title="Previous scene">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="white">
              <path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/>
            </svg>
          </div>

          <!-- Play/Pause pill between L/R arrows -->
          <div class="play-btn" id="play-btn" onclick="togglePlay()">&#9654; PLAY</div>

          <div class="arrow arrow-side" onclick="goNext()" title="Next scene">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="white">
              <path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/>
            </svg>
          </div>
        </div>
      </div>

      <script>
        var playing = false;

        function goFwd()      { sketchup.nextScene(); }
        function goNext()     { sketchup.nextScene(); }
        function goPrev()     { sketchup.prevScene(); }

        function togglePlay() {
          playing = !playing;
          var btn = document.getElementById('play-btn');
          if (playing) {
            btn.innerHTML = '&#9646;&#9646; PAUSE';
            btn.classList.add('playing');
          } else {
            btn.innerHTML = '&#9654; PLAY';
            btn.classList.remove('playing');
          }
          sketchup.togglePlay();
        }

        function updateScene(name, index, total) {
          document.getElementById('scene-pill').textContent =
            name + '  \u2022  ' + index + ' / ' + total;
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
      dialog_title:    "Walkthrough",
      preferences_key: "WalkthroughNav",
      width:           340,
      height:          220,
      min_width:       340,
      min_height:      220,
      resizable:       false,
      style:           UI::HtmlDialog::STYLE_UTILITY
    )

    @dialog.set_html(HTML)
    @playing = false

    @dialog.add_action_callback("nextScene") { |_|
      Sketchup.send_action("nextPage:")
      update_scene_label
    }

    @dialog.add_action_callback("prevScene") { |_|
      Sketchup.send_action("previousPage:")
      update_scene_label
    }

    @dialog.add_action_callback("togglePlay") { |_|
      @playing = !@playing
      Sketchup.send_action("playpauseAnimation:")
    }

    @observer = WalkthroughPageObserver.new
    Sketchup.active_model.pages.add_observer(@observer)

    @dialog.set_on_closed {
      Sketchup.active_model.pages.remove_observer(@observer) rescue nil
      @playing = false
    }

    @dialog.show
    update_scene_label
  end

  def self.update_scene_label
    return unless @dialog && @dialog.visible?
    model = Sketchup.active_model
    pages = model.pages.select { |p| p.name.start_with?("Walkthrough_") }
    sel   = model.pages.selected
    return unless sel && pages.include?(sel)
    idx = pages.index(sel)
    @dialog.execute_script(
      "updateScene('#{sel.name}', #{idx + 1}, #{pages.size})"
    )
  end

  class WalkthroughPageObserver < Sketchup::PagesObserver
    def onContentsModified(_pages)
      WalkthroughControls.update_scene_label rescue nil
    end
  end

  unless file_loaded?(__FILE__)
    menu = UI.menu("Extensions")
    menu.add_item("Walkthrough Controls") { WalkthroughControls.open_panel }
    file_loaded(__FILE__)
  end
end
