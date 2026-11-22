"use strict";

const vue = document.getElementById("vue");
let etat = { api: false, claude_code: false };
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

// ---------- Choix entre API Claude, Claude Code et copier-coller ----------
const NOMS_MODES = { api: "API Claude", abonnement: "Claude Code", manuel: "Appli Claude (copier-coller)" };
const modeDispo = (mode) => (mode === "api" ? etat.api : mode === "abonnement" ? etat.claude_code : true);
// Dernier mode utilisé, s'il fonctionne encore. Sinon le premier disponible.
function modePrefere() {
  const m = lireStock("mode-prefere", "");
  if (m && m !== "manuel" && modeDispo(m)) return m;
  return etat.claude_code ? "abonnement" : etat.api ? "api" : "";
}
function boutonMode(mode, type = "button", action = "") {
  const indispo = !modeDispo(mode);
  const titre = mode === "api" ? "Enregistre une clé API dans Réglages" : "Installe Claude Code (voir le README)";
  return `<button type="${type}" data-mode="${mode}" ${action ? `data-action="${action}"` : ""}
    class="${mode === modePrefere() ? "principal" : ""}" ${indispo ? `disabled title="${titre}"` : ""}>${NOMS_MODES[mode]}</button>`;
}
// Explique pourquoi un bouton est grisé (pas de survol sur téléphone).
function aideModes() {
  const manque = [];
  if (!etat.api) manque.push(`API Claude : enregistre une clé dans <a href="#/reglages">Réglages</a>.`);
  if (!etat.claude_code) manque.push("Claude Code : installe-le sur l'ordinateur (voir le README).");
  return manque.length ? `<p class="aide">${manque.join("<br>")}</p>` : "";
}
function choixClaude(action) {
  return `<div class="choix-claude">${boutonMode("api", "button", action)}${boutonMode("abonnement", "button", action)}${boutonMode("manuel", "button", action)}</div>${aideModes()}`;
}

