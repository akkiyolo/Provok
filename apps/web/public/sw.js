/* Provok service worker: web push only (no offline caching, so deploys are never served stale). */

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: event.data ? event.data.text() : "" };
  }
  const title = data.title || "Provok";
  const link = typeof data.link === "string" && data.link.startsWith("/") && !data.link.startsWith("//")
    ? data.link : "/notifications";
  event.waitUntil(self.registration.showNotification(title, {
    body: data.body || "",
    icon: "/icon",
    tag: data.tag || data.kind || "provok",
    renotify: Boolean(data.tag),
    data: { link },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.link || "/notifications", self.location.origin).href;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const open = windows.find((w) => new URL(w.url).origin === self.location.origin);
    if (open) {
      await open.focus();
      try {
        return await open.navigate(url);
      } catch {
        return self.clients.openWindow(url); // a tab this worker doesn't control yet can't be navigated
      }
    }
    return self.clients.openWindow(url);
  })());
});
