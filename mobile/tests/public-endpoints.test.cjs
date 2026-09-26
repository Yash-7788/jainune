const test = require("node:test");
const assert = require("node:assert/strict");
const { validatePublicEndpoints } = require("../scripts/validate-public-endpoints");

test("release endpoints require HTTPS API and WSS chat without Render fallback", () => {
  assert.doesNotThrow(() => validatePublicEndpoints(
    "https://jainune-api.example.workers.dev/v1",
    "wss://jainune-api.example.workers.dev/v1/ws/chat",
  ));
  assert.doesNotThrow(() => validatePublicEndpoints("https://jainune-api.example.workers.dev/v1"));
  assert.throws(() => validatePublicEndpoints(undefined), /EXPO_PUBLIC_API_URL/);
  assert.throws(() => validatePublicEndpoints("http://jainune-api.example.workers.dev/v1"), /HTTPS/);
  assert.throws(() => validatePublicEndpoints("https://jainune-backend-api.onrender.com/v1"), /Render origin/);
  assert.throws(() => validatePublicEndpoints(
    "https://jainune-api.example.workers.dev/v1",
    "wss://jainune-backend-api.onrender.com/v1/ws/chat",
  ), /Render origin/);
});
