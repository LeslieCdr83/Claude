"use strict";

const vue = document.getElementById("vue");
let etat = { cle_claude: false };
let filtre = { q: "", tag: "" };
let minuterie = null;

// ---------- Outils ----------
const echap = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(chemin, options = {}) {
  const rep = await fetch(chemin, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!rep.ok) {
    let msg = `Erreur ${rep.status}`;
    try { msg = (await rep.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  return rep.json();
}

function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("visible");
  clearTimeout(t._m);
  t._m = setTimeout(() => t.classList.remove("visible"), 3000);
}

const lireStock = (cle, defaut) => { try { return JSON.parse(localStorage.getItem(cle)) ?? defaut; } catch (_) { return defaut; } };
const ecrireStock = (cle, val) => { try { localStorage.setItem(cle, JSON.stringify(val)); } catch (_) {} };

const panier = () => lireStock("courses", []);
function majCompteur() {
  const n = panier().length;
  document.getElementById("compteur-courses").textContent = n ? n : "";
}

// Quantités : "1/2", "1,5", "2-3" sont pris en compte pour ajuster les portions.
function versNombre(txt) {
  const s = String(txt).trim().replace(",", ".");
  let m = s.match(/^(\d+)\s+(\d+)\/(\d+)$/);
  if (m) return +m[1] + m[2] / m[3];
  m = s.match(/^(\d+)\/(\d+)$/);
  if (m) return m[1] / m[2];
  return /^\d+(\.\d+)?$/.test(s) ? parseFloat(s) : null;
}
function formater(n) {
  if (Math.abs(n - Math.round(n)) < 0.05) return String(Math.round(n));
  return (Math.round(n * 10) / 10).toString().replace(".", ",");
}
// Sans unité (œufs, citrons...) : nombre entier, ou demi en dessous de 1.
function arrondir(n, unite) {
  if (unite) return n;
  return n < 1 ? Math.max(0.5, Math.round(n * 2) / 2) : Math.round(n);
}
function ajuster(qte, facteur, unite = "x") {
  if (!qte || facteur === 1) return qte || "";
  const plage = String(qte).match(/^([\d.,/ ]+)\s*-\s*([\d.,/ ]+)$/);
  if (plage) {
    const a = versNombre(plage[1]), b = versNombre(plage[2]);
    if (a != null && b != null) return `${formater(arrondir(a * facteur, unite))}-${formater(arrondir(b * facteur, unite))}`;
  }
  const n = versNombre(qte);
  return n == null ? qte : formater(arrondir(n * facteur, unite));
}
const nombrePortions = (p) => { const m = String(p || "").match(/\d+/); return m ? +m[0] : null; };

function imageRecette(r) {
  return r.miniature ? `/images/${encodeURI(r.miniature)}` : "/icone.svg";
}

// ---------- Liste ----------
async function vueListe() {
  const alerte = etat.cle_claude ? "" : `<p class="alerte">Pas encore de clé Claude. L'import fonctionne déjà : il garde la vidéo, la légende et la transcription. Ajoute une clé (voir le README) pour obtenir la fiche complète.</p>`;
  vue.innerHTML = `
    <section class="import">
      <h2>Ajouter une recette</h2>
      <p>Colle le lien d'une vidéo TikTok, Instagram ou YouTube.</p>
      <form class="ligne" id="form-import">
        <input type="text" id="champ-url" placeholder="https://www.tiktok.com/@..." inputmode="url" autocomplete="off" required>
        <button class="principal" type="submit">Importer</button>
      </form>
    </section>
    ${alerte}
    <div class="filtres">
      <input type="search" id="recherche" placeholder="Chercher un plat, un ingrédient..." value="${echap(filtre.q)}">
      <div class="puces" id="puces"></div>
    </div>
    <div id="liste"></div>`;

  document.getElementById("form-import").addEventListener("submit", async (e) => {
    e.preventDefault();
    const champ = document.getElementById("champ-url");
    await lancerImport(champ.value);
    champ.value = "";
  });
  let delai;
  document.getElementById("recherche").addEventListener("input", (e) => {
    clearTimeout(delai);
    delai = setTimeout(() => { filtre.q = e.target.value; chargerListe(); }, 200);
  });
  await chargerPuces();
  await chargerListe();
}

async function chargerPuces() {
  const tags = await api("/api/tags");
  const zone = document.getElementById("puces");
  if (!zone) return;
  const puces = ["", ...tags].map((t) => `<button class="puce ${filtre.tag === t ? "active" : ""}" data-tag="${echap(t)}">${t ? echap(t) : "Toutes"}</button>`);
  zone.innerHTML = tags.length ? puces.join("") : "";
  zone.querySelectorAll(".puce").forEach((b) => b.addEventListener("click", () => {
    filtre.tag = b.dataset.tag;
    chargerPuces();
    chargerListe();
  }));
}

async function chargerListe() {
  const zone = document.getElementById("liste");
  if (!zone) return;
  const params = new URLSearchParams(filtre);
  const recettes = await api(`/api/recettes?${params}`);
  if (!recettes.length) {
    zone.innerHTML = `<p class="vide">${filtre.q || filtre.tag ? "Aucune recette ne correspond." : "Aucune recette pour l'instant. Colle un lien ci-dessus pour commencer."}</p>`;
    return;
  }
  zone.innerHTML = `<div class="grille">${recettes.map(carte).join("")}</div>`;
  surveiller(recettes.some((r) => r.statut === "en_cours"), chargerListe);
}

function carte(r) {
  const etiquettes = {
    en_cours: `<span class="etiquette"><span class="chargement"></span> ${echap(r.progression || "En cours")}</span>`,
    brouillon: `<span class="etiquette">Brouillon</span>`,
    erreur: `<span class="etiquette erreur">Échec</span>`,
  };
  const meta = [r.temps_preparation && `⏱ ${r.temps_preparation}`, r.auteur].filter(Boolean).map(echap).join(" · ");
  return `
    <a class="carte" href="#/recette/${r.id}">
      <div class="visuel">
        <img src="${imageRecette(r)}" alt="" loading="lazy">
        ${etiquettes[r.statut] || ""}
        ${r.favori ? `<span class="coeur">❤️</span>` : ""}
      </div>
      <div class="infos">
        <h3>${echap(r.titre || "Sans titre")}</h3>
        ${meta ? `<div class="meta">${meta}</div>` : ""}
      </div>
    </a>`;
}

function surveiller(actif, rappel) {
  clearTimeout(minuterie);
  if (actif) minuterie = setTimeout(rappel, 2500);
}

async function lancerImport(texte) {
  try {
    const res = await api("/api/importer", { method: "POST", body: { url: texte } });
    if (res.deja_presente) toast("Cette recette est déjà dans ta bibliothèque.");
    else toast("Import lancé. Compte 30 secondes à 2 minutes.");
    location.hash = `#/recette/${res.id}`;
  } catch (err) {
    toast(err.message);
  }
}

// ---------- Fiche ----------
// Message gardé d'un import fait avant l'ajout de la clé.
const cleAjoutee = (r) => etat.cle_claude && r.statut === "brouillon" && (r.erreur || "").startsWith("Pas de clé Claude");

async function vueRecette(id) {
  let r;
  try { r = await api(`/api/recettes/${id}`); } catch (err) { vue.innerHTML = `<p class="vide">${echap(err.message)}</p>`; return; }

  if (r.statut === "en_cours") {
    vue.innerHTML = `<div class="attente"><p><span class="chargement"></span></p><p><strong>${echap(r.progression || "Import en cours")}</strong></p><p>${echap(r.titre && r.titre !== "Import en cours" ? r.titre : r.source_url)}</p></div>`;
    surveiller(true, () => routeur());
    return;
  }

  const base = nombrePortions(r.portions);
  let portions = base ? (etat.portions_defaut || base) : base;
  const dansPanier = panier().some((p) => p.id === r.id);
  const chiffres = [
    r.portions && `🍽 ${r.portions}`,
    r.temps_preparation && `🔪 Préparation ${r.temps_preparation}`,
    r.temps_cuisson && `🔥 Cuisson ${r.temps_cuisson}`,
  ].filter(Boolean).map((c) => `<span>${echap(c)}</span>`).join("");

  const boutonAnalyser = r.source_url && (r.statut === "brouillon" || r.statut === "pret")
    ? `<button id="b-analyser" ${etat.cle_claude ? "" : "disabled title='Ajoute une clé Claude'"}>${r.statut === "pret" ? "Réanalyser" : "Analyser avec Claude"}</button>` : "";

  vue.innerHTML = `
    ${r.erreur ? `<p class="alerte">${echap(cleAjoutee(r) ? "Clé Claude détectée. Clique sur « Analyser avec Claude » pour rédiger la fiche de cette recette." : r.erreur)}</p>` : ""}
    <div class="fiche-entete">
      <img src="${imageRecette(r)}" alt="">
      <div>
        <h1>${echap(r.titre || "Sans titre")}</h1>
        <div class="source">${[r.auteur, r.plateforme].filter(Boolean).map(echap).join(" · ")}
          ${r.source_url ? ` · <a href="${echap(r.source_url)}" target="_blank" rel="noopener">Voir la vidéo</a>` : ""}</div>
        <div class="chiffres">${chiffres}</div>
        <div class="puces">${r.tags.map((t) => `<span class="puce">${echap(t)}</span>`).join("")}</div>
        <div class="actions">
          <button id="b-favori">${r.favori ? "❤️ Favori" : "🤍 Favori"}</button>
          <button id="b-panier">${dansPanier ? "✓ Dans les courses" : "🛒 Ajouter aux courses"}</button>
          <a class="bouton" href="#/recette/${r.id}/modifier">Modifier</a>
          ${boutonAnalyser}
          ${r.statut === "erreur" ? `<button id="b-reimporter" class="principal">Réessayer l'import</button>` : ""}
          <button id="b-imprimer">Imprimer</button>
          <button id="b-supprimer" class="danger">Supprimer</button>
        </div>
      </div>
    </div>

    <section class="bloc">
      <h2>Ingrédients
        ${base ? `<span class="portions"><button id="moins" aria-label="Moins de portions">−</button><span id="nb-portions">${portions}</span> pers.<button id="plus" aria-label="Plus de portions">+</button></span>` : ""}
      </h2>
      ${base ? `<p class="aide" id="origine"></p>` : `<p class="aide">Nombre de personnes inconnu : quantités de la vidéo.</p>`}
      <ul class="ingredients" id="ingredients"></ul>
    </section>

    <section class="bloc">
      <h2>Étapes</h2>
      ${r.etapes.length ? `<ol class="etapes">${r.etapes.map((e) => `<li>${echap(e)}</li>`).join("")}</ol>` : `<p class="vide">Aucune étape pour l'instant.</p>`}
    </section>

    <section class="bloc" id="appareils"></section>

    ${r.notes ? `<section class="bloc"><h2>Notes</h2><p>${echap(r.notes).replace(/\n/g, "<br>")}</p></section>` : ""}

    <section class="bloc">
      <details><summary>Légende du post</summary><pre>${echap(r.legende || "(vide)")}</pre></details>
      <details><summary>Transcription de la voix</summary><pre>${echap(r.transcription || "(aucune)")}</pre></details>
      ${r.images.length ? `<details><summary>Captures de la vidéo</summary><div class="captures">${r.images.map((i) => `<img src="/images/${encodeURI(i)}" alt="" loading="lazy">`).join("")}</div></details>` : ""}
    </section>`;

  const coches = lireStock(`coches-${r.id}`, []);
  function dessinerIngredients() {
    const facteur = base && portions ? portions / base : 1;
    const origine = document.getElementById("origine");
    if (origine) origine.textContent = portions === base ? "Quantités de la recette d'origine." : `Quantités recalculées. Recette d'origine : ${r.portions}.`;
    const ul = document.getElementById("ingredients");
    if (!r.ingredients.length) { ul.innerHTML = `<li class="vide">Aucun ingrédient pour l'instant.</li>`; return; }
    ul.innerHTML = r.ingredients.map((i, n) => `
      <li><label class="${coches.includes(n) ? "coche" : ""}">
        <input type="checkbox" data-n="${n}" ${coches.includes(n) ? "checked" : ""}>
        <span class="qte">${echap([ajuster(i.quantite, facteur, i.unite), i.unite].filter(Boolean).join(" "))}</span>
        <span>${echap(i.nom)}</span>
      </label></li>`).join("");
    ul.querySelectorAll("input").forEach((c) => c.addEventListener("change", () => {
      const n = +c.dataset.n;
      const pos = coches.indexOf(n);
      pos >= 0 ? coches.splice(pos, 1) : coches.push(n);
      ecrireStock(`coches-${r.id}`, coches);
      c.parentElement.classList.toggle("coche", c.checked);
    }));
  }
  dessinerIngredients();
  dessinerAppareils(r);

  if (base) {
    const maj = (d) => { portions = Math.max(1, portions + d); document.getElementById("nb-portions").textContent = portions; dessinerIngredients(); };
    document.getElementById("moins").onclick = () => maj(-1);
    document.getElementById("plus").onclick = () => maj(1);
  }
  document.getElementById("b-favori").onclick = async () => { await api(`/api/recettes/${r.id}`, { method: "PUT", body: { favori: !r.favori } }); routeur(); };
  document.getElementById("b-panier").onclick = () => {
    let p = panier();
    if (p.some((x) => x.id === r.id)) p = p.filter((x) => x.id !== r.id);
    else p.push({ id: r.id, facteur: base && portions ? portions / base : 1 });
    ecrireStock("courses", p);
    majCompteur();
    routeur();
  };
  document.getElementById("b-imprimer").onclick = () => window.print();
  document.getElementById("b-supprimer").onclick = async () => {
    if (!confirm("Supprimer cette recette ?")) return;
    await api(`/api/recettes/${r.id}`, { method: "DELETE" });
    ecrireStock("courses", panier().filter((x) => x.id !== r.id));
    majCompteur();
    location.hash = "#/";
  };
  const ba = document.getElementById("b-analyser");
  if (ba) ba.onclick = async () => {
    try { await api(`/api/recettes/${r.id}/analyser`, { method: "POST" }); routeur(); } catch (err) { toast(err.message); }
  };
  const br = document.getElementById("b-reimporter");
  if (br) br.onclick = async () => { await api(`/api/recettes/${r.id}/reimporter`, { method: "POST" }); routeur(); };
}

// ---------- Thermomix et airfryer ----------
const APPAREILS = [
  { cle: "thermomix", nom: "Thermomix TM7" },
  { cle: "airfryer", nom: "Airfryer Ninja" },
];
const FAISABLE = { oui: "Faisable", partiel: "En partie", non: "Pas adapté" };

function dessinerAppareils(r, onglet = "thermomix") {
  const zone = document.getElementById("appareils");
  if (!zone) return;
  const a = r.adaptations || {};
  if (!a.thermomix) {
    const possible = r.ingredients.length || r.etapes.length;
    zone.innerHTML = `
      <h2>Thermomix TM7 et airfryer Ninja</h2>
      <p class="aide">Claude rédige les deux versions pour ${etat.portions_defaut || 4} personnes, avec les réglages de chaque appareil.</p>
      <div class="actions"><button class="principal" id="b-adapter" ${etat.cle_claude && possible ? "" : "disabled"}>Adapter la recette</button></div>
      ${etat.cle_claude ? "" : `<p class="aide">Ajoute une clé Claude pour utiliser cette fonction.</p>`}`;
  } else {
    const ap = a[onglet] || {};
    const pastille = (v, icone) => v ? `<span class="reglage">${icone} ${echap(v)}</span>` : "";
    zone.innerHTML = `
      <h2>Avec un appareil</h2>
      <div class="onglets" role="tablist">
        ${APPAREILS.map((x) => `<button role="tab" class="onglet ${x.cle === onglet ? "actif" : ""}" data-onglet="${x.cle}" aria-selected="${x.cle === onglet}">${x.nom}</button>`).join("")}
      </div>
      <p><span class="faisable ${echap(ap.faisable)}">${FAISABLE[ap.faisable] || ""}</span> ${echap(ap.resume || "")}</p>
      ${ap.explication ? `<p class="aide">${echap(ap.explication)}</p>` : ""}
      ${a.ingredients && a.ingredients.length && ap.faisable !== "non" ? `
        <details><summary>Ingrédients pour ${echap(a.portions)} personnes</summary>
          <ul class="ingredients">${a.ingredients.map((i) => `<li><span class="qte">${echap([i.quantite, i.unite].filter(Boolean).join(" "))}</span><span>${echap(i.nom)}</span></li>`).join("")}</ul>
        </details>` : ""}
      ${(ap.etapes || []).length ? `<ol class="etapes etapes-appareil">${ap.etapes.map((e) => `
        <li>${echap(e.instruction)}
          <div class="reglages">${pastille(e.mode, "⚙️")}${pastille(e.temps, "⏱")}${pastille(e.temperature, "🌡")}${pastille(e.vitesse, "🌀")}</div>
        </li>`).join("")}</ol>` : ""}
      ${ap.conseils ? `<p class="aide">💡 ${echap(ap.conseils)}</p>` : ""}
      <div class="actions"><button id="b-adapter" ${etat.cle_claude ? "" : "disabled"}>Régénérer</button></div>`;
    zone.querySelectorAll("[data-onglet]").forEach((b) => b.onclick = () => dessinerAppareils(r, b.dataset.onglet));
  }
  const bouton = document.getElementById("b-adapter");
  if (bouton) bouton.onclick = async () => {
    bouton.disabled = true;
    bouton.innerHTML = `<span class="chargement"></span> Adaptation en cours, 20 à 60 s`;
    try {
      const maj = await api(`/api/recettes/${r.id}/adapter`, { method: "POST" });
      r.adaptations = maj.adaptations;
      dessinerAppareils(r, onglet);
    } catch (err) {
      toast(err.message);
      dessinerAppareils(r, onglet);
    }
  };
}

// ---------- Édition ----------
async function vueEdition(id) {
  const r = id ? await api(`/api/recettes/${id}`) : { titre: "", portions: "", temps_preparation: "", temps_cuisson: "", ingredients: [], etapes: [], tags: [], notes: "" };
  const ingr = r.ingredients.length ? [...r.ingredients] : [{ quantite: "", unite: "", nom: "" }];
  const etapes = r.etapes.length ? [...r.etapes] : [""];

  vue.innerHTML = `
    <form class="formulaire bloc" id="form-edition">
      <h2>${id ? "Modifier la recette" : "Nouvelle recette"}</h2>
      <label for="f-titre">Titre</label>
      <input id="f-titre" value="${echap(r.titre)}" required>
      <div class="trois">
        <div><label for="f-portions">Portions</label><input id="f-portions" value="${echap(r.portions)}" placeholder="4 personnes"></div>
        <div><label for="f-prep">Préparation</label><input id="f-prep" value="${echap(r.temps_preparation)}" placeholder="15 min"></div>
        <div><label for="f-cuisson">Cuisson</label><input id="f-cuisson" value="${echap(r.temps_cuisson)}" placeholder="30 min"></div>
      </div>
      <label>Ingrédients</label>
      <div id="f-ingr"></div>
      <button type="button" id="ajout-ingr">+ Ingrédient</button>
      <label>Étapes</label>
      <div id="f-etapes"></div>
      <button type="button" id="ajout-etape">+ Étape</button>
      <label for="f-tags">Tags</label>
      <input id="f-tags" value="${echap(r.tags.join(", "))}" placeholder="dessert, rapide">
      <p class="aide">Sépare les tags par des virgules.</p>
      <label for="f-notes">Notes</label>
      <textarea id="f-notes">${echap(r.notes)}</textarea>
      <div class="actions">
        <button class="principal" type="submit">Enregistrer</button>
        <a class="bouton" href="${id ? `#/recette/${id}` : "#/"}">Annuler</a>
      </div>
    </form>`;

  const zoneIngr = document.getElementById("f-ingr");
  const zoneEtapes = document.getElementById("f-etapes");
  const lireIngr = () => [...zoneIngr.children].map((l) => ({ quantite: l.children[0].value, unite: l.children[1].value, nom: l.children[2].value }));
  const lireEtapes = () => [...zoneEtapes.children].map((l) => l.children[0].value);

  function dessiner() {
    zoneIngr.innerHTML = ingr.map((i, n) => `
      <div class="ligne-ingr">
        <input value="${echap(i.quantite)}" placeholder="Qté" aria-label="Quantité">
        <input value="${echap(i.unite)}" placeholder="Unité" aria-label="Unité">
        <input value="${echap(i.nom)}" placeholder="Ingrédient" aria-label="Ingrédient">
        <button type="button" data-suppr-ingr="${n}" aria-label="Retirer">✕</button>
      </div>`).join("");
    zoneEtapes.innerHTML = etapes.map((e, n) => `
      <div class="ligne-etape">
        <textarea aria-label="Étape ${n + 1}" placeholder="Étape ${n + 1}">${echap(e)}</textarea>
        <button type="button" data-suppr-etape="${n}" aria-label="Retirer">✕</button>
      </div>`).join("");
    zoneIngr.querySelectorAll("[data-suppr-ingr]").forEach((b) => b.onclick = () => { ingr.splice(0, ingr.length, ...lireIngr()); ingr.splice(+b.dataset.supprIngr, 1); dessiner(); });
    zoneEtapes.querySelectorAll("[data-suppr-etape]").forEach((b) => b.onclick = () => { etapes.splice(0, etapes.length, ...lireEtapes()); etapes.splice(+b.dataset.supprEtape, 1); dessiner(); });
  }
  dessiner();
  document.getElementById("ajout-ingr").onclick = () => { ingr.splice(0, ingr.length, ...lireIngr(), { quantite: "", unite: "", nom: "" }); dessiner(); };
  document.getElementById("ajout-etape").onclick = () => { etapes.splice(0, etapes.length, ...lireEtapes(), ""); dessiner(); };

  document.getElementById("form-edition").addEventListener("submit", async (e) => {
    e.preventDefault();
    const donnees = {
      titre: document.getElementById("f-titre").value.trim(),
      portions: document.getElementById("f-portions").value.trim(),
      temps_preparation: document.getElementById("f-prep").value.trim(),
      temps_cuisson: document.getElementById("f-cuisson").value.trim(),
      ingredients: lireIngr().filter((i) => i.nom.trim()),
      etapes: lireEtapes().map((s) => s.trim()).filter(Boolean),
      tags: document.getElementById("f-tags").value.split(",").map((t) => t.trim()).filter(Boolean),
      notes: document.getElementById("f-notes").value,
    };
    try {
      const res = id
        ? await api(`/api/recettes/${id}`, { method: "PUT", body: donnees })
        : await api("/api/recettes", { method: "POST", body: donnees });
      toast("Recette enregistrée.");
      location.hash = `#/recette/${res.id}`;
    } catch (err) { toast(err.message); }
  });
}

