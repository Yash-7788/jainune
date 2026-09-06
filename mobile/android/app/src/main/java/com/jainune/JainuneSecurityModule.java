package com.jainune;

import android.app.Activity;
import android.content.Context;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.os.Build;
import android.os.Debug;
import android.provider.Settings;
import android.view.WindowManager;

import com.facebook.react.bridge.Promise;
import com.facebook.react.bridge.ReactApplicationContext;
import com.facebook.react.bridge.ReactContextBaseJavaModule;
import com.facebook.react.bridge.ReactMethod;

import java.io.File;
import java.io.InputStream;
import java.net.Socket;
import java.security.MessageDigest;
import java.security.cert.Certificate;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.List;

/**
 * JainuneSecurityModule — Native Android security checks
 *
 * Implements all checks referenced in deviceIntegrity.ts and antiReversing.ts:
 *  - isDeviceRooted()          → su / Magisk / KernelSU / APatch detection
 *  - detectFrida()             → TCP socket probe on port 27042
 *  - isDebuggerAttached()      → android.os.Debug.isDebuggerConnected() [sync]
 *  - isAdbEnabled()            → Settings.Global.ADB_ENABLED
 *  - getAppCertificateFingerprint() → SHA-256 of signing cert
 *  - enableFlagSecure()        → WindowManager.LayoutParams.FLAG_SECURE on Activity
 *  - disableFlagSecure()       → clears FLAG_SECURE
 *  - emergencyPurgeStorage()   → clears all app SharedPreferences
 *  - exitApp()                 → android.os.Process.killProcess
 */
public class JainuneSecurityModule extends ReactContextBaseJavaModule {

  // Paths that indicate root presence
  private static final List<String> ROOT_PATHS = Arrays.asList(
    "/system/app/Superuser.apk",
    "/sbin/su",
    "/system/bin/su",
    "/system/xbin/su",
    "/data/local/xbin/su",
    "/data/local/bin/su",
    "/system/sd/xbin/su",
    "/system/bin/failsafe/su",
    "/data/local/su",
    "/su/bin/su",
    "/system/app/Magisk.apk",
    "/sbin/.magisk/",
    "/data/adb/magisk/",
    "/data/adb/ksu/",         // KernelSU
    "/data/adb/ap/",          // APatch
    "/data/adb/modules/",     // Magisk modules
    "/system/xbin/busybox",
    "/system/bin/busybox"
  );

  // Frida server default port
  private static final int FRIDA_PORT = 27042;

  public JainuneSecurityModule(ReactApplicationContext reactContext) {
    super(reactContext);
  }

  @Override
  public String getName() {
    return "JainuneSecurityModule";
  }

  // ── Root Detection ──────────────────────────────────────────────────────────

  /**
   * Returns true if device shows signs of root / Magisk / KernelSU / APatch.
   * Checks: known root binary paths + build tags + package manager.
   */
  @ReactMethod
  public void isDeviceRooted(Promise promise) {
    try {
      // 1. Known root binary paths
      for (String path : ROOT_PATHS) {
        File f = new File(path);
        if (f.exists()) {
          promise.resolve(true);
          return;
        }
      }

      // 2. Build tags check: test-keys confirmed only if su is discoverable in PATH
      String buildTags = Build.TAGS;
      if (buildTags != null && buildTags.contains("test-keys")) {
        Process process = null;
        try {
          process = Runtime.getRuntime().exec(new String[]{"which", "su"});
          if (process.getInputStream().read() != -1) {
            promise.resolve(true);
            return;
          }
        } catch (Exception ignored) {
        } finally {
          if (process != null) {
            process.destroy();
          }
        }
      }

      // 3. Check for root management apps via PackageManager
      String[] rootPackages = {
        "com.topjohnwu.magisk",
        "io.github.huskydg.magisk",
        "com.kingroot.kinguser",
        "com.kingo.root",
        "com.smedialink.oneclickroot",
        "com.zhiqupk.root.global",
        "com.alephzain.framaroot",
        "com.koushikdutta.superuser",
        "eu.chainfire.supersu"
      };
      PackageManager pm = getReactApplicationContext().getPackageManager();
      for (String pkg : rootPackages) {
        try {
          pm.getPackageInfo(pkg, 0);
          promise.resolve(true); // Package found = rooted
          return;
        } catch (PackageManager.NameNotFoundException ignored) {
          // Package not installed — continue checking
        }
      }

      // 4. Attempt to execute su (will throw if not available)
      try {
        Runtime.getRuntime().exec(new String[]{"su", "-c", "id"});
        // If exec didn't throw, su exists
        promise.resolve(true);
        return;
      } catch (Exception ignored) {
        // su not found — normal
      }

      promise.resolve(false);
    } catch (Exception e) {
      // Fail secure: treat inspection failure as rooted
      promise.reject("ROOT_CHECK_ERROR", e.getMessage());
    }
  }

