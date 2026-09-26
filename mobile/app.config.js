const fs = require("node:fs");
const path = require("node:path");
const config = require("./app.json").expo;

const googleServicesFile = process.env.GOOGLE_SERVICES_JSON || "./android/app/google-services.json";

module.exports = {
  ...config,
  android: {
    ...config.android,
    ...(fs.existsSync(path.resolve(__dirname, googleServicesFile))
      ? { googleServicesFile }
      : {}),
  },
};
