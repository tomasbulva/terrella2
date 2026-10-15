package com.godot.game;

import android.content.Context;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.util.Properties;

/** Tiny file-backed settings shared by the app and wallpaper processes (SharedPreferences is not multi-process safe). */
public final class SpikeSettings {
	private SpikeSettings() {}

	private static File file(Context ctx) {
		return new File(ctx.getFilesDir(), "spike_settings.properties");
	}

	public static synchronized Properties load(Context ctx) {
		Properties p = new Properties();
		File f = file(ctx);
		if (f.exists()) {
			try (FileInputStream in = new FileInputStream(f)) {
				p.load(in);
			} catch (Exception ignored) {
			}
		}
		return p;
	}

	public static String get(Context ctx, String key, String def) {
		return load(ctx).getProperty(key, def);
	}

	public static synchronized void set(Context ctx, String key, String value) {
		Properties p = load(ctx);
		p.setProperty(key, value);
		File f = file(ctx);
		File tmp = new File(f.getPath() + ".tmp");
		try (FileOutputStream out = new FileOutputStream(tmp)) {
			p.store(out, "terrella spike");
		} catch (Exception ignored) {
			return;
		}
		tmp.renameTo(f);
	}

	/** Godot command line for the chosen renderer: "vulkan" (Mobile) or "gl" (Compatibility). */
	public static String[] rendererArgs(Context ctx) {
		if ("gl".equals(get(ctx, "renderer", "vulkan"))) {
			return new String[] { "--rendering-driver", "opengl3", "--rendering-method", "gl_compatibility" };
		}
		return new String[] { "--rendering-driver", "vulkan", "--rendering-method", "mobile" };
	}
}
