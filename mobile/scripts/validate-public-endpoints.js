const forbiddenOrigin = (host) => host === "onrender.com" || host.endsWith(".onrender.com");

function validatePublicEndpoints(apiRaw, wsRaw) {
  if (!apiRaw) throw new Error("Set EXPO_PUBLIC_API_URL for release builds");

  let api;
  try {
    api = new URL(apiRaw);
  } catch {
    throw new Error("EXPO_PUBLIC_API_URL must be an absolute HTTPS URL");
  }
  if (api.protocol !== "https:" || api.pathname.replace(/\/$/, "") !== "/v1" ||
      api.username || api.password || api.search || api.hash || forbiddenOrigin(api.hostname)) {
    throw new Error("EXPO_PUBLIC_API_URL must be a clean HTTPS /v1 endpoint outside the Render origin");
  }

  if (wsRaw) {
    let ws;
    try {
      ws = new URL(wsRaw);
    } catch {
      throw new Error("EXPO_PUBLIC_WS_URL must be an absolute WSS URL");
    }
    if (ws.protocol !== "wss:" || ws.pathname.replace(/\/$/, "") !== "/v1/ws/chat" ||
        ws.username || ws.password || ws.search || ws.hash || forbiddenOrigin(ws.hostname)) {
      throw new Error("EXPO_PUBLIC_WS_URL must be a clean WSS chat endpoint outside the Render origin");
    }
  }
}

if (require.main === module &&
    (["preview", "production"].includes(process.env.EAS_BUILD_PROFILE) || process.argv.includes("--web"))) {
  validatePublicEndpoints(process.env.EXPO_PUBLIC_API_URL, process.env.EXPO_PUBLIC_WS_URL);
}

module.exports = { validatePublicEndpoints };