// ---------- Courses ----------
async function vueCourses() {
  const p = panier();
  if (!p.length) {
    vue.innerHTML = `<p class="vide">Ta liste de courses est vide. Ouvre une recette et clique sur « Ajouter aux courses ».</p>`;
    return;
  }
  const recettes = (await Promise.all(p.map((x) => api(`/api/recettes/${x.id}`).catch(() => null))))
    .map((r, n) => r && { ...r, facteur: p[n].facteur || 1 }).filter(Boolean);

  // Fusionne les ingrédients de même nom et même unité quand les quantités sont des nombres.
  const lignes = new Map();
  for (const r of recettes) {
    for (const i of r.ingredients) {
      const cle = `${i.nom.trim().toLowerCase()}|${(i.unite || "").trim().toLowerCase()}`;
      const n = versNombre(i.quantite);
      const l = lignes.get(cle) || { nom: i.nom.trim(), unite: i.unite, total: 0, autres: [] };
      if (n != null) l.total += n * r.facteur;
      else if (i.quantite) l.autres.push(i.quantite);
      lignes.set(cle, l);
    }
  }
  const coches = lireStock("coches-courses", []);
  const triees = [...lignes.entries()].sort((a, b) => a[1].nom.localeCompare(b[1].nom, "fr"));

  vue.innerHTML = `
    <section class="bloc">
      <h2>Liste de courses <button id="vider" class="danger">Vider</button></h2>
      <p class="aide">${recettes.map((r) => `<a href="#/recette/${r.id}">${echap(r.titre)}</a>`).join(" · ")}</p>
      <ul class="ingredients">
        ${triees.map(([cle, l]) => {
          const qte = [l.total ? formater(l.total) : "", ...l.autres].filter(Boolean).join(" + ");
          const fait = coches.includes(cle);
          return `<li><label class="${fait ? "coche" : ""}"><input type="checkbox" data-cle="${echap(cle)}" ${fait ? "checked" : ""}>
            <span class="qte">${echap([qte, l.unite].filter(Boolean).join(" "))}</span><span>${echap(l.nom)}</span></label></li>`;
        }).join("")}
      </ul>
      <div class="actions"><button id="copier">Copier la liste</button></div>
    </section>`;

  vue.querySelectorAll("input[data-cle]").forEach((c) => c.addEventListener("change", () => {
    const liste = lireStock("coches-courses", []);
    const pos = liste.indexOf(c.dataset.cle);
    pos >= 0 ? liste.splice(pos, 1) : liste.push(c.dataset.cle);
    ecrireStock("coches-courses", liste);
    c.parentElement.classList.toggle("coche", c.checked);
  }));
  document.getElementById("vider").onclick = () => { ecrireStock("courses", []); ecrireStock("coches-courses", []); majCompteur(); vueCourses(); };
  document.getElementById("copier").onclick = async () => {
    const texte = triees.map(([, l]) => `- ${[l.total ? formater(l.total) : "", ...l.autres].filter(Boolean).join(" + ")} ${l.unite || ""} ${l.nom}`.replace(/\s+/g, " ").trim()).join("\n");
    try { await navigator.clipboard.writeText(texte); toast("Liste copiée."); } catch (_) { toast("Copie impossible sur ce navigateur."); }
  };
}

// ---------- Routeur ----------
async function routeur() {
  clearTimeout(minuterie);
  const h = location.hash || "#/";
  let m;
  try {
    if ((m = h.match(/^#\/recette\/(\d+)\/modifier$/))) await vueEdition(+m[1]);
    else if ((m = h.match(/^#\/recette\/(\d+)$/))) await vueRecette(+m[1]);
    else if (h === "#/nouvelle") await vueEdition(null);
    else if (h === "#/courses") await vueCourses();
    else await vueListe();
  } catch (err) {
    vue.innerHTML = `<p class="vide">${echap(err.message)}</p>`;
  }
}

async function demarrer() {
  try { etat = await api("/api/etat"); } catch (_) {}
  majCompteur();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});

  // Partage depuis TikTok ou Instagram (appli installée sur le téléphone).
  const params = new URLSearchParams(location.search);
  const partage = [params.get("url"), params.get("text"), params.get("title")].filter(Boolean).join(" ");
  if (partage) {
    history.replaceState(null, "", "/");
    await lancerImport(partage);
  }
  window.addEventListener("hashchange", routeur);
  routeur();
}

demarrer();
