/**
 * Jainune Android MainActivity — Phase 8 Security Hardening
 *
 * Applies:
 * 1. FLAG_SECURE — prevents screenshots, screen recording, recent-apps thumbnail
 *    caching of ANY screen (chat, profile, payment). JainuneSecurityModule
 *    can toggle per-screen via RN bridge calls.
 * 2. Network Security Config reference (network_security_config.xml)
 *    enforces SPKI certificate pinning at OS level — defeats Frida SSL unpin.
 *
 * NOTE: Keep android:networkSecurityConfig in AndroidManifest.xml pointing to
 * @xml/network_security_config (this is the OS-level pinning enforcement).
 */

package com.jainune;

import android.os.Bundle;
import android.view.WindowManager;

import com.facebook.react.ReactActivity;
import com.facebook.react.ReactActivityDelegate;
import com.facebook.react.defaults.DefaultNewArchitectureEntryPoint;
import com.facebook.react.defaults.DefaultReactActivityDelegate;

public class MainActivity extends ReactActivity {

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);

    // SECURITY: Block screenshots, screen recordings, and recent-app previews
    // on ALL screens globally. JainuneSecurityModule can narrow this per-screen.
    // Ref: SECURITY.md §9.2
    getWindow().setFlags(
      WindowManager.LayoutParams.FLAG_SECURE,
      WindowManager.LayoutParams.FLAG_SECURE
    );
  }

  @Override
  protected String getMainComponentName() {
    return "jainune";
  }

  @Override
  protected ReactActivityDelegate createReactActivityDelegate() {
    return new DefaultReactActivityDelegate(
      this,
      getMainComponentName(),
      DefaultNewArchitectureEntryPoint.getFabricEnabled()
    );
  }
}
