import test from "node:test";
import assert from "node:assert/strict";
import worker from "./photo-proxy.mjs";

const photoUrl = "https://cdn.jainune.com/storage/v1/object/public/avatars/" +
  "8fa85a26-95eb-4868-90ac-6dc352c5e0f0/avatar.webp?v=1234abcd";

test("marks only successful avatar GETs cacheable for Workers Caching", async () => {
  let fetches = 0;
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    fetches++;
    assert.match(url, /^https:\/\/project\.supabase\.co\/storage\/v1\/object\/public\/avatars\//);
    return new Response(new Uint8Array([82, 73, 70, 70]), {
      headers: { "content-type": "image/webp", "content-length": "4" },
    });
  };
  try {
    const env = { SUPABASE_ORIGIN: "https://project.supabase.co" };
    const first = await worker.fetch(new Request(photoUrl), env);
    assert.equal(first.status, 200);
    assert.equal(fetches, 1);
    assert.equal(first.headers.get("cache-control"), "public, max-age=300");
    const head = await worker.fetch(new Request(photoUrl, { method: "HEAD" }), env);
    assert.equal(head.headers.get("cache-control"), "no-store");
  } finally {
    globalThis.fetch = previousFetch;
  }
});

test("rejects arbitrary paths and query parameters", async () => {
  const env = { SUPABASE_ORIGIN: "https://project.supabase.co" };
  assert.equal((await worker.fetch(new Request("https://cdn.jainune.com/v1/users"), env)).status, 404);
  assert.equal((await worker.fetch(new Request(photoUrl + "&token=secret"), env)).status, 400);
});

test("rejects an oversized origin response without caching it", async () => {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(new Uint8Array(350 * 1024 + 1), {
    headers: { "content-type": "image/webp" },
  });
  try {
    const response = await worker.fetch(
      new Request(photoUrl),
      { SUPABASE_ORIGIN: "https://project.supabase.co" }
    );
    assert.equal(response.status, 502);
    assert.equal(response.headers.get("cache-control"), "no-store");
  } finally {
    globalThis.fetch = previousFetch;
  }
});
