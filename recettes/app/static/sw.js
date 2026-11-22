// Service worker minimal : nécessaire pour installer l'appli et apparaître dans le menu Partager.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
