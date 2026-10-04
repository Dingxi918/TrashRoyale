# Trash Royale frontend

The Python backend serves this folder and its API from the same origin. From the repository root:

```bash
.venv/bin/python -m server.app --demo --host 0.0.0.0
```

Open `http://PI_LOCAL_IP:8080/`. The frontend needs the backend; opening the HTML file directly or using a separate IDE static server will not connect to the game. No Node build, API URL setting, or CORS configuration is needed.

`index.html` contains the parchment panels and sorting controls, `style.css` keeps the illustrated design, and `game.js` renders the village from `/api/state`. Project requirements, selection, resource allocation, daily rollover, and saved progress belong to `server/game.py` and SQLite. The backend's daily queue has eight projects; the counter follows the API rather than a fixed number. Existing Pi saves are reused and smaller daily queues expand without losing progress. Browser-local prototype saves are not imported.

The panels use a responsive grid: wide windows show sidebars around the map, compact windows place resources above it, and narrow windows stack the panels into a scrollable page. The current-project bar spans the space below the resources and map. Project names and descriptions wrap, sorting buttons keep their icons and labels aligned, and the canvas fits its own map area without stretching the village. Short windows scroll so controls remain accessible.

The four **+1** category buttons post a simulated sort to `/api/demo_sort` in every mode. They can add demo resources alongside real camera items, including during automatic motor routing, and never move motors or consume a pending camera classification. Without motors, separate bin-confirmation buttons appear below a pending item and use `/api/confirm`; a completed motor cycle credits resources automatically. Unknown camera classifications award no resource. Live camera status, pending items, errors, and empty-reference controls appear within the current-project bar; the standalone demo status panel has been removed.

**Reset game** in the current-project bar opens a confirmation dialog and posts `{}` to `/api/reset_game`. It clears all shared project progress, completed buildings, resources, decorations, and sorting history, then generates a new saved map and eight fresh projects. All connected screens update to the new village, and pan/zoom return to the initial view. Canceling keeps the existing game. Reset waits until classification or motor routing has finished and preserves the camera reference and hardware fault state.

`window.ecoCitySort(type)` and same-origin `{kind: 'eco-sort', type}` messages add the same simulated resources as the **+1** buttons. `ecoCitySort` returns a promise. Manual camera confirmations use the separate bin controls; neither frontend action invokes motors.

The page polls once per second and animates new confirmed resource events. Disconnected screens keep their last village view and disable actions until the Pi responds. All connected screens use the same saved city.

Drag the village to pan, scroll over it to zoom, or use two fingers to pinch on a touchscreen. `map-navigation.js` updates the single canvas camera for terrain, buildings, particles, and the floating island. The island's rim follows the outer tile anchors, and its generated rock texture is projected onto two tapered faces beneath the land. The initial view includes the island's full depth; resizing preserves the user's zoom and pan. The generated material and its prompt are in `assets/cliffs/floating_island_rock.png` and `assets/cliffs/floating_island_rock-prompt.txt`.

The deeper cliffs include moss, hanging vines, flowers, mineral flecks, and floating stone fragments. `island-effects.js` locates the river's outlets from the current terrain and draws a waterfall at each end: the rear cascade falls vertically behind the island, while the front cascade spills over the visible cliff. Water streaks, spray, mist, drifting leaves, and light motes animate in the same world coordinates as the map. Particle counts stay fixed, static rock and terrain layers are cached, and animation is capped at 24 frames per second. Atmospheric motion pauses while the map is offscreen or the document is hidden; reduced-motion settings keep the scene still.

`asset_manifest_original.json` and `ART_ASSETS_NOTE.txt` document the artwork. Images remain in `assets/` with their original names. Replace `assets/background/full_landscape.png` to change the default background, or preview `?background=sunny|sunset|autumn|evening|misty`. The duplicate `.txt` source copies and previous backend placeholder frontend have been removed.