// ---------- Liste ----------
async function vueListe() {
  const alerte = etat.api || etat.claude_code ? "" : `<p class="alerte">Ni clé API ni Claude Code pour l'instant. Tu peux importer sans analyse, puis copier-coller avec l'appli Claude. Pour l'analyse automatique, enregistre une clé dans <a href="#/reglages">Réglages</a> ou installe Claude Code.</p>`;
  vue.innerHTML = `
    <section class="import">
      <h2>Ajouter une recette</h2>
      <p>Colle le lien d'une vidéo TikTok, Instagram, Facebook ou YouTube.</p>
      <form id="form-import">
        <input type="text" id="champ-url" placeholder="https://www.tiktok.com/@..." inputmode="url" autocomplete="off" required>
        <p class="aide">Importer et rédiger la fiche avec :</p>
        <div class="choix-claude">
          ${boutonMode("api", "submit")}
          ${boutonMode("abonnement", "submit")}
          <button type="submit" data-mode="">Sans analyse</button>
        </div>
        ${aideModes()}
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
    const mode = e.submitter ? e.submitter.dataset.mode : modePrefere();
    if (mode) ecrireStock("mode-prefere", mode);
    await lancerImport(champ.value, mode);
    champ.value = "";
  });
  // Touche Entrée : importe avec le mode préféré (un bouton grisé bloquerait l'envoi du formulaire).
  document.getElementById("champ-url").addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    document.getElementById("form-import").requestSubmit(
      document.querySelector(`#form-import button[data-mode="${modePrefere()}"]`) || undefined);
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

async function lancerImport(texte, mode = modePrefere()) {
  try {
    const res = await api("/api/importer", { method: "POST", body: { url: texte, mode: mode || null } });
    if (res.deja_presente) toast("Cette recette est déjà dans ta bibliothèque.");
    else toast("Import lancé. Compte 30 secondes à 2 minutes.");
    location.hash = `#/recette/${res.id}`;
  } catch (err) {
    toast(err.message);
  }
}

// ---------- Fiche ----------
// Les anciens messages de brouillon renvoient tous vers les boutons de choix.
function messageFiche(r) {
  const ancien = /^(Pas de clé Claude|Claude n'est pas connecté|Vidéo importée)/.test(r.erreur || "");
  return r.statut === "brouillon" && ancien ? "Vidéo importée. Choisis comment rédiger la fiche ci-dessous." : r.erreur;
}

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

  const analysable = r.source_url || r.legende || r.transcription;

  vue.innerHTML = `
    ${r.erreur ? `<p class="alerte">${echap(messageFiche(r))}</p>` : ""}
    ${r.statut === "brouillon" && analysable ? `
      <section class="bloc">
        <h2>Rédiger la fiche avec</h2>
        ${choixClaude("analyser")}
      </section>` : ""}
    <section class="bloc" id="manuel" hidden></section>
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
          <button id="b-coller">Coller un JSON Claude</button>
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
      <p class="aide" id="legende-estimee" hidden>≈ Quantité absente de la vidéo, estimée par Claude.</p>
    </section>

    <section class="bloc">
      <h2>Étapes</h2>
      ${r.etapes.length ? `<ol class="etapes">${r.etapes.map((e) => `<li>${echap(e)}</li>`).join("")}</ol>` : `<p class="vide">Aucune étape pour l'instant.</p>`}
    </section>

    <section class="bloc" id="appareils"></section>

    ${r.notes ? `<section class="bloc"><h2>Notes</h2><p>${echap(r.notes).replace(/\n/g, "<br>")}</p></section>` : ""}

    <section class="bloc">
      ${r.statut === "pret" && analysable ? `<details><summary>Réanalyser la vidéo</summary>${choixClaude("analyser")}</details>` : ""}
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
    const legende = document.getElementById("legende-estimee");
    if (legende) legende.hidden = !r.ingredients.some((i) => i.estimee && i.quantite);
    ul.innerHTML = r.ingredients.map((i, n) => `
      <li><label class="${coches.includes(n) ? "coche" : ""}">
        <input type="checkbox" data-n="${n}" ${coches.includes(n) ? "checked" : ""}>
        <span class="qte">${i.estimee && i.quantite ? "≈ " : ""}${echap([ajuster(i.quantite, facteur, i.unite), i.unite].filter(Boolean).join(" "))}</span>
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
  document.getElementById("b-coller").onclick = () => ouvrirCollage(r);
  document.getElementById("b-supprimer").onclick = async () => {
    if (!confirm("Supprimer cette recette ?")) return;
    await api(`/api/recettes/${r.id}`, { method: "DELETE" });
    ecrireStock("courses", panier().filter((x) => x.id !== r.id));
    majCompteur();
    location.hash = "#/";
  };
  vue.querySelectorAll('[data-action="analyser"]').forEach((b) => b.onclick = async () => {
    const mode = b.dataset.mode;
    if (mode === "manuel") return ouvrirManuel(r, "fiche");
    ecrireStock("mode-prefere", mode);
    try { await api(`/api/recettes/${r.id}/analyser?mode=${mode}`, { method: "POST" }); routeur(); } catch (err) { toast(err.message); }
  });
  const br = document.getElementById("b-reimporter");
  if (br) br.onclick = async () => {
    const mode = modePrefere();
    try { await api(`/api/recettes/${r.id}/reimporter${mode ? `?mode=${mode}` : ""}`, { method: "POST" }); routeur(); } catch (err) { toast(err.message); }
  };
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
      ${possible ? `<p class="aide">Adapter avec :</p>${choixClaude("adapter")}` : `<p class="aide">Ajoute d'abord des ingrédients ou des étapes.</p>`}`;
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
          <ul class="ingredients">${a.ingredients.map((i) => `<li><span class="qte">${i.estimee && i.quantite ? "≈ " : ""}${echap([i.quantite, i.unite].filter(Boolean).join(" "))}</span><span>${echap(i.nom)}</span></li>`).join("")}</ul>
        </details>` : ""}
      ${(ap.etapes || []).length ? `<ol class="etapes etapes-appareil">${ap.etapes.map((e) => `
        <li>${echap(e.instruction)}
          <div class="reglages">${pastille(e.mode, "⚙️")}${pastille(e.temps, "⏱")}${pastille(e.temperature, "🌡")}${pastille(e.vitesse, "🌀")}</div>
        </li>`).join("")}</ol>` : ""}
      ${ap.conseils ? `<p class="aide">💡 ${echap(ap.conseils)}</p>` : ""}
      <details><summary>Régénérer</summary>${choixClaude("adapter")}</details>`;
    zone.querySelectorAll("[data-onglet]").forEach((b) => b.onclick = () => dessinerAppareils(r, b.dataset.onglet));
  }
  zone.querySelectorAll('[data-action="adapter"]').forEach((bouton) => bouton.onclick = async () => {
    const mode = bouton.dataset.mode;
    if (mode === "manuel") return ouvrirManuel(r, "adaptation");
    ecrireStock("mode-prefere", mode);
    zone.querySelectorAll('[data-action="adapter"]').forEach((b) => { b.disabled = true; });
    bouton.innerHTML = `<span class="chargement"></span> Adaptation en cours, 20 à 60 s`;
    try {
      const maj = await api(`/api/recettes/${r.id}/adapter?mode=${mode}`, { method: "POST" });
      r.adaptations = maj.adaptations;
      dessinerAppareils(r, onglet);
    } catch (err) {
      toast(err.message);
      dessinerAppareils(r, onglet);
    }
  });
}

// ---------- Mode manuel : copier-coller avec l'appli Claude ----------
async function ouvrirManuel(r, type) {
  const zone = document.getElementById("manuel");
  let demande;
  try { demande = await api(`/api/recettes/${r.id}/demande?type=${type}`); } catch (err) { toast(err.message); return; }
  const titre = type === "fiche" ? "Analyser avec l'appli Claude" : "Adapter avec l'appli Claude";
  zone.hidden = false;
  zone.innerHTML = `
    <h2>${titre} <button id="m-fermer" aria-label="Fermer">✕</button></h2>
    <ol class="etapes">
      <li>Copie la demande.
        <div class="actions"><button class="principal" id="m-copier">Copier la demande</button></div>
        <details><summary>Voir la demande</summary><textarea id="m-demande" readonly rows="8">${echap(demande.texte)}</textarea></details>
      </li>
      <li>Ouvre une nouvelle conversation dans l'appli Claude ou sur <a href="https://claude.ai/new" target="_blank" rel="noopener">claude.ai</a> et colle la demande.
        ${demande.images.length ? `<p class="aide">Pour que Claude lise le texte affiché dans la vidéo, joins aussi les captures. Appui long ou clic droit pour les enregistrer.</p>
        <div class="captures">${demande.images.map((u) => `<a href="${encodeURI(u)}" download target="_blank"><img src="${encodeURI(u)}" alt="Capture"></a>`).join("")}</div>` : ""}
      </li>
      <li>Copie toute la réponse de Claude et colle-la ici.
        <textarea id="m-reponse" rows="8" placeholder='{"titre": "...", ...}'></textarea>
        <div class="actions"><button class="principal" id="m-valider">Enregistrer la réponse</button></div>
      </li>
    </ol>`;
  zone.scrollIntoView({ behavior: "smooth", block: "start" });
  document.getElementById("m-fermer").onclick = () => { zone.hidden = true; zone.innerHTML = ""; };
  document.getElementById("m-copier").onclick = async () => {
    try { await navigator.clipboard.writeText(demande.texte); toast("Demande copiée. Colle-la dans Claude."); }
    catch (_) {
      const champ = document.getElementById("m-demande");
      champ.closest("details").open = true;
      champ.select();
      toast("Copie automatique impossible : le texte est sélectionné, copie-le à la main.");
    }
  };
  document.getElementById("m-valider").onclick = async () => {
    const texte = document.getElementById("m-reponse").value;
    if (!texte.trim()) { toast("Colle d'abord la réponse de Claude."); return; }
    try {
      await api(`/api/recettes/${r.id}/reponse`, { method: "POST", body: { type, texte } });
      toast(type === "fiche" ? "Fiche enregistrée." : "Versions appareils enregistrées.");
      routeur();
    } catch (err) { toast(err.message); }
  };
}

// ---------- Coller un JSON Claude sur une recette existante ----------
const AIDE_JSON = "Colle une fiche ou une version TM7 et Ninja. L'appli reconnaît le type. Les champs absents gardent leur valeur actuelle : tu peux coller seulement les ingrédients, par exemple.";

async function enregistrerJson(id, texte) {
  if (!texte.trim()) throw new Error("Colle d'abord le JSON de Claude.");
  return api(`/api/recettes/${id}/reponse`, { method: "POST", body: { type: "auto", texte } });
}

function ouvrirCollage(r) {
  const zone = document.getElementById("manuel");
  zone.hidden = false;
  zone.innerHTML = `
    <h2>Coller un JSON Claude <button id="c-fermer" aria-label="Fermer">✕</button></h2>
    <p class="aide">${AIDE_JSON}</p>
    <textarea id="c-json" rows="10" placeholder='{"ingredients": [...], "etapes": [...]}'></textarea>
    <div class="actions"><button class="principal" id="c-valider">Mettre à jour la recette</button></div>
    <details><summary>Besoin d'une demande à donner à Claude ?</summary>
      <p class="aide">Copie la demande, colle-la dans Claude avec tes corrections (par exemple « mets 6 personnes »), puis recolle sa réponse ci-dessus.</p>
      <div class="actions">
        <button data-demande="fiche">Copier la demande pour la fiche</button>
        <button data-demande="adaptation">Copier la demande TM7 et Ninja</button>
      </div>
    </details>`;
  zone.scrollIntoView({ behavior: "smooth", block: "start" });
  document.getElementById("c-fermer").onclick = () => { zone.hidden = true; zone.innerHTML = ""; };
  document.getElementById("c-valider").onclick = async () => {
    try {
      await enregistrerJson(r.id, document.getElementById("c-json").value);
      toast("Recette mise à jour.");
      routeur();
    } catch (err) { toast(err.message); }
  };
  zone.querySelectorAll("[data-demande]").forEach((b) => b.onclick = async () => {
    try {
      const d = await api(`/api/recettes/${r.id}/demande?type=${b.dataset.demande}`);
      await navigator.clipboard.writeText(d.texte);
      toast("Demande copiée. Colle-la dans Claude.");
    } catch (err) { toast(err.message || "Copie impossible sur ce navigateur."); }
  });
}

// ---------- Réglages ----------
async function vueReglages() {
  const r = await api("/api/reglages");
  vue.innerHTML = `
    <form class="bloc formulaire" id="form-reglages">
      <h2>API Claude</h2>
      <p class="aide">Facturé à l'usage : environ 5 à 12 centimes par recette, fiche et appareils compris.</p>
      <label for="cle">Clé API</label>
      <input id="cle" type="password" autocomplete="off" placeholder="${r.cle_api ? echap(r.cle_api) : "sk-ant-..."}">
      <p class="aide">${r.cle_api ? "Une clé est enregistrée. Laisse le champ vide pour la garder." : "Crée une clé sur console.anthropic.com."}</p>
      <div class="actions">
        <button class="principal" type="submit">Enregistrer</button>
        <button type="button" data-tester="api">Tester l'API</button>
        ${r.cle_api ? `<button type="button" id="effacer-cle" class="danger">Effacer la clé</button>` : ""}
      </div>
      <p class="aide" id="test-api"></p>
    </form>
    <section class="bloc">
      <h2>Claude Code</h2>
      <p class="aide">Utilise ton abonnement Claude Pro ou Max, sans jetons facturés.</p>
      <p>${r.claude_code ? "✓ Claude Code est installé sur cet ordinateur." : "✗ Claude Code est introuvable. Installe-le (voir le README), puis relance l'appli."}</p>
      <div class="actions"><button type="button" data-tester="abonnement" ${r.claude_code ? "" : "disabled"}>Tester Claude Code</button></div>
      <p class="aide" id="test-abonnement"></p>
    </section>
    <section class="bloc">
      <h2>Appli Claude (copier-coller)</h2>
      <p class="aide">Rien à configurer. Fonctionne avec n'importe quel compte Claude, même gratuit.</p>
    </section>`;

  const form = document.getElementById("form-reglages");
  async function enregistrer(extra = {}) {
    const cle = document.getElementById("cle").value.trim();
    if (!cle && !Object.keys(extra).length) return;
    await api("/api/reglages", { method: "PUT", body: { ...(cle ? { cle_api: cle } : {}), ...extra } });
    etat = await api("/api/etat");
  }
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await enregistrer(); toast("Clé enregistrée."); vueReglages(); } catch (err) { toast(err.message); }
  });
  const effacer = document.getElementById("effacer-cle");
  if (effacer) effacer.onclick = async () => {
    if (!confirm("Effacer la clé API enregistrée ?")) return;
    try { await enregistrer({ effacer_cle: true }); toast("Clé effacée."); vueReglages(); } catch (err) { toast(err.message); }
  };
  vue.querySelectorAll("[data-tester]").forEach((b) => b.onclick = async () => {
    const mode = b.dataset.tester;
    const sortie = document.getElementById(`test-${mode}`);
    sortie.innerHTML = `<span class="chargement"></span> Test en cours...`;
    try {
      if (mode === "api") await enregistrer();
      const res = await api(`/api/reglages/tester?mode=${mode}`, { method: "POST" });
      sortie.textContent = (res.ok ? "✓ " : "✗ ") + res.message;
    } catch (err) { sortie.textContent = "✗ " + err.message; }
  });
}

