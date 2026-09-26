// Optional, domain-free API entrypoint. The origin gate must remain disabled
// until this Worker, mobile clients, browser preflights, WebSockets, and
// payment callbacks have all passed live checks.
const ALLOWED_METHODS = new Set(["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]);
const PAYMENT_WEBHOOK_PATHS = new Set([
  "/v1/subscriptions/webhook",
  "/v1/payments/razorpay/webhook",
  "/v1/subscriptions/store-notification",
]);
const MAX_PAYMENT_WEBHOOK_BYTES = 1024 * 1024;
const SPOOFABLE_HEADERS = [
  "x-edge-secret", "x-origin-secret", "cf-origin-secret", "cf-connecting-ip",
  "x-real-ip", "x-forwarded-for", "forwarded", "cf-ray",
];

export default {
  async fetch(request, env) {
    if (!ALLOWED_METHODS.has(request.method)) {
      return new Response(null, { status: 405, headers: { Allow: [...ALLOWED_METHODS].join(", ") } });
    }

    const incoming = new URL(request.url);
    if (PAYMENT_WEBHOOK_PATHS.has(incoming.pathname) && request.method === "POST") {
      const declaredLength = request.headers.get("content-length");
      if (declaredLength !== null) {
        const size = Number(declaredLength);
        if (!Number.isSafeInteger(size) || size < 0) return new Response(null, { status: 400 });
        if (size > MAX_PAYMENT_WEBHOOK_BYTES) return new Response(null, { status: 413 });
      }
    }
    let origin;
    try {
      origin = new URL(env.API_ORIGIN || "");
    } catch {
      return new Response(null, { status: 503 });
    }
    if (origin.protocol !== "https:" || origin.pathname !== "/" || origin.search || origin.hash ||
        !env.EDGE_ORIGIN_SECRET) {
      return new Response(null, { status: 503 });
    }

    const clientIp = request.headers.get("cf-connecting-ip");
    const headers = new Headers(request.headers);
    for (const name of SPOOFABLE_HEADERS) headers.delete(name);
    headers.delete("host");
    headers.set("X-Edge-Secret", env.EDGE_ORIGIN_SECRET);
    if (clientIp) headers.set("CF-Connecting-IP", clientIp);

    // Preserve the entire path and query string, including WS tickets and
    // payment return parameters. Do not cache personalized API responses.
    const upstream = new URL(incoming.pathname + incoming.search, origin);
    const response = await fetch(new Request(upstream, {
      method: request.method,
      headers,
      body: request.body,
      duplex: "half",
      redirect: "manual",
    }));
    return response;
  },
};