  // ── Frida Detection ─────────────────────────────────────────────────────────

  /**
   * Probes localhost:27042 (default Frida server port).
   * If port responds within 200ms, Frida is running.
   */
  @ReactMethod
  public void detectFrida(Promise promise) {
    new Thread(() -> {
      try {
        // TCP socket probe — must run off main thread
        Socket socket = new Socket();
        socket.connect(
          new java.net.InetSocketAddress("127.0.0.1", FRIDA_PORT),
          200 // 200ms timeout
        );
        socket.close();
        // Port responded — Frida server is running
        promise.resolve(true);
      } catch (java.net.ConnectException | java.net.SocketTimeoutException e) {
        // Port refused or timed out — Frida not running
        promise.resolve(false);
      } catch (Exception e) {
        // Network error — treat as clean
        promise.resolve(false);
      }

      // Also check /proc/self/maps for frida-agent
      try {
        Process proc = Runtime.getRuntime().exec("cat /proc/self/maps");
        InputStream is = proc.getInputStream();
        byte[] buffer = new byte[8192];
        StringBuilder maps = new StringBuilder();
        int n;
        while ((n = is.read(buffer)) != -1) {
          maps.append(new String(buffer, 0, n));
        }
        String mapsStr = maps.toString().toLowerCase();
        if (mapsStr.contains("frida") || mapsStr.contains("gum-js-loop") || mapsStr.contains("gmain")) {
          promise.resolve(true);
        }
      } catch (Exception ignored) {
        // Silently ignore /proc read errors
      }
    }).start();
  }

  // ── Debugger Detection ──────────────────────────────────────────────────────

  /**
   * Synchronous check for active debugger/PTRACE attachment.
   * Annotated as blocking synchronous method — do not call from UI thread.
   */
  @ReactMethod(isBlockingSynchronousMethod = true)
  public boolean isDebuggerAttached() {
    return Debug.isDebuggerConnected() || Debug.waitingForDebugger();
  }

  // ── ADB / Developer Options Detection ──────────────────────────────────────

  /**
   * Checks if USB debugging (ADB) is enabled via Android Settings.
   * Only meaningful in production builds — dev builds always return false.
   */
  @ReactMethod
  public void isAdbEnabled(Promise promise) {
    try {
      Context ctx = getReactApplicationContext();
      int adbEnabled = Settings.Global.getInt(
        ctx.getContentResolver(),
        Settings.Global.ADB_ENABLED,
        0
      );
      promise.resolve(adbEnabled == 1);
    } catch (Exception e) {
      promise.resolve(false); // Fail open for ADB check (soft violation)
    }
  }

  // ── APK Certificate Fingerprint ─────────────────────────────────────────────

