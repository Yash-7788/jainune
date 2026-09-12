const { withDangerousMod } = require("@expo/config-plugins");
const fs = require("fs");
const path = require("path");

module.exports = function withIosSecurity(config) {
  return withDangerousMod(config, [
    "ios",
    async (config) => {
      const podfilePath = path.join(config.modRequest.platformProjectRoot, "Podfile");
      if (fs.existsSync(podfilePath)) {
        let contents = fs.readFileSync(podfilePath, "utf8");
        if (!contents.includes("JainuneSecurityModule")) {
          contents += `\n  pod 'JainuneSecurityModule', :path => '../ios/Jainune'\n`;
          fs.writeFileSync(podfilePath, contents);
        }
      }
      return config;
    },
  ]);
};
