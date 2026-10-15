package com.godot.game;

import android.app.Activity;
import android.app.ActivityManager;
import android.app.WallpaperManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Process;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.core.content.FileProvider;

import org.godotengine.godot.Godot;
import org.godotengine.godot.plugin.GodotPlugin;
import org.godotengine.godot.plugin.UsedByGodot;

import java.io.File;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Bridge between GDScript and the Android host: mode, settings, metrics, wallpaper helpers. */
public class SpikePlugin extends GodotPlugin {
	private static final String TAG = "TerrellaSpike";

	/** Set by the wallpaper service before the engine starts. "app" otherwise. */
	public static volatile String hostMode = "app";
	public static volatile boolean preview = false;
	public static volatile float xOffset = 0.5f;
	public static volatile boolean visible = true;

	private static final java.io.FilenameFilter CSV = new java.io.FilenameFilter() {
		public boolean accept(File d, String n) { return n.endsWith(".csv"); }
	};

	public SpikePlugin(Godot godot) {
		super(godot);
	}

	@NonNull
	@Override
	public String getPluginName() {
		return "TerrellaSpike";
	}

	private Context ctx() {
		return getGodot().getContext();
	}

	private SpikeMetrics metrics() {
		return SpikeMetrics.get(ctx(), hostMode);
	}

	@NonNull
	@Override
	public List<String> getCommandLineParams(@NonNull List<String> original) {
		String[] args = SpikeSettings.rendererArgs(ctx());
		metrics().setRenderer(SpikeSettings.get(ctx(), "renderer", "vulkan"));
		Log.i(TAG, "Renderer args for " + hostMode + ": " + Arrays.toString(args));
		return new ArrayList<>(Arrays.asList(args));
	}

	@Override
	public void onMainResume() {
		if ("app".equals(hostMode)) {
			metrics().setVisible(true);
		}
	}

	@Override
	public void onMainPause() {
		if ("app".equals(hostMode)) {
			metrics().setVisible(false);
		}
	}

	@UsedByGodot
	public String getMode() {
		return preview ? "preview" : hostMode;
	}

	@UsedByGodot
	public float getXOffset() {
		return xOffset;
	}

	@UsedByGodot
	public String getSetting(String key, String def) {
		return SpikeSettings.get(ctx(), key, def);
	}

	@UsedByGodot
	public void setSetting(String key, String value) {
		SpikeSettings.set(ctx(), key, value);
	}

	@UsedByGodot
	public void reportFrame(float fps, float frameMs, float frameMsMax, float drawCalls, float primitives, float vramMb, float staticMb) {
		metrics().reportFrame(fps, frameMs, frameMsMax, drawCalls, primitives, vramMb, staticMb);
	}

	@UsedByGodot
	public void firstFrame() {
		metrics().firstFrame();
	}

	@UsedByGodot
	public void logEvent(String name) {
		metrics().event(name.replace(',', ' '), 0);
	}

	@UsedByGodot
	public void setLabel(String label) {
		metrics().setLabel(label);
	}

	@UsedByGodot
	public void setVariant(String variant) {
		metrics().setVariant(variant);
	}

	@UsedByGodot
	public void setFpsCap(int cap) {
		metrics().setFpsCap(cap);
	}

	@UsedByGodot
	public String getSummary() {
		return metrics().summary();
	}

	@UsedByGodot
	public String getMetricsDir() {
		return metrics().dir().getAbsolutePath();
	}

	/** Opens the system live-wallpaper preview for our service. */
	@UsedByGodot
	public void setAsWallpaper() {
		final Activity a = getActivity();
		if (a == null) {
			return;
		}
		a.runOnUiThread(new Runnable() { public void run() {
			Intent i = new Intent(WallpaperManager.ACTION_CHANGE_LIVE_WALLPAPER);
			i.putExtra(WallpaperManager.EXTRA_LIVE_WALLPAPER_COMPONENT, new ComponentName(a, TerrellaWallpaperService.class));
			try {
				a.startActivity(i);
			} catch (Exception e) {
				a.startActivity(new Intent(WallpaperManager.ACTION_LIVE_WALLPAPER_CHOOSER));
			}
		} });
	}

	/** Kills the wallpaper process so it restarts with new settings (Android re-binds it automatically). */
	@UsedByGodot
	public void restartWallpaper() {
		ActivityManager am = (ActivityManager) ctx().getSystemService(Context.ACTIVITY_SERVICE);
		List<ActivityManager.RunningAppProcessInfo> procs = am.getRunningAppProcesses();
		if (procs == null) {
			return;
		}
		for (ActivityManager.RunningAppProcessInfo p : procs) {
			if (p.processName.endsWith(":wallpaper")) {
				Log.i(TAG, "Killing wallpaper process " + p.pid);
				Process.killProcess(p.pid);
			}
		}
	}

	/** Restarts the app process (used after switching renderer). */
	@UsedByGodot
	public void restartApp() {
		final Activity a = getActivity();
		if (a == null) {
			return;
		}
		restartWallpaper();
		Intent i = a.getPackageManager().getLaunchIntentForPackage(a.getPackageName());
		if (i != null) {
			i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
			a.startActivity(i);
		}
		Process.killProcess(Process.myPid());
	}

	/** Shares every CSV in the metrics folder (both processes write there). */
	@UsedByGodot
	public void shareMetrics() {
		final Activity a = getActivity();
		if (a == null) {
			return;
		}
		File[] files = metrics().dir().listFiles(CSV);
		if (files == null || files.length == 0) {
			return;
		}
		ArrayList<Uri> uris = new ArrayList<>();
		for (File f : files) {
			uris.add(FileProvider.getUriForFile(a, a.getPackageName() + ".fileprovider", f));
		}
		final Intent send = new Intent(Intent.ACTION_SEND_MULTIPLE);
		send.setType("text/csv");
		send.putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris);
		send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
		a.runOnUiThread(new Runnable() { public void run() { a.startActivity(Intent.createChooser(send, "Share Terrella metrics")); } });
	}

	/** Deletes old CSVs (keeps the files of currently running processes open). */
	@UsedByGodot
	public void clearMetrics() {
		File[] files = metrics().dir().listFiles(CSV);
		if (files == null) {
			return;
		}
		long cutoff = System.currentTimeMillis() - 15000;
		for (File f : files) {
			if (f.lastModified() < cutoff) {
				f.delete();
			}
		}
	}
}
