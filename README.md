# Trash Royale: garbage sorting city game

A single-location StormHacks backend. An ESP32-S3 camera sends JPEGs to a Raspberry Pi over serial. The Pi waits for a new item to stop moving and classifies it once with Gemini into **recycling, compost, paper, garbage, or unknown**. With `--motors`, the Pi routes known categories through three A4988 motor drivers and credits the shared city after the routing cycle completes. Without that flag, bin confirmation is manual. The game saves its progress in SQLite and exposes a JSON API for the frontend.

The city has a daily randomized queue of eight projects. Recycling supplies building materials, compost supplies fertilizer, paper supplies exterior details, and garbage supplies energy. Each project changes appearance at construction milestones; excess of one resource goes to the next project, and contributions after all projects are full decorate the city. Completed landmarks and lifetime totals persist across days. A player can change the active project. Existing saves with fewer projects expand to eight while preserving their current projects and progress.

## Quick start on the Pi

Use Python 3.11 or newer. From the repository root, create the virtual environment if you do not already have one, then install the dependencies:

```bash
~/.local/bin/uv venv --python 3.11 .venv
~/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m server.app --demo --host 0.0.0.0
```

Open `http://PI_LOCAL_IP:8080` on a device on the same trusted network. The same Python process serves your teammate's illustrated **Trash Royale** frontend from [`frontend/`](frontend/) and the backend API. Tap a **+1** category button to simulate a correctly sorted item; these work in both demo and live camera modes alongside real camera scores. Choose a project in the right panel to direct new resources there. The browser polls the Pi about once per second, so changes appear across connected screens and survive a browser reload.

Stop the existing backend with Ctrl+C and restart it after updating these files. Run only one backend on port 8080. For an isolated test alongside an existing server, use `--port 8081 --database /tmp/little-river-test.sqlite3`.

Progress is saved to `game_state.sqlite3` in the current directory. Use `--database /path/to/file.sqlite3` and `--location "Your location"` to choose a save and city name. Reuse the same location name when reopening an existing save.

SQLite uses a write-ahead journal with full commit synchronization. Stop the backend before copying a save so the database and its journal are checkpointed together.

## Camera and Gemini mode

Flash [`esp32/esp32_cam_capture.ino`](esp32/esp32_cam_capture.ino) to the ESP32-S3 camera board with the pin mapping shown in that file. Connect the CH340 serial adapter to the Pi. The firmware and Python receiver both default to **460800 baud**. Stop any separate camera preview before running the game, because only one process can own the serial port.

Set the Gemini key in the Pi shell, keeping it out of shell history:

```bash
read -rsp 'Gemini API key: ' GEMINI_API_KEY; echo
export GEMINI_API_KEY
.venv/bin/python -m server.app --host 0.0.0.0 \
  --serial-port /dev/ttyUSB0 --baud 460800
```

Leave the sorting area empty for the first frame. Place one object and let your hand leave the view. The sorting status inside the current-project bar will show the item and predicted category. Without motors, tap the actual bin's confirmation button below the pending item after disposal; a wrong bin or `unknown` earns no resource. The **+1** buttons remain available for additional simulated scores. The camera must see the area clear before it classifies another item. If the empty reference was taken with an item present, clear the area and use **Reset empty-area reference**. `--model` overrides the default Gemini model; `--frame-interval` changes sampling time in seconds.

Without `--motors`, use manual bin confirmation. HTTP endpoints have no authentication; bind to `127.0.0.1` (the default) or use a trusted local network.

## Automatic motor routing

The C driver and its manual test program live in [`hardware/motor`](hardware/motor). Build the shared library on the Pi:

```bash
sudo apt-get install -y libgpiod-dev
make -C hardware/motor
```

With `GEMINI_API_KEY` set, start the camera and motor backend:

```bash
.venv/bin/python -m server.app --host 0.0.0.0 \
  --serial-port /dev/ttyUSB0 --baud 460800 --motors
```

| Gemini category | Motor input |
| --- | --- |
| `garbage` | 1 |
| `recycling` | 2 |
| `paper` | 3 |
| `compost` | 4 |
| `unknown` | No movement or resource credit |

Each recognized item runs one out/hold/return cycle. A completed cycle records one resource event with `source: "motor"` and its `motor_input`. Scene detection waits for the area to clear before accepting another item. Unknown items are cleared from pending state when the scene empties. A GPIO error blocks further routing and awards no resource for that item; inspect the gates and restart before continuing. A successful GPIO cycle is the current completion signal; there is no passage sensor or automatic homing.

Use `--motor-map 'garbage=1,recycling=2,paper=3,compost=4'` to change the bin arrangement, or `--motor-library /path/to/libmotor.so` to use a different library build. The hardware wiring and manual test instructions are in [`hardware/motor/README.md`](hardware/motor/README.md).

## Frontend integration

The integrated frontend lives in [`frontend/`](frontend/); the previous `server/static/` interface has been removed. The original artwork and illustrated style are preserved, with live sorting status inside the current-project bar. Daily projects and construction stages are rendered from the backend's saved state. See [`frontend/README.md`](frontend/README.md) for frontend development details.

All requests use relative `/api/...` paths. The frontend and backend run on the same Pi and domain, so no separate API URL is needed. Point the Cloudflare Tunnel route for `trashroyale.tech` to **HTTP** `127.0.0.1:8080`; visitors still use `https://trashroyale.tech`. Run the Python app rather than a separate frontend development server.

`GET /api/state` returns city resources, projects, event history, `pending`, `last_classification`, `status`, `error`, and a `motor` object containing `enabled`, `routing`, `faulted`, and the category-to-input mapping. `GET /api/frame` returns the latest JPEG. `POST /api/project` accepts `{"id": "project-id"}` to select a project; `POST /api/reset_scene` accepts `{}` to reset the empty-area reference. `POST /api/dismiss` dismisses an unknown or failed pending item without scoring it.

**Reset game** in the current-project bar starts a new shared village after confirmation. `POST /api/reset_game` accepts `{}`, clears all saved progress, completed buildings, decorations, totals, history, and pending items, and returns the new state with a freshly randomized map and eight projects. It rejects resets while classification or motor routing is underway. Camera settings, the empty-area reference, and hardware fault state are preserved. The new village survives a backend restart.

Motor mode records successful routes automatically. `POST /api/confirm` accepts `{"bin": "category"}` only in manual mode. `POST /api/demo_sort` accepts `{"category": "recycling|compost|paper|garbage"}` in every mode and records exactly one completed simulated sort per successful request, without consuming a pending item or changing camera or motor state. The existing `/api/demo_item` endpoint supports testing a classification followed by manual confirmation in demo mode. No HTTP endpoint directly moves the motors; movement comes from a new, settled camera item and a valid Gemini category.

## Individual camera and classifier checks

Capture JPEGs without OpenCV using:

```bash
.venv/bin/python -m server.esp32_cam_rcv --port /dev/ttyUSB0 --baud 460800 \
  --headless --save-latest server/latest.jpg
```

Classify one saved JPEG (with `GEMINI_API_KEY` set):

```bash
.venv/bin/python -m server.gemini_classifier --image server/latest.jpg \
  --labels recycling,compost,paper,garbage
```

The camera preview command without `--headless` additionally needs `opencv-python` and `numpy`. The game itself uses Pillow to compare small grayscale thumbnails and does not need OpenCV.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The motor tests compile the production C source with simulated GPIO calls and timing, so tests do not move hardware. The actual library build requires libgpiod v1, matching Debian Bullseye's development package.
