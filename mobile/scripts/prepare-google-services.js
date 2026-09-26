const fs = require("node:fs");
const path = require("node:path");

const destination = path.resolve(__dirname, "../android/app/google-services.json");
const supplied = process.env.GOOGLE_SERVICES_JSON;

if (supplied) {
  if (!fs.existsSync(supplied)) {
    throw new Error("GOOGLE_SERVICES_JSON must be an EAS file variable pointing to google-services.json");
  }
  fs.copyFileSync(supplied, destination);
}

if (!fs.existsSync(destination)) {
  if (process.env.EAS_BUILD_PROFILE === "production") {
    throw new Error("Android production push requires GOOGLE_SERVICES_JSON in EAS");
  }
  process.exit(0);
}

const config = JSON.parse(fs.readFileSync(destination, "utf8"));
const clients = Array.isArray(config.client) ? config.client : [];
const matches = clients.some(
  (client) => client?.client_info?.android_client_info?.package_name === "com.jainune.app"
);
if (!matches) {
  throw new Error("google-services.json does not contain the com.jainune.app Android app");
}
