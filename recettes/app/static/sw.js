// Service worker : installation de l'appli, menu Partager, notifications et mode hors ligne.
//
// Hors ligne : chaque réponse reçue du PC est gardée sur l'appareil. Quand le PC ne répond pas
// (éteint, appli fermée, pas de réseau), l'appli affiche cette copie. Les réponses tirées de la
// copie portent l'en-tête X-Hors-Ligne pour que la page affiche un bandeau.
const CACHE_APP = "mes-recettes-app-v1";
const CACHE_DONNEES = "mes-recettes-donnees-v1";
const CACHE_IMAGES = "mes-recettes-images-v1";
const COQUILLE = ["/", "/app.js", "/style.css", "/manifest.json", "/icone.svg", "/icone-192.png", "/icone-512.png"];
const DELAI = 4000; // au-delà, on considère le PC injoignable

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE_APP).then((c) => c.addAll(COQUILLE)).catch(() => {}).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

function avecDelai(promesse) {
  return Promise.race([promesse, new Promise((_, refus) => setTimeout(() => refus(new Error("délai")), DELAI))]);
}

function marquerHorsLigne(reponse) {
  const entetes = new Headers(reponse.headers);
  entetes.set("X-Hors-Ligne", "1");
  return reponse.blob().then((corps) => new Response(corps, { status: reponse.status, headers: entetes }));
}

// Réseau d'abord, copie ensuite.
async function reseauPuisCopie(requete, nomCache, cleCopie = requete) {
  const cache = await caches.open(nomCache);
  try {
    const reponse = await avecDelai(fetch(requete));
    if (reponse.ok) await cache.put(cleCopie, reponse.clone());
    return reponse;
  } catch (err) {
    const copie = await cache.match(cleCopie, { ignoreSearch: nomCache === CACHE_APP });
    if (copie) return marquerHorsLigne(copie);
    throw err;
  }
}

// Liste des recettes : toute la liste est gardée, la recherche se fait ici quand le PC ne répond pas.
async function listeRecettes(requete) {
  const url = new URL(requete.url);
  const q = (url.searchParams.get("q") || "").toLowerCase();
  const tag = (url.searchParams.get("tag") || "").toLowerCase();
  const cache = await caches.open(CACHE_DONNEES);
  try {
    const reponse = await avecDelai(fetch(requete));
    if (reponse.ok && !q && !tag) await cache.put("/api/recettes", reponse.clone());
    return reponse;
  } catch (err) {
    const copie = await cache.match("/api/recettes");
    if (!copie) throw err;
    let recettes = await copie.json();
    if (tag) recettes = recettes.filter((r) => r.tags.some((t) => t.toLowerCase() === tag));
    if (q) {
      const mots = q.split(/\s+/).filter(Boolean);
      const texte = (r) => [r.titre, r.auteur, r.ingredients.map((i) => i.nom).join(" "), r.tags.join(" "), r.notes]
        .join(" ").toLowerCase();
      recettes = recettes.filter((r) => mots.every((m) => texte(r).includes(m)));
    }
    return new Response(JSON.stringify(recettes), {
      headers: { "Content-Type": "application/json", "X-Hors-Ligne": "1" },
    });
  }
}

// Images : la copie d'abord (elles ne changent pas), le réseau si elle manque.
async function image(requete) {
  const cache = await caches.open(CACHE_IMAGES);
  const copie = await cache.match(requete);
  if (copie) return copie;
  const reponse = await fetch(requete);
  if (reponse.ok) await cache.put(requete, reponse.clone());
  return reponse;
}

self.addEventListener("fetch", (e) => {
  const requete = e.request;
  const url = new URL(requete.url);
  if (requete.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/images/")) return e.respondWith(image(requete));
  if (url.pathname === "/api/recettes") return e.respondWith(listeRecettes(requete));
  if (url.pathname.startsWith("/api/")) {
    // Pas de copie pour les actions qui n'ont de sens qu'en ligne.
    if (/^\/api\/(notifications|reglages)/.test(url.pathname)) return;
    return e.respondWith(reseauPuisCopie(requete, CACHE_DONNEES));
  }
  if (requete.mode === "navigate") return e.respondWith(reseauPuisCopie(requete, CACHE_APP, "/"));
  if (COQUILLE.includes(url.pathname)) return e.respondWith(reseauPuisCopie(requete, CACHE_APP));
});

// ---------- Notifications ----------
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
