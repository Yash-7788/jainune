# Optional Cloudflare Workers on the Free plan

No purchased domain is required for these Workers. They use separate
`*.workers.dev` addresses. A Worker URL is public and can be extracted from
the app just like any other network destination. The security value comes from
server-side verification, not hiding a URL. Neither Worker is live merely
because its source exists here.

## Photo Worker

`photo-proxy.mjs` serves only public WebP avatars. `wrangler.toml` enables
Workers Caching for repeat GETs on `workers.dev`; it does not cache private
API responses. It uses the public Supabase Storage URL and needs no service
role key. A deleted avatar may remain cached for five minutes, so do not use
this route for private media or instant revocation.

1. Deploy from this directory with `wrangler deploy --config wrangler.toml`.
2. Test a real avatar GET twice and require a Cloudflare cache MISS then HIT;
   test a new `?v=` after replacement, missing/deleted objects, HEAD, and
   rejected paths. Local unit tests only verify headers and routing, not a
   live edge cache.
3. Compare Supabase egress and Cloudflare request usage before claiming any
   savings. Free Workers share a 100,000-request daily ceiling; over-limit
   requests can fail with error 1027.
4. Only after the live canary succeeds, set Render `MEDIA_CDN_URL` to the
   actual photo Worker origin. Existing database rows containing Supabase URLs
   stay unchanged until separately inspected and migrated. Rollback must
   restore those rows as well as clear the setting.

## API Worker and optional Render origin gate

`api-proxy.mjs` forwards HTTP, browser preflight, checkout, provider webhook,
and WebSocket requests to Render. It never caches private API responses.
`wrangler.api.toml` contains only the public origin URL. The Worker requires
the private `EDGE_ORIGIN_SECRET` secret, identical to Render's existing
`CLOUDFLARE_ORIGIN_SECRET`. Use Cloudflare's secret binding; never place this
value in Wrangler variables, the app, or Git.

**Keep Render `REQUIRE_EDGE_ORIGIN=false` until every step below passes.**
Turning it on early would block app calls and payment callbacks sent directly
to Render. It is also a Render-side check, so it cannot absorb a network flood
before that traffic reaches Render. The Worker can reject malformed traffic
earlier, but `workers.dev` is not a custom-domain DNS/WAF proxy.

1. Deploy with `wrangler deploy --config wrangler.api.toml`, then add
   `EDGE_ORIGIN_SECRET` to that Worker as a secret. Confirm that it has the
   same value as Render `CLOUDFLARE_ORIGIN_SECRET`.
2. Through the Worker, test Android and PWA login, refresh, feed, media
   confirmation, chat WebSocket, CORS preflight, checkout, verify-web, and
   Razorpay and store webhook signature flows. A webhook sent directly to
   Render is expected to work only while the gate is off.
3. Update Razorpay and store notification callback URLs to the API Worker
   address. Confirm real provider callbacks are acknowledged. Preserve their
   original signed payloads and headers. `return_origin` for PWA checkout
   remains an explicitly allowed PWA origin, never the Worker address.
4. Set `EXPO_PUBLIC_API_URL` to `<api-worker-origin>/v1` and
   `EXPO_PUBLIC_WS_URL` to `wss://<api-worker-host>/v1/ws/chat` in PWA/EAS
   configuration. Build and test a new Android APK and PWA. Old app builds
   continue using Render directly and would be blocked by the gate.
5. Verify direct Render `/health` remains available, then enable Render
   `REQUIRE_EDGE_ORIGIN=true`. Confirm direct application calls fail with 403,
   while Worker calls, browser preflight, chat, and provider callbacks work.
   Roll back by setting `REQUIRE_EDGE_ORIGIN=false` first.

The Worker account's Free request ceiling is shared by photo and API Workers.
Run a traffic estimate before making the API Worker mandatory for everyone.

References: [Workers routing](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/),
[Workers Caching](https://developers.cloudflare.com/workers/cache/),
[Worker secrets](https://developers.cloudflare.com/workers/configuration/secrets/),
[Free limits](https://developers.cloudflare.com/workers/platform/limits/).

