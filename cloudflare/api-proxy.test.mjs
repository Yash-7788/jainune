import test from "node:test";
import assert from "node:assert/strict";
import worker from "./api-proxy.mjs";

const env = {
  API_ORIGIN: "https://jainune-backend-api.onrender.com",
  EDGE_ORIGIN_SECRET: "server-only-test-secret",
};

test("forwards app and checkout requests with trusted origin header", async () => {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async (request) => {
    assert.equal(request.url, "https://jainune-backend-api.onrender.com/v1/payments/razorpay/verify-web?x=1");
    assert.equal(request.method, "POST");
    assert.equal(request.headers.get("authorization"), "Bearer user-token");
    assert.equal(request.headers.get("origin"), "https://jainune.vercel.app");
    assert.equal(request.headers.get("x-edge-secret"), env.EDGE_ORIGIN_SECRET);
    assert.equal(request.headers.get("cf-connecting-ip"), "203.0.113.4");
    assert.equal(request.headers.get("x-forwarded-for"), null);
    assert.equal(await request.text(), '{"a":1}');
    return new Response('{"success":true}', { headers: { "Cache-Control": "no-store" } });
  };
  try {
    const request = new Request("https://jainune-api-proxy.account.workers.dev/v1/payments/razorpay/verify-web?x=1", {
      method: "POST",
      headers: {
        authorization: "Bearer user-token", origin: "https://jainune.vercel.app",
        "cf-connecting-ip": "203.0.113.4", "x-edge-secret": "attacker",
        "x-forwarded-for": "198.51.100.5",
      },
      body: '{"a":1}',
    });
    const response = await worker.fetch(request, env);
    assert.equal(response.status, 200);
  } finally {
    globalThis.fetch = previousFetch;
  }
});

test("forwards browser preflight and WebSocket upgrade without false rejection", async () => {
  const previousFetch = globalThis.fetch;
  const seen = [];
  globalThis.fetch = async (request) => {
    seen.push({ method: request.method, upgrade: request.headers.get("upgrade") });
    return new Response(null, { status: 204 });
  };
  try {
    const base = "https://jainune-api-proxy.account.workers.dev";
    await worker.fetch(new Request(base + "/v1/auth/google", { method: "OPTIONS", headers: {
      origin: "https://jainune.vercel.app", "access-control-request-method": "POST",
    } }), env);
    await worker.fetch(new Request(base + "/v1/ws/chat/00000000-0000-4000-8000-000000000001?ticket=abc", {
      headers: { upgrade: "websocket" },
    }), env);
    assert.deepEqual(seen, [{ method: "OPTIONS", upgrade: null }, { method: "GET", upgrade: "websocket" }]);
  } finally {
    globalThis.fetch = previousFetch;
  }
});

test("fails closed when secret or origin config is missing", async () => {
  const request = new Request("https://jainune-api-proxy.account.workers.dev/v1/feed");
  assert.equal((await worker.fetch(request, { API_ORIGIN: env.API_ORIGIN })).status, 503);
  assert.equal((await worker.fetch(request, { EDGE_ORIGIN_SECRET: env.EDGE_ORIGIN_SECRET })).status, 503);
});

test("rejects declared oversized payment webhooks before Render", async () => {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error("must not reach Render"); };
  try {
    const request = new Request(
      "https://jainune-api-proxy.account.workers.dev/v1/subscriptions/store-notification",
      { method: "POST", headers: { "Content-Length": "1048577" }, body: "x" },
    );
    assert.equal((await worker.fetch(request, env)).status, 413);
  } finally {
    globalThis.fetch = previousFetch;
  }
});
