package com.godot.game;

import android.app.Activity;
import android.graphics.PixelFormat;
import android.os.Handler;
import android.os.Looper;
import android.os.Parcel;
import android.os.SystemClock;
import android.service.wallpaper.WallpaperService;
import android.util.Log;
import android.view.MotionEvent;
import android.view.Surface;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.widget.FrameLayout;

import org.godotengine.godot.Godot;
import org.godotengine.godot.GodotHost;
import org.godotengine.godot.GodotRenderView;
import org.godotengine.godot.plugin.GodotPlugin;
import org.godotengine.godot.utils.CommandLineFileParser;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Set;

/**
 * Hosts the same Godot project as the app inside a live wallpaper, in its own process (":wallpaper"),
 * because Godot is a per-process singleton.
 *
 * Godot builds its own (never attached) SurfaceView. We redirect that view's Surface to the wallpaper
 * surface with Surface.readFromParcel (public API) and forward the SurfaceHolder callbacks to it. This
 * works for both the Vulkan (Mobile) and OpenGL (Compatibility) render views, since both read
 * view.getHolder().getSurface().
 *
 * Several Engine instances can exist at once (home screen + picker preview). Only one owns the Godot
 * surface at a time: whichever became visible last.
 */
public class TerrellaWallpaperService extends WallpaperService {
	private static final String TAG = "TerrellaWallpaper";

	private final Handler main = new Handler(Looper.getMainLooper());
	private Godot godot;
	private SurfaceView renderSurface;
	private TerrellaEngine owner;
	private boolean running = false;
	private SpikeMetrics metrics;

	private final GodotHost host = new GodotHost() {
		@Override
		public Activity getActivity() {
			return null;
		}

		@Override
		public Godot getGodot() {
			return godot;
		}

		@Override
		public List<String> getCommandLine() {
			return commandLine;
		}

		@Override
		public void runOnHostThread(Runnable action) {
			if (Looper.myLooper() == Looper.getMainLooper()) {
				action.run();
			} else {
				main.post(action);
			}
		}

		@Override
		public void onGodotForceQuit(Godot instance) {
			Log.w(TAG, "Godot requested force quit; stopping wallpaper process");
			android.os.Process.killProcess(android.os.Process.myPid());
		}
	};

	private final List<String> commandLine = new ArrayList<>();

	@Override
	public void onCreate() {
		super.onCreate();
		SpikePlugin.hostMode = "wallpaper";
		metrics = SpikeMetrics.get(this, "wallpaper");
		metrics.event("service_create", SystemClock.uptimeMillis() - android.os.Process.getStartUptimeMillis());
	}

	@Override
	public Engine onCreateEngine() {
		return new TerrellaEngine();
	}

	private boolean ensureGodot() {
		if (godot != null && renderSurface != null) {
			return true;
		}
		long t0 = SystemClock.uptimeMillis();
		try {
			commandLine.clear();
			try {
				commandLine.addAll(CommandLineFileParser.INSTANCE.parseCommandLine(getAssets().open("_cl_")));
			} catch (Exception ignored) {
			}
			godot = Godot.getInstance(getApplicationContext());
			Set<GodotPlugin> plugins = host.getHostPlugins(godot);
			if (!godot.initEngine(host, commandLine, plugins == null ? Collections.emptySet() : plugins)) {
				Log.e(TAG, "initEngine failed");
				metrics.event("error_init_engine", 0);
				return false;
			}
			FrameLayout container = godot.onInitRenderView(host, new FrameLayout(this));
			GodotRenderView rv = godot.getRenderView();
			if (container == null || rv == null) {
				Log.e(TAG, "onInitRenderView failed");
				metrics.event("error_render_view", 0);
				return false;
			}
			renderSurface = rv.getView();
			metrics.event("engine_init", SystemClock.uptimeMillis() - t0);
			return true;
		} catch (Throwable t) {
			Log.e(TAG, "Unable to start Godot in wallpaper", t);
			metrics.event("error_" + t.getClass().getSimpleName(), 0);
			return false;
		}
	}

	private static void redirectSurface(SurfaceView view, Surface target) {
		Parcel p = Parcel.obtain();
		try {
			target.writeToParcel(p, 0);
			p.setDataPosition(0);
			view.getHolder().getSurface().readFromParcel(p);
		} finally {
			p.recycle();
		}
	}

	private void attachTo(TerrellaEngine e) {
		if (!ensureGodot() || e.holder == null || e.width == 0) {
			return;
		}
		if (owner != null && owner != e) {
			detachFrom(owner);
		}
		SurfaceHolder.Callback cb = (SurfaceHolder.Callback) renderSurface;
		if (owner != e) {
			redirectSurface(renderSurface, e.holder.getSurface());
			cb.surfaceCreated(renderSurface.getHolder());
			owner = e;
			metrics.event("attach", 0);
		}
		cb.surfaceChanged(renderSurface.getHolder(), PixelFormat.RGBA_8888, e.width, e.height);
		SpikePlugin.preview = e.isPreview();
		resume();
	}

	private void detachFrom(TerrellaEngine e) {
		if (owner != e || renderSurface == null) {
			return;
		}
		pause();
		((SurfaceHolder.Callback) renderSurface).surfaceDestroyed(renderSurface.getHolder());
		owner = null;
		metrics.event("detach", 0);
	}

	private void resume() {
		if (!running) {
			godot.onStart(host);
			godot.onResume(host);
			running = true;
			SpikePlugin.visible = true;
			metrics.setVisible(true);
		}
	}

	private void pause() {
		if (running) {
			godot.onPause(host);
			godot.onStop(host);
			running = false;
			SpikePlugin.visible = false;
			metrics.setVisible(false);
		}
	}

	private class TerrellaEngine extends Engine {
		SurfaceHolder holder;
		int width, height;
		boolean engineVisible;

		@Override
		public void onCreate(SurfaceHolder surfaceHolder) {
			super.onCreate(surfaceHolder);
			setTouchEventsEnabled(true);
			setOffsetNotificationsEnabled(true);
			metrics.event(isPreview() ? "engine_create_preview" : "engine_create", 0);
		}

		@Override
		public void onSurfaceCreated(SurfaceHolder h) {
			super.onSurfaceCreated(h);
			holder = h;
		}

		@Override
		public void onSurfaceChanged(SurfaceHolder h, int format, int w, int hgt) {
			super.onSurfaceChanged(h, format, w, hgt);
			holder = h;
			width = w;
			height = hgt;
			if (owner == this || engineVisible) {
				attachTo(this);
			}
		}

		@Override
		public void onVisibilityChanged(boolean v) {
			engineVisible = v;
			if (v) {
				attachTo(this);
			} else if (owner == this) {
				pause();
			}
		}

		@Override
		public void onSurfaceDestroyed(SurfaceHolder h) {
			detachFrom(this);
			holder = null;
			super.onSurfaceDestroyed(h);
		}

		@Override
		public void onDestroy() {
			detachFrom(this);
			super.onDestroy();
		}

		@Override
		public void onTouchEvent(MotionEvent event) {
			if (owner == this && running && renderSurface != null) {
				renderSurface.onTouchEvent(event);
			}
		}

		@Override
		public void onOffsetsChanged(float xOffset, float yOffset, float xStep, float yStep, int xPixels, int yPixels) {
			SpikePlugin.xOffset = xOffset;
		}
	}
}
