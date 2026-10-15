package com.godot.game;

import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.BatteryManager;
import android.os.Build;
import android.os.Debug;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.PowerManager;
import android.os.Process;
import android.os.SystemClock;
import android.util.Log;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * Per-process CSV sampler. One row per second while visible, one per 10 s while hidden.
 * Godot-side numbers (fps, frame time, draw calls) are pushed in by {@link SpikePlugin#reportFrame}.
 * Files: Android/data/<pkg>/files/metrics/<mode>_<timestamp>.csv
 */
public final class SpikeMetrics {
	private static final String TAG = "TerrellaMetrics";
	private static final long VISIBLE_INTERVAL_MS = 1000;
	private static final long HIDDEN_INTERVAL_MS = 10000;

	private static SpikeMetrics instance;

	public static synchronized SpikeMetrics get(Context ctx, String mode) {
		if (instance == null) {
			instance = new SpikeMetrics(ctx.getApplicationContext(), mode);
		}
		return instance;
	}

	public static synchronized SpikeMetrics peek() {
		return instance;
	}

	private final Context ctx;
	private final String mode;
	private final Handler handler;
	private final BatteryManager battery;
	private final PowerManager power;
	private BufferedWriter out;
	private File file;

	// State shared with the sampler thread.
	private volatile boolean visible = false;
	private volatile String renderer = "?";
	private volatile String label = "";
	private volatile String variant = "";
	private volatile double fps, frameMs, frameMsMax, drawCalls, primitives, vramMb, godotStaticMb;
	private volatile int fpsCap;

	private long lastCpuMs = -1, lastSampleMs = -1;
	private long lastPssKb = 0;
	private long lastPssAt = 0;
	private float lastHeadroom = Float.NaN;
	private long lastHeadroomAt = 0;
	private boolean firstFrameLogged = false;
	private volatile String lastSummary = "";

	private SpikeMetrics(Context ctx, String mode) {
		this.ctx = ctx;
		this.mode = mode;
		this.battery = (BatteryManager) ctx.getSystemService(Context.BATTERY_SERVICE);
		this.power = (PowerManager) ctx.getSystemService(Context.POWER_SERVICE);
		HandlerThread t = new HandlerThread("terrella-metrics", Process.THREAD_PRIORITY_BACKGROUND);
		t.start();
		handler = new Handler(t.getLooper());
		handler.post(new Runnable() { public void run() { open(); } });
		handler.post(tickRunnable);
	}

	public String mode() {
		return mode;
	}

	public File dir() {
		File d = new File(ctx.getExternalFilesDir(null), "metrics");
		d.mkdirs();
		return d;
	}

	private void open() {
		try {
			String ts = new SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(new Date());
			file = new File(dir(), mode + "_" + ts + ".csv");
			out = new BufferedWriter(new FileWriter(file, true));
			out.write("wall_ms,uptime_s,mode,device,renderer,visible,fps_cap,label,variant,event,event_ms,"
					+ "fps,frame_ms,frame_ms_max,draw_calls,primitives,vram_mb,godot_static_mb,pss_mb,java_heap_mb,cpu_pct,"
					+ "batt_current_ua,batt_charge_uah,batt_pct,batt_temp_c,batt_mv,plugged,thermal_status,thermal_headroom\n");
			out.flush();
			Log.i(TAG, "Writing metrics to " + file);
		} catch (Exception e) {
			Log.e(TAG, "Cannot open metrics file", e);
		}
	}

	public void setVisible(boolean v) {
		if (visible != v) {
			visible = v;
			event(v ? "visible" : "hidden", 0);
			handler.removeCallbacks(tickRunnable);
			handler.post(tickRunnable);
		}
	}

	public void setRenderer(String r) {
		renderer = r;
	}

	public void setLabel(String l) {
		label = l == null ? "" : l.replace(',', ' ');
		event("label", 0);
	}

	public void setVariant(String v) {
		variant = v == null ? "" : v.replace(',', ' ');
	}

	public void setFpsCap(int cap) {
		fpsCap = cap;
	}

	public void reportFrame(double fps, double frameMs, double frameMsMax, double drawCalls, double primitives, double vramMb, double godotStaticMb) {
		this.fps = fps;
		this.frameMs = frameMs;
		this.frameMsMax = frameMsMax;
		this.drawCalls = drawCalls;
		this.primitives = primitives;
		this.vramMb = vramMb;
		this.godotStaticMb = godotStaticMb;
	}

	/** Records the first rendered frame once per process: time since process start. */
	public synchronized void firstFrame() {
		if (firstFrameLogged) {
			return;
		}
		firstFrameLogged = true;
		long sinceStart = SystemClock.uptimeMillis() - Process.getStartUptimeMillis();
		event("first_frame", sinceStart);
	}

	public void event(final String name, final long valueMs) {
		handler.post(new Runnable() { public void run() { write(name, valueMs); } });
	}

	public String summary() {
		return lastSummary;
	}

	private final Runnable tickRunnable = new Runnable() { public void run() { tick(); } };

	private void tick() {
		write("", 0);
		handler.removeCallbacks(tickRunnable);
		handler.postDelayed(tickRunnable, visible ? VISIBLE_INTERVAL_MS : HIDDEN_INTERVAL_MS);
	}

	private void write(String event, long eventMs) {
		if (out == null) {
			return;
		}
		try {
			long now = SystemClock.uptimeMillis();
			long cpuMs = Process.getElapsedCpuTime();
			double cpuPct = 0;
			if (lastCpuMs >= 0 && now > lastSampleMs) {
				cpuPct = 100.0 * (cpuMs - lastCpuMs) / (now - lastSampleMs);
			}
			if (event.isEmpty()) {
				lastCpuMs = cpuMs;
				lastSampleMs = now;
			}
			if (now - lastPssAt > 10000 || lastPssAt == 0) {
				lastPssKb = Debug.getPss();
				lastPssAt = now;
			}
			if (Build.VERSION.SDK_INT >= 30 && now - lastHeadroomAt > 5000) {
				lastHeadroom = power.getThermalHeadroom(10);
				lastHeadroomAt = now;
			}
			Runtime rt = Runtime.getRuntime();
			double javaHeapMb = (rt.totalMemory() - rt.freeMemory()) / 1048576.0;
			int currentUa = battery.getIntProperty(BatteryManager.BATTERY_PROPERTY_CURRENT_NOW);
			int chargeUah = battery.getIntProperty(BatteryManager.BATTERY_PROPERTY_CHARGE_COUNTER);
			int pct = battery.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY);
			Intent b = ctx.registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
			double tempC = b == null ? 0 : b.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0) / 10.0;
			int mv = b == null ? 0 : b.getIntExtra(BatteryManager.EXTRA_VOLTAGE, 0);
			int plugged = b == null ? 0 : b.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0);
			int thermal = Build.VERSION.SDK_INT >= 29 ? power.getCurrentThermalStatus() : -1;
			boolean live = visible;
			String row = String.format(Locale.US,
					"%d,%.1f,%s,%s,%s,%d,%d,%s,%s,%s,%d,%.1f,%.2f,%.2f,%.0f,%.0f,%.1f,%.1f,%.1f,%.1f,%.1f,%d,%d,%d,%.1f,%d,%d,%d,%.3f\n",
					System.currentTimeMillis(), now / 1000.0, mode, Build.MODEL.replace(',', ' '), renderer, live ? 1 : 0, fpsCap, label, variant,
					event, eventMs,
					live ? fps : 0, live ? frameMs : 0, live ? frameMsMax : 0, live ? drawCalls : 0, live ? primitives : 0, vramMb, godotStaticMb,
					lastPssKb / 1024.0, javaHeapMb, cpuPct,
					currentUa, chargeUah, pct, tempC, mv, plugged, thermal, lastHeadroom);
			out.write(row);
			out.flush();
			lastSummary = String.format(Locale.US,
					"%s | %s | %.0f fps %.1f ms | %.0f dc | PSS %.0f MB | CPU %.0f%% | %.0f mA | %.1f C | thermal %d%s",
					mode, renderer, fps, frameMs, drawCalls, lastPssKb / 1024.0, cpuPct, currentUa / 1000.0, tempC, thermal,
					plugged != 0 ? " | PLUGGED IN (battery numbers invalid)" : "");
		} catch (Exception e) {
			Log.e(TAG, "Metrics write failed", e);
		}
	}
}
