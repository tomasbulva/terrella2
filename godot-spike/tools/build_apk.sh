#!/usr/bin/env bash
# Builds build/terrella-spike.apk without Gradle:
#   Godot export (prebuilt template) -> compile host Java -> dex -> apktool patch manifest -> align -> sign.
# Needs: GODOT, ANDROID_JAR, GODOT_LIB_JAR, CP_JAR (androidx stubs), APKTOOL, dalvik-exchange, zipalign, apksigner.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT:-$HOME/tools/godot}"
ANDROID_JAR="${ANDROID_JAR:-$HOME/android-sdk/platforms/android-36/android.jar}"
GODOT_LIB_JAR="${GODOT_LIB_JAR:-$HOME/tools/cp/godot-lib.jar}"
CP_JAR="${CP_JAR:-$HOME/tools/cp/classes.jar}"
APKTOOL="${APKTOOL:-$HOME/tools/apktool.jar}"
KEYSTORE="${KEYSTORE:-$HOME/spike-release.keystore}"
JAVAC="${JAVAC:-/usr/lib/jvm/java-17-openjdk-amd64/bin/javac}"
WORK="$(mktemp -d)"
OUT="$ROOT/build/terrella-spike.apk"
mkdir -p "$ROOT/build"

echo "== Godot export"
"$GODOT" --headless --path "$ROOT" --export-release Android "$WORK/base.apk" >"$WORK/export.log" 2>&1 || { tail -40 "$WORK/export.log"; exit 1; }

echo "== Compile host Java"
mkdir -p "$WORK/classes"
"$JAVAC" -source 8 -target 8 -nowarn -Xlint:-options -bootclasspath "$ANDROID_JAR" \
  -cp "$GODOT_LIB_JAR:$CP_JAR" -d "$WORK/classes" "$ROOT"/host/*.java 2>&1 | grep -v JAVA_TOOL || true
(cd "$WORK/classes" && dalvik-exchange --dex --min-sdk-version=26 --output="$WORK/classes2.dex" . 2>&1 | grep -v JAVA_TOOL || true)
test -f "$WORK/classes2.dex"

echo "== Patch APK"
java -jar "$APKTOOL" d -s -f -o "$WORK/dec" "$WORK/base.apk" 2>&1 | grep -v JAVA_TOOL | grep -iE "error|exception" || true
cp "$WORK/classes2.dex" "$WORK/dec/classes2.dex"
mkdir -p "$WORK/dec/res/xml"
cp "$ROOT/host/terrella_wallpaper.xml" "$WORK/dec/res/xml/"
python3 - "$WORK/dec" <<'PY'
import sys, os
d = sys.argv[1]
p = os.path.join(d, "AndroidManifest.xml"); s = open(p).read()
inject = """        <meta-data android:name="org.godotengine.plugin.v2.TerrellaSpike" android:value="com.godot.game.SpikePlugin"/>
        <service android:name="com.godot.game.TerrellaWallpaperService" android:label="Terrella diorama"
            android:process=":wallpaper" android:exported="true" android:permission="android.permission.BIND_WALLPAPER">
            <intent-filter><action android:name="android.service.wallpaper.WallpaperService"/></intent-filter>
            <meta-data android:name="android.service.wallpaper" android:resource="@xml/terrella_wallpaper"/>
        </service>
    </application>"""
assert s.count("</application>") == 1
s = s.replace("    </application>", inject, 1)
s = s.replace('<uses-feature android:glEsVersion', '<uses-feature android:name="android.software.live_wallpaper" android:required="false"/>\n    <uses-feature android:glEsVersion', 1)
open(p, "w").write(s)
# apktool cannot recompile Godot's boolean placeholder mipmap; it is unused, point it at a real icon.
m = os.path.join(d, "res/values-anydpi-v26/mipmaps.xml")
if os.path.exists(m):
    t = open(m).read().replace('name="themed_icon">false<', 'name="themed_icon">@mipmap/icon_monochrome<')
    open(m, "w").write(t)
PY
java -jar "$APKTOOL" b -o "$WORK/unsigned.apk" "$WORK/dec" 2>&1 | grep -v JAVA_TOOL | grep -iE "error|exception|W:" || true
test -f "$WORK/unsigned.apk"
zipalign -f -p 4 "$WORK/unsigned.apk" "$WORK/aligned.apk"
apksigner sign --ks "$KEYSTORE" --ks-pass "pass:${KS_PASS:?set KS_PASS}" --ks-key-alias "${KS_ALIAS:-spike}" --key-pass "pass:${KS_PASS}" --out "$OUT" "$WORK/aligned.apk" 2>&1 | grep -v JAVA_TOOL || true
apksigner verify "$OUT" 2>&1 | grep -v JAVA_TOOL || true
rm -f "$OUT.idsig"
ls -la "$OUT"
rm -rf "$WORK"
