// Service worker : nécessaire pour installer l'appli, apparaître dans le menu Partager
// et recevoir les notifications.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});

self.addEventListener("push", (e) => {
  let message = { titre: "Mes recettes", texte: "", lien: "/#/menus" };
  try { message = { ...message, ...e.data.json() }; } catch (_) {}
  e.waitUntil(self.registration.showNotification(message.titre, {
    body: message.texte,
    icon: "/icone-192.png",
    badge: "/icone-192.png",
    data: { lien: message.lien },
  }));
});

// Toucher la notification ouvre l'appli sur le menu.
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const lien = new URL((e.notification.data && e.notification.data.lien) || "/#/menus", self.location.origin).href;
  e.waitUntil((async () => {
    const fenetres = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const f of fenetres) {
      if ("focus" in f) { await f.navigate(lien).catch(() => {}); return f.focus(); }
    }
    return self.clients.openWindow(lien);
  })());
});
