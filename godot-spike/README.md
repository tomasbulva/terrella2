# Terrella engine spike (Godot 4.7.2)

One Godot project that runs as both the explorable app and an Android live wallpaper. The goal is to measure whether Godot is good enough on real phones (Pixel 7, Pixel 9 Pro) before committing to it.

The scene is a **stand-in** procedural Amsterdam canal: two rows of leaning gabled houses, water, a bridge, trees and lamps. It has moving life (a boat, bikes, people, ducks, clouds), day/night, seasons, weather particles and a three-tulip treasure hunt. Finding all three tulips plays a reward animation and grants a golden-windmill collectible. **Controls → Scene → Pipeline kit** switches to the asset pipeline's assembled canal diorama (`diorama/kit_canal.glb` plus `kit_canal.puzzle.json`, built from 25 kit pieces, about 19.6k triangles and 91 meshes). It is copied from `terrella-v2/asset-pipeline/out/dioramas/`. A kit shader reads the palette-atlas role from the UVs, so windows glow at night and snow, autumn and water work without per-asset materials. Tulips hide at the diorama's `hide_spot` entities. The moving boat, bikes and people are stand-in only. The switch applies to the app and the wallpaper within about 3 s.
When `diorama/diorama.glb` exists (the `dutch_houses.py` export), it replaces the stand-in. Materials named water / window / leaf are swapped for the spike shaders.

## Install
`adb install -r terrella-spike.apk`, or copy the APK to the phone and open it (allow "install unknown apps").
It needs Android 7+ and arm64. It is signed with a throwaway spike key.

## What gets measured
Each process (app, wallpaper) writes its own CSV to `Android/data/com.terrella.spike/files/metrics/`. It writes one row per second while visible and one per 10 s while hidden:
- **Godot:** fps, frame interval (avg/max), draw calls, primitives, VRAM, Godot static memory
- **Process:** PSS, Java heap, CPU % of one core
- **Device:** battery current (µA), charge counter (µAh), battery %, temperature, voltage, plugged state, thermal status and headroom
- **Events:** `first_frame` (ms from process start), `engine_init`, `attach`/`detach` (wallpaper surface hand-over), `visible`/`hidden`, settings changes, `tulip_found`, `reward`, and `error_*` if the wallpaper engine fails to start

To get the files off the phone, use **Controls → Share CSVs** (Drive, email and so on), or run `adb pull /sdcard/Android/data/com.terrella.spike/files/metrics`.
Then run `python3 tools/analyze.py metrics/` to get a markdown table per segment.

**Battery numbers are only valid unplugged.** The HUD warns when plugged in, and analyze.py drops those rows.

## Test protocol (same for both phones)
Fix the conditions first: brightness at 50% with adaptive brightness off, screen timeout at 30 min, other apps closed, battery between 30% and 90%, phone at room temperature, unplugged. Start each run with **Controls → Clear CSVs**. Run each test for 10 minutes.

1. **Baseline wallpaper:** set the wallpaper (**Controls → Set wallpaper**) with Wallpaper fps **1 (near static)**. Sit on the home screen.
2. **Wallpaper 30 fps, Vulkan, High.** This is the default.
3. **Wallpaper 15 fps** and **60 fps** (one run each).
4. **Wallpaper 30 fps, Low quality** (no shadows, no glow, 0.75 render scale).
5. **Scene: Pipeline kit**, then repeat test 2. Expect about 4× the draw calls, because the kit diorama is not merged yet.
6. **Renderer GL (Compatibility)**, then repeat test 2. Switching the renderer restarts the app and the wallpaper process.
7. **App explore, 60 fps:** open the app, hide the controls, and orbit, zoom and hunt tulips the whole time.
8. **App idle, 60 fps:** open the app and don't touch it.
9. **Robustness:** with the wallpaper set, open the wallpaper picker preview, go back, lock and unlock 10×, and rotate through apps. Note any black frame, freeze or crash. `error_*` events land in the CSV.
10. **Cold start:** force-stop the app from Settings, then go to the home screen. The wallpaper CSV gets `first_frame`.

Weather, season and time set in the app also apply to the wallpaper within about 3 s. Snow plus night is the heaviest scene.

## Known gaps
- **The wallpaper path is untested on hardware.** Godot runs in its own `:wallpaper` process, because Godot allows one instance per process. Its internal SurfaceView is redirected to the wallpaper surface with `Surface.readFromParcel`, a public API. It is verified to build, not to run, because there is no emulator here.
- **Frame pacing (Swappy) is off in both modes**, since it requires an Activity. If the app stutters, that is the first suspect.
- **Not live yet:** location, weather (open-meteo) and the sun's latitude.
- **The look is placeholder:** flat vertex colours, no baked AO, no textures. Treat performance as a lower bound for a textured asset.

## Build (no Gradle)
Google's Maven and SDK hosts were blocked in the build container, so `tools/build_apk.sh` takes a different route. It exports with Godot's prebuilt template, compiles `host/*.java` with javac and dx, then uses apktool to patch the manifest (wallpaper service and plugin) before signing. In a normal environment you can instead enable Gradle build in `export_presets.cfg` and put `host/*.java` into `android/build/src`.
