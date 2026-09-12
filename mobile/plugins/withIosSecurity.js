const { withDangerousMod } = require("@expo/config-plugins");
const fs = require("fs");
const path = require("path");

module.exports = function withIosSecurity(config) {
  return withDangerousMod(config, [
    "ios",
    async (config) => {
      const iosRoot = config.modRequest.platformProjectRoot;
      const targetDir = path.join(iosRoot, "Jainune");
      if (!fs.existsSync(targetDir)) {
        fs.mkdirSync(targetDir, { recursive: true });
      }

      // Preserve native security module files across Expo prebuild lifecycle
      const srcDir = path.join(config.modRequest.projectRoot, "plugins", "ios-security");
      if (fs.existsSync(srcDir)) {
        for (const file of fs.readdirSync(srcDir)) {
          fs.copyFileSync(path.join(srcDir, file), path.join(targetDir, file));
        }
      }

      const podfilePath = path.join(iosRoot, "Podfile");
      if (fs.existsSync(podfilePath)) {
        let contents = fs.readFileSync(podfilePath, "utf8");
        if (!contents.includes("JainuneSecurityModule")) {
          contents += `\n  pod 'JainuneSecurityModule', :path => './Jainune'\n`;
          fs.writeFileSync(podfilePath, contents);
        }
      }
      return config;
    },
  ]);
};
