/* Background Web Push for installed Jainune web apps. No fetch interception. */
self.addEventListener("push", function (event) {
  var payload = {};
  try { payload = event.data ? event.data.json() : {}; } catch (_) {}
  var data = payload.data || {};
  var path = "/";
  var conversationId = data.match_id || data.chat_id || "";
  if ((data.type === "chat" || data.type === "new_message" || data.type === "new_match" || data.type === "match") &&
      /^[0-9a-f-]{36}$/i.test(conversationId)) {
    path = "/chat/" + encodeURIComponent(conversationId);
  } else if (data.type === "new_like" || data.type === "super_connect") {
    path = "/likes";
  } else if (data.type === "match_expiring" || data.type === "momentum") {
    path = "/chats";
  } else if (data.type === "subscription" || data.type === "billing") {
    path = "/subscriptions";
  }
  event.waitUntil(self.registration.showNotification(payload.title || "Jainune", {
    body: payload.body || "You have a new update.",
    icon: "/icon.png",
    badge: "/icon.png",
    tag: data.match_id || data.chat_id || data.type || "jainune",
    data: { path: path }
  }));
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  var target = new URL((event.notification.data || {}).path || "/", self.location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (clients) {
    for (var i = 0; i < clients.length; i++) {
      if (new URL(clients[i].url).origin === self.location.origin) {
        return clients[i].navigate(target).then(function (client) { return client.focus(); });
      }
    }
    return self.clients.openWindow(target);
  }));
});
