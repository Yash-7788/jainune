const { withDangerousMod, withInfoPlist, withEntitlementsPlist, withPodfile } = require("@expo/config-plugins");
const { addSecurityPod } = require("./securityPod");
const fs = require("fs");
const path = require("path");

function withIosSecurityInfo(config) {
  return withInfoPlist(config, (config) => {
    config.modResults.NSAppTransportSecurity = {
      ...config.modResults.NSAppTransportSecurity,
      NSAllowsArbitraryLoads: false,
      NSExceptionDomains: {
        ...(config.modResults.NSAppTransportSecurity?.NSExceptionDomains || {}),
        localhost: {
          NSExceptionAllowsInsecureHTTPLoads: true,
        },
        "127.0.0.1": {
          NSExceptionAllowsInsecureHTTPLoads: true,
        },
      },
      NSPinnedDomains: {
        ...(config.modResults.NSAppTransportSecurity?.NSPinnedDomains || {}),
        "api.jainune.com": {
          NSIncludesSubdomains: true,
          NSPinnedLeafIdentities: [
            {
              "SPKI-SHA256-BASE64": "k20YWfohKw3kUj5t5K65soVIyzxPCQFvMQkxZpmGsoo=",
            },
            {
              "SPKI-SHA256-BASE64": "WoiWRyIOVNa9ihaBciRSC7XHjliYS9VwUGOIud4PB18=",
            },
          ],
        },
      },
    };
    return config;
  });
}

function withIosSecurityEntitlements(config) {
  return withEntitlementsPlist(config, (config) => {
    const existing = config.modResults["com.apple.developer.associated-domains"] || [];
    const domain = "applinks:jainune.com";
    if (!existing.includes(domain)) {
      config.modResults["com.apple.developer.associated-domains"] = [...existing, domain];
    }
    return config;
  });
}

function withIosSecurityPod(config) {
  return withDangerousMod(config, [
    "ios",
    async (config) => {
      const iosRoot = config.modRequest.platformProjectRoot;
      const targetDir = path.join(iosRoot, "JainuneSecurityModule");
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

      return config;
    },
  ]);
}

module.exports = function withIosSecurity(config) {
  config = withPodfile(config, (config) => {
    config.modResults.contents = addSecurityPod(config.modResults.contents);
    return config;
  });
  return withIosSecurityPod(withIosSecurityEntitlements(withIosSecurityInfo(config)));
};
