const { withDangerousMod, withAndroidManifest } = require("@expo/config-plugins");
const fs = require("fs");
const path = require("path");

function withAndroidAppConfig(config) {
  return withAndroidManifest(config, (config) => {
    const androidManifest = config.modResults.manifest;
    const mainApplication = androidManifest.application?.[0];
    if (mainApplication) {
      mainApplication.$["android:largeHeap"] = "true";
      mainApplication.$["android:networkSecurityConfig"] = "@xml/network_security_config";
    }

    // Strip debug SYSTEM_ALERT_WINDOW from release manifest
    if (androidManifest["uses-permission"]) {
      androidManifest["uses-permission"] = androidManifest["uses-permission"].filter(
        (perm) => perm.$["android:name"] !== "android.permission.SYSTEM_ALERT_WINDOW"
      );
    }

    return config;
  });
}

function withAndroidNativeSecurity(config) {
  return withDangerousMod(config, [
    "android",
    async (config) => {
      const androidRoot = config.modRequest.platformProjectRoot;
      const appPackageDir = path.join(
        androidRoot,
        "app",
        "src",
        "main",
        "java",
        "com",
        "jainune",
        "app"
      );

      // 1. Ensure MainActivity.kt has FLAG_SECURE
      const mainActivityPath = path.join(appPackageDir, "MainActivity.kt");
      if (fs.existsSync(mainActivityPath)) {
        let content = fs.readFileSync(mainActivityPath, "utf8");
        if (!content.includes("FLAG_SECURE")) {
          content = content.replace(
            "super.onCreate(null)",
            `super.onCreate(null)\n    window.setFlags(\n      android.view.WindowManager.LayoutParams.FLAG_SECURE,\n      android.view.WindowManager.LayoutParams.FLAG_SECURE\n    )`
          );
          fs.writeFileSync(mainActivityPath, content);
        }
      }

      // 2. Ensure MainApplication.kt adds JainuneSecurityPackage()
      const mainApplicationPath = path.join(appPackageDir, "MainApplication.kt");
      if (fs.existsSync(mainApplicationPath)) {
        let content = fs.readFileSync(mainApplicationPath, "utf8");
        if (!content.includes("JainuneSecurityPackage()")) {
          content = content.replace(
            "val packages = PackageList(this).packages.toMutableList()",
            "val packages = PackageList(this).packages.toMutableList()\n            packages.add(JainuneSecurityPackage())"
          );
          fs.writeFileSync(mainApplicationPath, content);
        }
      }

      return config;
    },
  ]);
}

module.exports = function withAndroidSecurity(config) {
  return withAndroidNativeSecurity(withAndroidAppConfig(config));
};