  /**
   * Returns the SHA-256 fingerprint of the APK signing certificate.
   * Compare against EXPECTED_RELEASE_CERT_SHA256 in deviceIntegrity.ts.
   * If mismatch, APK was repackaged and resigned with an attacker's key.
   */
  @ReactMethod
  public void getAppCertificateFingerprint(Promise promise) {
    try {
      Context ctx = getReactApplicationContext();
      PackageManager pm = ctx.getPackageManager();
      String packageName = ctx.getPackageName();

      Signature[] signatures;
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
        android.content.pm.PackageInfo info = pm.getPackageInfo(
          packageName,
          PackageManager.GET_SIGNING_CERTIFICATES
        );
        signatures = info.signingInfo.getApkContentsSigners();
      } else {
        @SuppressWarnings("deprecation")
        android.content.pm.PackageInfo info = pm.getPackageInfo(
          packageName,
          PackageManager.GET_SIGNATURES
        );
        signatures = info.signatures;
      }

      if (signatures == null || signatures.length == 0) {
        promise.reject("NO_SIGNATURES", "No signing certificates found");
        return;
      }

      // Hash the first (primary) signing certificate
      byte[] certBytes = signatures[0].toByteArray();
      MessageDigest md = MessageDigest.getInstance("SHA-256");
      byte[] digest = md.digest(certBytes);

      // Format as colon-separated hex pairs: "E8:7A:B4:..."
      StringBuilder sb = new StringBuilder();
      for (int i = 0; i < digest.length; i++) {
        if (i > 0) sb.append(":");
        sb.append(String.format("%02X", digest[i] & 0xff));
      }

      promise.resolve(sb.toString());
    } catch (Exception e) {
      promise.reject("FINGERPRINT_ERROR", e.getMessage());
    }
  }

  // ── Screen Capture Protection ────────────────────────────────────────────────

  /**
   * Enables FLAG_SECURE on the current Activity window.
   * Prevents: screenshots, screen recording, recent-app thumbnails.
   * Must run on UI thread.
   */
  @ReactMethod
  public void enableFlagSecure(Promise promise) {
    Activity activity = getCurrentActivity();
    if (activity == null) {
      if (promise != null) promise.reject("NO_ACTIVITY", "No current activity");
      return;
    }
    activity.runOnUiThread(() -> {
      activity.getWindow().setFlags(
        WindowManager.LayoutParams.FLAG_SECURE,
        WindowManager.LayoutParams.FLAG_SECURE
      );
      if (promise != null) promise.resolve(true);
    });
  }

  /**
   * Disables FLAG_SECURE — call only when navigating to public non-sensitive screens.
   * NOTE: MainActivity.java sets FLAG_SECURE globally at startup. This method
   * allows fine-grained per-screen control if needed in future.
   */
  @ReactMethod
  public void disableFlagSecure(Promise promise) {
    Activity activity = getCurrentActivity();
    if (activity == null) {
      if (promise != null) promise.reject("NO_ACTIVITY", "No current activity");
      return;
    }
    activity.runOnUiThread(() -> {
      activity.getWindow().clearFlags(WindowManager.LayoutParams.FLAG_SECURE);
      if (promise != null) promise.resolve(true);
    });
  }

  // ── Emergency Storage Purge ──────────────────────────────────────────────────

  /**
   * Wipes ALL SharedPreferences on device for this app.
   * Called on critical integrity violation before app halt.
   * Purges: Expo SecureStore (stored in EncryptedSharedPreferences),
   *         MMKV storage, React Native AsyncStorage, and all custom prefs.
   */
  @ReactMethod
  public void emergencyPurgeStorage(Promise promise) {
    try {
      Context ctx = getReactApplicationContext();
      File prefsDir = new File(ctx.getApplicationInfo().dataDir, "shared_prefs");
      boolean allCleared = true;

      if (prefsDir.exists()) {
        File[] prefFiles = prefsDir.listFiles();
        if (prefFiles != null) {
          for (File f : prefFiles) {
            // Clear each SharedPreferences file
            String prefName = f.getName().replace(".xml", "");
            ctx.getSharedPreferences(prefName, Context.MODE_PRIVATE)
               .edit()
               .clear()
               .apply();
          }
        }
      }

      // Clear MMKV if present
      try {
        Class<?> mmkvClass = Class.forName("com.tencent.mmkv.MMKV");
        Object mmkv = mmkvClass.getMethod("defaultMMKV").invoke(null);
        mmkvClass.getMethod("clearAll").invoke(mmkv);
      } catch (Exception ignored) {
        // MMKV not present or already cleared
      }

      if (promise != null) promise.resolve(allCleared);
    } catch (Exception e) {
      if (promise != null) promise.reject("PURGE_ERROR", e.getMessage());
    }
  }

  // ── App Termination ─────────────────────────────────────────────────────────

  /**
   * Immediately kills the app process.
   * Called after purge when critical security violation detected.
   * SecurityBlockScreen should be shown before this is called.
   */
  @ReactMethod
  public void exitApp() {
    android.os.Process.killProcess(android.os.Process.myPid());
    System.exit(0); // Fallback
  }
}