// ---------- Édition ----------
async function vueEdition(id) {
  const r = id ? await api(`/api/recettes/${id}`) : { titre: "", portions: "", temps_preparation: "", temps_cuisson: "", ingredients: [], etapes: [], tags: [], notes: "" };
  const ingr = r.ingredients.length ? [...r.ingredients] : [{ quantite: "", unite: "", nom: "" }];
  const etapes = r.etapes.length ? [...r.etapes] : [""];

  vue.innerHTML = `
    <section class="bloc">
      <details id="d-json"><summary>${id ? "Mettre à jour avec un JSON Claude" : "Créer à partir d'un JSON Claude"}</summary>
        <p class="aide">${AIDE_JSON}</p>
        <textarea id="e-json" rows="8" placeholder='{"titre": "...", "ingredients": [...]}'></textarea>
        <div class="actions"><button class="principal" id="e-valider">${id ? "Mettre à jour la recette" : "Créer la recette"}</button></div>
      </details>
    </section>
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
  // Une quantité retouchée à la main n'est plus une estimation.
  const lireIngr = () => [...zoneIngr.children].map((l) => ({
    quantite: l.children[0].value, unite: l.children[1].value, nom: l.children[2].value,
    estimee: l.dataset.estimee === "1" && l.children[0].value === l.dataset.qte,
  }));
  const lireEtapes = () => [...zoneEtapes.children].map((l) => l.children[0].value);

  function dessiner() {
    zoneIngr.innerHTML = ingr.map((i, n) => `
      <div class="ligne-ingr" data-estimee="${i.estimee ? "1" : ""}" data-qte="${echap(i.quantite)}">
        <input value="${echap(i.quantite)}" placeholder="${i.estimee ? "≈ " : ""}Qté" aria-label="Quantité${i.estimee ? " estimée" : ""}" ${i.estimee ? 'class="estimee"' : ""}>
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

  document.getElementById("e-valider").onclick = async () => {
    const texte = document.getElementById("e-json").value;
    let nouvel = null;
    try {
      if (!texte.trim()) throw new Error("Colle d'abord le JSON de Claude.");
      const cible = id || (nouvel = await api("/api/recettes", { method: "POST", body: { titre: "Nouvelle recette" } })).id;
      await enregistrerJson(cible, texte);
      toast(id ? "Recette mise à jour." : "Recette créée.");
      location.hash = `#/recette/${cible}`;
    } catch (err) {
      if (nouvel) await api(`/api/recettes/${nouvel.id}`, { method: "DELETE" }).catch(() => {});
      toast(err.message);
    }
  };

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

// ---------- Menus de la semaine ----------
const JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"];
// Pas des plats pour un repas complet.
const HORS_MENU = /dessert|gâteau|gateau|boisson|cocktail|smoothie|sauce|apéro|apéritif|aperitif|goûter|gouter|biscuit|confiture|pâtisserie|patisserie/i;
// Ingrédients présents partout : ils ne disent rien du plat.
const BASIQUES = new Set(["sel", "poivre", "huile", "olive", "beurre", "eau", "ail", "oignon", "échalote", "sucre", "farine",
  "lait", "crème", "persil", "basilic", "thym", "laurier", "paprika", "cumin", "épices", "muscade", "vinaigre", "moutarde",
  "citron", "levure", "bouillon", "cube", "gousse", "pincée", "frais", "fraîche", "râpé", "râpée", "de", "du", "la", "le", "les", "à", "au", "aux", "et"]);

// Familles d'ingrédients principaux : deux plats de la même famille se ressemblent.
const FAMILLES = [
  ["pâtes", /p[âa]tes|spaghetti|penne|tagliatelle|linguine|fusilli|macaroni|lasagne|ravioli|gnocchi|nouille|coquillette/],
  ["riz", /\briz\b|risotto|paella/],
  ["poulet", /poulet|volaille|dinde|canard/],
  ["bœuf", /b(oe|œ)uf|steak|veau|hach[ée]/],
  ["porc", /porc|lardon|jambon|saucisse|chorizo|bacon/],
  ["poisson", /poisson|saumon|cabillaud|thon|colin|merlu|truite|crevette|moule|fruits de mer/],
  ["œufs", /\b(oe|œ)ufs?\b|omelette/],
  ["légumineuses", /lentille|pois chiche|haricot rouge|haricots rouges|f[èe]ve/],
  ["pâte à tarte", /p[âa]te bris[ée]e|p[âa]te feuillet[ée]e|tarte|quiche|pizza/],
  ["pommes de terre", /pommes? de terre|patate|frite/],
];

function motsCles(r) {
  const texte = (r.titre + " " + r.ingredients.slice(0, 5).map((i) => i.nom).join(" ")).toLowerCase();
  const familles = new Set(FAMILLES.filter(([, re]) => re.test(texte)).map(([nom]) => nom));
  const tags = new Set(r.tags.map((x) => x.toLowerCase()));
  const ingr = new Set();
  let gardes = 0;
  for (const i of r.ingredients) {
    const utiles = i.nom.toLowerCase().split(/[^a-zà-ÿœ]+/).filter((m) => m.length > 2 && !BASIQUES.has(m));
    if (!utiles.length) continue;
    utiles.forEach((m) => ingr.add(m.replace(/s$/, "")));
    if (++gardes >= 4) break;
  }
  return { familles, tags, ingr };
}
const communs = (a, b) => { let n = 0; for (const x of a) if (b.has(x)) n++; return n; };
function ressemblance(a, b) {
  return 0.7 * Math.min(1, communs(a.familles, b.familles)) + 0.25 * communs(a.tags, b.tags) + 0.1 * communs(a.ingr, b.ingr);
}

// Tire des plats au hasard en écartant ceux qui ressemblent trop à ceux déjà choisis.
// eviter : plats du tirage précédent, pénalisés pour varier d'une semaine à l'autre.
function tirerMenus(candidats, nombre, imposes = [], eviter = new Set()) {
  const choisis = [...imposes];
  const restants = candidats.filter((r) => !choisis.some((c) => c.id === r.id));
  while (choisis.length < nombre && restants.length) {
    const scores = restants.map((r) => {
      const proche = choisis.length ? Math.max(...choisis.map((c) => ressemblance(r._mots, c._mots))) : 0;
      return { r, score: proche + (eviter.has(r.id) ? 0.5 : 0) + Math.random() * 0.6 };
    });
    scores.sort((x, y) => x.score - y.score);
    choisis.push(scores[0].r);
    restants.splice(restants.indexOf(scores[0].r), 1);
  }
  return choisis;
}

async function vueMenus() {
  const toutes = (await api("/api/recettes")).filter((r) => r.statut === "pret" && r.ingredients.length);
  const plats = toutes.filter((r) => !HORS_MENU.test(r.tags.join(" ") + " " + r.titre));
  const candidats = (plats.length >= 5 ? plats : toutes).map((r) => ({ ...r, _mots: motsCles(r) }));
  const parId = new Map(candidats.map((r) => [r.id, r]));

  // Le menu en cours reste affiché d'une visite à l'autre.
  let menu = lireStock("menu-semaine", []).map((id) => parId.get(id)).filter(Boolean);
  const verrous = new Set(lireStock("menu-verrous", []));

  function generer(garder = []) {
    const imposes = menu.filter((r) => garder.includes(r.id));
    const tirage = tirerMenus(candidats, Math.min(5, candidats.length), imposes, new Set(menu.map((r) => r.id)));
    // Remet les plats gardés à leur jour d'origine.
    const resultat = new Array(tirage.length);
    menu.forEach((r, j) => { if (garder.includes(r.id) && j < resultat.length) resultat[j] = r; });
    const libres = tirage.filter((r) => !garder.includes(r.id));
    for (let j = 0; j < resultat.length; j++) if (!resultat[j]) resultat[j] = libres.shift();
    menu = resultat.filter(Boolean);
    ecrireStock("menu-semaine", menu.map((r) => r.id));
    dessiner();
  }

  function remplacer(jour) {
    const autres = menu.filter((_, j) => j !== jour);
    const options = candidats.filter((r) => !menu.some((m) => m.id === r.id));
    if (!options.length) { toast("Pas d'autre recette disponible."); return; }
    menu[jour] = tirerMenus(options, autres.length + 1, autres).pop();
    ecrireStock("menu-semaine", menu.map((r) => r.id));
    dessiner();
  }

  function dessiner() {
    if (candidats.length < 2) {
      vue.innerHTML = `<p class="vide">Il faut au moins 2 recettes rédigées pour composer des menus. Tu en as ${candidats.length}.</p>`;
      return;
    }
    vue.innerHTML = `
      <section class="bloc">
        <h2>Menus de la semaine</h2>
        <p class="aide">5 plats tirés au hasard parmi tes ${candidats.length} recettes, en évitant les plats trop proches. Les desserts, boissons et sauces sont écartés.${candidats.length < 5 ? " Ajoute des recettes pour remplir toute la semaine." : ""}</p>
        <div class="actions">
          <button class="principal" id="m-tirer">${menu.length ? "Nouveau tirage" : "Tirer 5 menus"}</button>
          ${menu.length ? `<button id="m-courses">🛒 Tout ajouter aux courses</button>` : ""}
        </div>
        ${menu.length ? `<p class="aide">🔒 garde un plat au prochain tirage. ↻ change seulement ce jour.</p>` : ""}
      </section>
      ${menu.map((r, j) => `
        <article class="jour">
          <a href="#/recette/${r.id}"><img src="${imageRecette(r)}" alt="" loading="lazy"></a>
          <div class="jour-infos">
            <div class="aide">${JOURS[j]}</div>
            <a href="#/recette/${r.id}"><strong>${echap(r.titre)}</strong></a>
            <div class="aide">${echap([r.temps_preparation && "⏱ " + r.temps_preparation, r.tags.slice(0, 3).join(", ")].filter(Boolean).join(" · "))}</div>
          </div>
          <div class="jour-actions">
            <button data-verrou="${r.id}" aria-label="Garder ce plat" class="${verrous.has(r.id) ? "principal" : ""}">🔒</button>
            <button data-changer="${j}" aria-label="Changer ce plat">↻</button>
          </div>
        </article>`).join("")}`;

    document.getElementById("m-tirer").onclick = () => generer([...verrous].filter((id) => menu.some((r) => r.id === id)));
    const courses = document.getElementById("m-courses");
    if (courses) courses.onclick = () => {
      const p = panier();
      for (const r of menu) {
        if (p.some((x) => x.id === r.id)) continue;
        const base = nombrePortions(r.portions);
        p.push({ id: r.id, facteur: base ? (etat.portions_defaut || base) / base : 1 });
      }
      ecrireStock("courses", p);
      majCompteur();
      toast(`Ingrédients des ${menu.length} plats ajoutés, pour ${etat.portions_defaut || 4} personnes.`);
    };
    vue.querySelectorAll("[data-changer]").forEach((b) => b.onclick = () => remplacer(+b.dataset.changer));
    vue.querySelectorAll("[data-verrou]").forEach((b) => b.onclick = () => {
      const id = +b.dataset.verrou;
      verrous.has(id) ? verrous.delete(id) : verrous.add(id);
      ecrireStock("menu-verrous", [...verrous]);
      dessiner();
    });
  }

  if (!menu.length && candidats.length >= 2) generer();
  else dessiner();
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
      const l = lignes.get(cle) || { nom: i.nom.trim(), unite: i.unite, total: 0, autres: [], estimee: false };
      if (i.estimee && i.quantite) l.estimee = true;
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
            <span class="qte">${l.estimee && qte ? "≈ " : ""}${echap([qte, l.unite].filter(Boolean).join(" "))}</span><span>${echap(l.nom)}</span></label></li>`;
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
    const texte = triees.map(([, l]) => `- ${l.estimee ? "≈" : ""}${[l.total ? formater(l.total) : "", ...l.autres].filter(Boolean).join(" + ")} ${l.unite || ""} ${l.nom}`.replace(/\s+/g, " ").trim()).join("\n");
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
    else if (h === "#/reglages") await vueReglages();
    else if (h === "#/menus") await vueMenus();
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
