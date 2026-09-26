// Optional photo-only Worker. Workers Caching is configured in wrangler.toml
// so repeat public GETs can be served on workers.dev without origin subrequests.
const AVATAR_PATH = /^\/storage\/v1\/object\/public\/avatars\/[0-9a-f-]{36}\/avatar\.webp$/;
const MAX_AVATAR_BYTES = 350 * 1024;

export default {
  async fetch(request, env, context) {
    const incoming = new URL(request.url);
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response(null, { status: 405, headers: { Allow: "GET, HEAD", "Cache-Control": "no-store" } });
    }
    if (!AVATAR_PATH.test(incoming.pathname)) {
      return new Response(null, { status: 404, headers: { "Cache-Control": "no-store" } });
    }
    if ([...incoming.searchParams.keys()].some((key) => key !== "v") ||
        (incoming.searchParams.has("v") && !/^[0-9a-f]{8}$/.test(incoming.searchParams.get("v") || ""))) {
      return new Response(null, { status: 400, headers: { "Cache-Control": "no-store" } });
    }

    const origin = new URL(env.SUPABASE_ORIGIN);
    if (origin.protocol !== "https:" || origin.pathname !== "/" || origin.search || origin.hash) {
      return new Response(null, { status: 500, headers: { "Cache-Control": "no-store" } });
    }

    const upstream = new URL(incoming.pathname + incoming.search, origin);
    const response = await fetch(upstream.toString(), {
      method: request.method,
      headers: { Accept: "image/webp" },
      redirect: "error",
    });
    if (!response.ok) {
      return new Response(null, { status: response.status, headers: { "Cache-Control": "no-store" } });
    }

    const contentType = response.headers.get("content-type") || "";
    const declaredLength = response.headers.get("content-length");
    if (!contentType.startsWith("image/webp") ||
        (declaredLength && Number(declaredLength) > MAX_AVATAR_BYTES)) {
      return new Response(null, { status: 502, headers: { "Cache-Control": "no-store" } });
    }

    if (request.method === "HEAD") {
      return new Response(null, {
        status: 200,
        headers: { "Content-Type": "image/webp", "Cache-Control": "no-store" },
      });
    }

    const reader = response.body?.getReader();
    if (!reader) return new Response(null, { status: 502, headers: { "Cache-Control": "no-store" } });
    const chunks = [];
    let total = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_AVATAR_BYTES) {
        await reader.cancel();
        return new Response(null, { status: 502, headers: { "Cache-Control": "no-store" } });
      }
      chunks.push(value);
    }
    if (total === 0) return new Response(null, { status: 502, headers: { "Cache-Control": "no-store" } });
    const body = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) {
      body.set(chunk, offset);
      offset += chunk.byteLength;
    }

    const proxied = new Response(body, {
      status: 200,
      headers: {
        "Content-Type": "image/webp",
        "Content-Length": String(total),
        "Cache-Control": "public, max-age=300",
        "X-Content-Type-Options": "nosniff",
      },
    });
    return proxied;
  },
};
