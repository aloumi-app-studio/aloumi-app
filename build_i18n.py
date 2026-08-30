#!/usr/bin/env python3
"""Génère le site multilingue SEO/GEO-friendly : une page HTML statique PRÉ-RENDUE
par langue, contenu 100 % dans le HTML brut (aucune traduction par JS au runtime).

Sortie (chemins propres par langue, GÉNÉRÉS — jamais hand-maintenus) :
  /fr/  /en/  (/de/ …)   landing
  /                      routeur : hreflang statique (découverte crawler) + redirection JS (commodité user)

Source (hand-maintenue, UN seul endroit) :
  _landing.html          template du landing (contenu FR de base + dico I18N + data-i18n)
  META (ci-dessous)      métadonnées <head> par langue (title/description/OG/JSON-LD)

Rendu = Chrome headless --dump-dom sur _landing.html?lang=XX (réutilise le dico I18N runtime
pour appliquer les traductions du corps), puis post-traitement : <head> SEO par langue,
switcher runtime → vrais liens <a>, chemins root-absolute, script i18n retiré (le contenu
est déjà figé). Idempotent, re-runnable. Ajouter une langue = l'ajouter à LANGS + META.

Prérequis : Chrome + Python 3 (aucune lib externe). Lancer : python build_i18n.py
"""
import datetime, json, os, re, subprocess, sys
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
from threading import Thread
import pathlib

SITE = pathlib.Path(__file__).parent
BASE = "https://aloumi.app"
PLAY = "https://play.google.com/store/apps/details?id=com.aloumi.app"
sys.path.insert(0, str((SITE / ".." / "store").resolve()))
import i18n_loader as i18n  # noqa: E402  (chemin posé juste au-dessus)
# LANGS vient de la SSOT vitrine (i18n_loader, qui lit store/i18n/langs.json) — le module est
# IMPORTÉ, pas re-lu : le bloc de chargement était lui aussi recopié ici et dans build_screens.py.
LANGS = i18n.LANGS               # ordre = ordre d'affichage dans le sélecteur de langue
LANG_LABEL = {"fr": "Français", "en": "English", "de": "Deutsch", "it": "Italiano", "es": "Español"}
OG_LOCALE = {"fr": "fr_FR", "en": "en_US", "de": "de_DE", "it": "it_IT", "es": "es_ES"}
X_DEFAULT = "fr"               # langue du hreflang x-default (marché principal)
TEMPLATE = "_src/landing.html"   # template source (hors pages servies, disallow robots)
LEGAL = {                        # slug unifié -> source bilingue (blocs data-lang)
    "privacy": "_src/privacy.html",
    "terms": "_src/terms.html",
    "legal-notice": "_src/legal-notice.html",
}
LEGAL_FREQ = {"privacy": "monthly", "terms": "monthly", "legal-notice": "yearly"}

CHROME = next((p for p in [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
] if os.path.exists(p)), None)
assert CHROME, "Chrome introuvable — ajuste le chemin"

# ── Métadonnées <head> par langue (SEO/GEO — traduites au SENS, pas mot à mot) ────────────
META = {
    "fr": {
        "title": "Aloumi — Tes recettes adaptées à ta cuisine, avec un chef IA",
        "desc": "Aloumi importe tes recettes (lien, photo, PDF, Instagram, TikTok, YouTube) et les adapte à ton four et ta plaque. Assistant cuisine IA pas à pas, sur Google Play.",
        "ogdesc": "Importe tes recettes (lien, photo, PDF, Instagram, TikTok, YouTube) et laisse le Chef IA les adapter à ton four et ta plaque. Sur Google Play.",
        "appdesc": "App de recettes boostée à l'IA : importe depuis un lien, une photo, un PDF, Instagram, TikTok ou YouTube, adapte les recettes à ton four et ta plaque, guide pas à pas et gère la liste de courses.",
        "features": [
            "Import de recettes depuis un lien, du texte, une photo, un PDF, Instagram, TikTok et YouTube",
            "Adaptation des recettes à l'équipement de cuisine (four, plaque, air fryer, robots)",
            "Modification d'une recette existante à la demande en langage naturel (végétarien, sans four, moins salé), avec aperçu des changements et conservation de l'originale",
            "Assistant IA culinaire contextuel",
            "Mode cuisine pas à pas avec minuteurs par étape",
            "Liste de courses avec catégorisation automatique par rayon",
            "Partage de recettes, courses et bonnes adresses en temps réel",
        ],
        "faq": [
            ("Aloumi est-elle gratuite ?", "Oui. Aloumi est disponible gratuitement sur Google Play pendant sa phase de test ouvert."),
            ("Peut-on importer une recette depuis Instagram, TikTok ou YouTube ?", "Oui. Colle le lien ou partage la publication vers Aloumi : le Chef IA récupère la recette et la structure automatiquement, y compris depuis une vidéo."),
            ("Aloumi adapte-t-elle les recettes à mon four et ma plaque ?", "Oui. Tu configures ton équipement (four, plaque, air fryer, robots) une fois, et Aloumi adapte les étapes de cuisson à ton matériel réel."),
            ("Puis-je demander une modification sur une recette que j'ai déjà ?", "Oui. Sur n'importe quelle recette de ton carnet, demande au Chef IA en langage naturel : « rends-la végé », « sans four », « moins salée ». Il te montre d'abord ce qui changerait, tu appliques d'un tap, et tu peux annuler. Les ingrédients que tu n'as pas mentionnés ne sont jamais modifiés, et tu peux garder l'originale à côté de la nouvelle version."),
            ("Peut-on importer une recette depuis une photo ou un PDF ?", "Oui. Photographie une recette manuscrite ou une page de livre, ou importe un PDF : Aloumi en extrait les ingrédients et les étapes."),
            ("Sur quelles plateformes Aloumi est-elle disponible ?", "Aloumi est disponible sur Android via Google Play. Une version iOS est à l'étude."),
            ("Comment fonctionne le mode cuisine ?", "Le mode cuisine affiche la recette étape par étape, avec des minuteurs par étape, le rappel des ingrédients et un assistant IA qui connaît la recette en cours."),
            ("Pourquoi adapter une recette à ma cuisine ?", "Chaque équipement cuit différemment : un four, une plaque à induction, un air fryer ou un robot n'ont ni la même puissance ni les mêmes réglages d'un modèle à l'autre. Une recette écrite pour un autre matériel peut rater chez toi. Aloumi réécrit temps, températures et réglages pour ton équipement réel — pour réussir du premier coup."),
        ],
    },
    "en": {
        "title": "Aloumi — Your recipes, adapted to your kitchen, with an AI chef",
        "desc": "Aloumi imports your recipes (link, photo, PDF, Instagram, TikTok, YouTube) and adapts them to your oven and cooktop. Step-by-step AI cooking assistant, on Google Play.",
        "ogdesc": "Import your recipes (link, photo, PDF, Instagram, TikTok, YouTube) and let the AI Chef adapt them to your oven and cooktop. On Google Play.",
        "appdesc": "AI-powered recipe app: import from a link, a photo, a PDF, Instagram, TikTok or YouTube, adapt recipes to your oven and cooktop, cook step by step and manage your shopping list.",
        "features": [
            "Recipe import from a link, text, a photo, a PDF, Instagram, TikTok and YouTube",
            "Recipe adaptation to your kitchen equipment (oven, cooktop, food processors, air fryer)",
            "On-request editing of an existing recipe in plain language (vegetarian, no oven, less salt), with a preview of the changes and the original kept",
            "Contextual AI cooking assistant",
            "Step-by-step cooking mode with per-step timers",
            "Shopping list with automatic sorting by aisle",
            "Real-time sharing of recipes, shopping lists and food finds",
        ],
        "faq": [
            ("Is Aloumi free?", "Yes. Aloumi is available for free on Google Play during its open testing phase."),
            ("Can I import a recipe from Instagram, TikTok or YouTube?", "Yes. Paste the link or share the post to Aloumi: the AI Chef fetches the recipe and structures it automatically, even from a video."),
            ("Does Aloumi adapt recipes to my oven and cooktop?", "Yes. Set up your equipment (oven, cooktop, food processors, air fryer) once, and Aloumi adapts the cooking steps to your actual gear."),
            ("Can I ask for changes to a recipe I already have?", "Yes. On any recipe in your collection, ask the AI Chef in plain language: \"make it vegetarian\", \"no oven\", \"less salt\". It shows you what would change first, you apply it with one tap, and you can undo. Ingredients you didn't mention are never modified, and you can keep the original alongside the new version."),
            ("Can I import a recipe from a photo or PDF?", "Yes. Snap a handwritten recipe or a cookbook page, or import a PDF: Aloumi extracts the ingredients and steps."),
            ("Which platforms is Aloumi available on?", "Aloumi is available on Android via Google Play. An iOS version is under consideration."),
            ("How does cooking mode work?", "Cooking mode shows the recipe step by step, with per-step timers, ingredient reminders and an AI assistant that knows the current recipe."),
            ("Why adapt a recipe to my kitchen?", "Every appliance cooks differently: an oven, an induction cooktop, an air fryer or a food processor don't share the same power or settings from one model to the next. A recipe written for other equipment can flop in your kitchen. Aloumi rewrites times, temperatures and settings for your actual gear — so it comes out right the first time."),
        ],
    },
    "de": {
        "title": "Aloumi — Deine Rezepte, angepasst an deine Küche, mit KI-Koch",
        "desc": "Aloumi importiert deine Rezepte (Link, Foto, PDF, Instagram, TikTok, YouTube) und passt sie an deinen Backofen und dein Kochfeld an. Schritt-für-Schritt-Kochassistent mit KI, bei Google Play.",
        "ogdesc": "Importiere deine Rezepte (Link, Foto, PDF, Instagram, TikTok, YouTube) und lass den KI-Koch sie an deinen Backofen und dein Kochfeld anpassen. Bei Google Play.",
        "appdesc": "Rezept-App mit KI: importiere aus einem Link, einem Foto, einem PDF, Instagram, TikTok oder YouTube, passe Rezepte an deinen Backofen und dein Kochfeld an, koche Schritt für Schritt und verwalte deine Einkaufsliste.",
        "features": [
            "Rezeptimport aus Link, Text, Foto, PDF, Instagram, TikTok und YouTube",
            "Anpassung der Rezepte an deine Küchengeräte (Backofen, Kochfeld, Heißluftfritteuse, Küchenmaschinen)",
            "Bestehende Rezepte auf Zuruf ändern, in normaler Sprache (vegetarisch, ohne Backofen, weniger Salz) — mit Vorschau der Änderungen und Erhalt des Originals",
            "Kontextbezogener KI-Kochassistent",
            "Schritt-für-Schritt-Kochmodus mit Timern pro Schritt",
            "Einkaufsliste mit automatischer Sortierung nach Warengruppen",
            "Rezepte, Einkaufslisten und Feinkost-Tipps in Echtzeit teilen",
        ],
        "faq": [
            ("Ist Aloumi kostenlos?", "Ja. Aloumi ist während der offenen Testphase kostenlos bei Google Play verfügbar."),
            ("Kann ich ein Rezept von Instagram, TikTok oder YouTube importieren?", "Ja. Füge den Link ein oder teile den Beitrag mit Aloumi: Der KI-Koch holt das Rezept und strukturiert es automatisch — auch aus einem Video."),
            ("Passt Aloumi Rezepte an meinen Backofen und mein Kochfeld an?", "Ja. Du richtest deine Geräte einmal ein (Backofen, Kochfeld, Heißluftfritteuse, Küchenmaschinen), und Aloumi passt die Garschritte an deine tatsächliche Ausstattung an."),
            ("Kann ich ein Rezept ändern lassen, das ich schon habe?", "Ja. Bei jedem Rezept in deiner Sammlung fragst du den KI-Koch in normaler Sprache: „mach es vegetarisch“, „ohne Backofen“, „weniger Salz“. Er zeigt dir zuerst, was sich ändern würde, du übernimmst es mit einem Tippen und kannst es rückgängig machen. Zutaten, die du nicht genannt hast, werden nie verändert, und du kannst das Original neben der neuen Version behalten."),
            ("Kann ich ein Rezept aus einem Foto oder PDF importieren?", "Ja. Fotografiere ein handschriftliches Rezept oder eine Kochbuchseite, oder importiere ein PDF: Aloumi liest Zutaten und Schritte heraus."),
            ("Auf welchen Plattformen gibt es Aloumi?", "Aloumi gibt es für Android bei Google Play. Eine iOS-Version wird geprüft."),
            ("Wie funktioniert der Kochmodus?", "Der Kochmodus zeigt das Rezept Schritt für Schritt, mit Timern pro Schritt, den Zutaten zum jeweiligen Schritt und einem KI-Assistenten, der das laufende Rezept kennt."),
            ("Warum ein Rezept an meine Küche anpassen?", "Jedes Gerät gart anders: Backofen, Induktionskochfeld, Heißluftfritteuse oder Küchenmaschine haben von Modell zu Modell weder dieselbe Leistung noch dieselben Einstellungen. Ein Rezept, das für andere Geräte geschrieben wurde, kann bei dir misslingen. Aloumi schreibt Zeiten, Temperaturen und Einstellungen für deine tatsächliche Ausstattung um — damit es gleich beim ersten Mal gelingt."),
        ],
    },
    "it": {
        "title": "Aloumi — Le tue ricette adattate alla tua cucina, con uno chef IA",
        "desc": "Aloumi importa le tue ricette (link, foto, PDF, Instagram, TikTok, YouTube) e le adatta al tuo forno e al tuo piano cottura. Assistente di cucina IA passo dopo passo, su Google Play.",
        "ogdesc": "Importa le tue ricette (link, foto, PDF, Instagram, TikTok, YouTube) e lascia che il Chef IA le adatti al tuo forno e al tuo piano cottura. Su Google Play.",
        "appdesc": "App di ricette con IA: importa da un link, una foto, un PDF, Instagram, TikTok o YouTube, adatta le ricette al tuo forno e al tuo piano cottura, cucina passo dopo passo e gestisci la lista della spesa.",
        "features": [
            "Importazione di ricette da link, testo, foto, PDF, Instagram, TikTok e YouTube",
            "Adattamento delle ricette alla tua attrezzatura (forno, piano cottura, friggitrice ad aria, robot da cucina)",
            "Modifica di una ricetta che hai già, chiesta in linguaggio naturale (vegetariana, senza forno, meno salata), con anteprima delle modifiche e originale conservato",
            "Assistente di cucina IA che conosce la ricetta in corso",
            "Modalità cucina passo dopo passo con timer per ogni passaggio",
            "Lista della spesa ordinata automaticamente per reparto",
            "Condivisione in tempo reale di ricette, liste della spesa e chicche golose",
        ],
        "faq": [
            ("Aloumi è gratuita?", "Sì. Aloumi è disponibile gratuitamente su Google Play durante la fase di test aperto."),
            ("Posso importare una ricetta da Instagram, TikTok o YouTube?", "Sì. Incolla il link o condividi il post con Aloumi: il Chef IA recupera la ricetta e la struttura in automatico, anche da un video."),
            ("Aloumi adatta le ricette al mio forno e al mio piano cottura?", "Sì. Configuri la tua attrezzatura una volta sola (forno, piano cottura, friggitrice ad aria, robot da cucina) e Aloumi adatta i passaggi di cottura a quello che hai davvero."),
            ("Posso chiedere una modifica su una ricetta che ho già?", "Sì. Su qualsiasi ricetta del tuo ricettario, chiedi al Chef IA in linguaggio naturale: «rendila vegetariana», «senza forno», «meno salata». Prima ti mostra cosa cambierebbe, poi applichi con un tocco e puoi annullare. Gli ingredienti che non hai nominato non vengono mai modificati, e puoi tenere l'originale accanto alla nuova versione."),
            ("Posso importare una ricetta da una foto o da un PDF?", "Sì. Fotografa una ricetta scritta a mano o la pagina di un libro, oppure importa un PDF: Aloumi ne estrae ingredienti e passaggi."),
            ("Su quali piattaforme è disponibile Aloumi?", "Aloumi è disponibile su Android tramite Google Play. Una versione iOS è allo studio."),
            ("Come funziona la modalità cucina?", "La modalità cucina mostra la ricetta passo dopo passo, con timer per ogni passaggio, il richiamo degli ingredienti e un assistente IA che conosce la ricetta in corso."),
            ("Perché adattare una ricetta alla mia cucina?", "Ogni apparecchio cuoce in modo diverso: un forno, un piano a induzione, una friggitrice ad aria o un robot da cucina non hanno né la stessa potenza né le stesse regolazioni da un modello all'altro. Una ricetta scritta per un'altra attrezzatura può non riuscire a casa tua. Aloumi riscrive tempi, temperature e regolazioni per quello che hai davvero — così riesce al primo colpo."),
        ],
    },
    "es": {
        "title": "Aloumi — Tus recetas adaptadas a tu cocina, con un chef IA",
        "desc": "Aloumi importa tus recetas (enlace, foto, PDF, Instagram, TikTok, YouTube) y las adapta a tu horno y a tu placa. Asistente de cocina con IA paso a paso, en Google Play.",
        "ogdesc": "Importa tus recetas (enlace, foto, PDF, Instagram, TikTok, YouTube) y deja que el Chef IA las adapte a tu horno y a tu placa. En Google Play.",
        "appdesc": "App de recetas con IA: importa desde un enlace, una foto, un PDF, Instagram, TikTok o YouTube, adapta las recetas a tu horno y a tu placa, cocina paso a paso y gestiona la lista de la compra.",
        "features": [
            "Importación de recetas desde un enlace, texto, foto, PDF, Instagram, TikTok y YouTube",
            "Adaptación de las recetas a tu equipamiento (horno, placa, freidora de aire, robot de cocina)",
            "Cambios en una receta que ya tienes, pedidos en lenguaje natural (vegetariana, sin horno, menos salada), con vista previa de los cambios y la original conservada",
            "Asistente de cocina con IA que conoce la receta en curso",
            "Modo cocina paso a paso con temporizador para cada paso",
            "Lista de la compra ordenada automáticamente por secciones",
            "Uso compartido en tiempo real de recetas, listas de la compra y joyas gastronómicas",
        ],
        "faq": [
            ("¿Aloumi es gratis?", "Sí. Aloumi está disponible gratis en Google Play durante la fase de prueba abierta."),
            ("¿Puedo importar una receta de Instagram, TikTok o YouTube?", "Sí. Pega el enlace o comparte la publicación con Aloumi: el Chef IA recupera la receta y la estructura automáticamente, incluso desde un vídeo."),
            ("¿Aloumi adapta las recetas a mi horno y a mi placa?", "Sí. Configuras tu equipamiento una sola vez (horno, placa, freidora de aire, robot de cocina) y Aloumi adapta los pasos de cocción a lo que tienes de verdad."),
            ("¿Puedo pedir un cambio en una receta que ya tengo?", "Sí. En cualquier receta de tu recetario, pídeselo al Chef IA en lenguaje natural: «hazla vegetariana», «sin horno», «menos salada». Primero te enseña lo que cambiaría, luego lo aplicas con un toque y puedes deshacerlo. Los ingredientes que no has nombrado nunca se tocan, y puedes quedarte con la original junto a la nueva versión."),
            ("¿Puedo importar una receta desde una foto o un PDF?", "Sí. Fotografía una receta escrita a mano o la página de un libro, o importa un PDF: Aloumi extrae los ingredientes y los pasos."),
            ("¿En qué plataformas está disponible Aloumi?", "Aloumi está disponible en Android a través de Google Play. Una versión para iOS está en estudio."),
            ("¿Cómo funciona el modo cocina?", "El modo cocina muestra la receta paso a paso, con temporizadores para cada paso, el recordatorio de los ingredientes y un asistente de IA que conoce la receta en curso."),
            ("¿Por qué adaptar una receta a mi cocina?", "Cada aparato cocina de una forma distinta: un horno, una placa de inducción, una freidora de aire o un robot de cocina no tienen ni la misma potencia ni los mismos ajustes de un modelo a otro. Una receta escrita para otro equipamiento puede no salir en tu casa. Aloumi reescribe tiempos, temperaturas y ajustes para lo que tienes de verdad — así sale a la primera."),
        ],
    },
}

# Réécriture des liens de page internes vers la nouvelle taxonomie par langue.
PAGE_LINKS = {  # ancien href du template -> slug de destination (préfixé /{lang}/ au build)
    "index.html": "",
    "privacy.html": "privacy/",
    "terms.html": "terms/",
    "mentions-legales.html": "legal-notice/",
}

# Langues qui ont RÉELLEMENT un texte légal (blocs `data-lang` dans `_src/privacy.html` etc.).
# ⚠️ Le juridique n'est PAS traduit par la chaîne i18n : c'est du contenu contractuel/réglementaire,
# une traduction approximative y a des conséquences. Tant qu'une langue n'a pas ses blocs, ses pages
# renvoient vers [LEGAL_FALLBACK] — un lien honnête vers une page qui existe, jamais un 404 (l'URL de
# politique de confidentialité est EXIGÉE par Google Play) ni une fausse URL /de/privacy/ vide.
LEGAL_FALLBACK = "en"


def _legal_langs():
    """Langues réellement couvertes par les sources légales — lu dans les fichiers, pas déclaré.

    ⚠️ INTERSECTION des TROIS sources, jamais la seule `privacy`. `LEGAL_LANGS` gouverne les trois
    slugs à la fois (hreflang + sitemap + liens de pied de page) : une langue traduite dans
    `privacy.html` mais pas encore dans `terms.html` serait annoncée pour /terms/ alors que
    `build_legal()` ne génère pas ce fichier — hreflang et sitemap pointeraient vers un 404.
    Avec l'intersection, une traduction légale partielle dégrade proprement (toute la langue
    reste sur [LEGAL_FALLBACK]) au lieu de publier un lien mort.
    """
    per_page = [
        set(re.findall(r'<div class="langblock" data-lang="([a-z]{2})"',
                       (SITE / src).read_text(encoding="utf-8")))
        for src in LEGAL.values()
    ]
    return set.intersection(*per_page) if per_page else set()


LEGAL_LANGS = _legal_langs()


def legal_href(lang, dst):
    """Préfixe de langue d'un lien de page : la langue elle-même si elle a du légal, sinon le repli."""
    if dst and lang not in LEGAL_LANGS:
        return f"/{LEGAL_FALLBACK}/{dst}"
    return f"/{lang}/{dst}"

# Confort du sélecteur de langue — CONFORT SEULEMENT : `<details>` ouvre/ferme, navigue et se pilote
# au clavier sans une ligne de JS. Ceci n'ajoute que ce que le natif ne fait pas (fermer au clic
# extérieur et à Échap). Si le script ne charge pas, le sélecteur reste pleinement utilisable.
LANGSEL_JS = ("<script>(function(){var s=document.querySelector('.langsel');if(!s)return;"
              "document.addEventListener('click',function(e){"
              "if(s.open&&!s.contains(e.target))s.open=false;});"
              "document.addEventListener('keydown',function(e){"
              "if(e.key==='Escape'&&s.open){s.open=false;s.querySelector('summary').focus();}});"
              "})();</script>")

REVEAL_JS = """<script>
  const hdr = document.getElementById('hdr');
  const onScroll = () => hdr && hdr.classList.toggle('scrolled', window.scrollY > 8);
  onScroll(); addEventListener('scroll', onScroll, { passive:true });
  const io = new IntersectionObserver((es) => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { threshold:.12 });
  document.querySelectorAll('.reveal').forEach((el,i) => { el.style.transitionDelay = (Math.min(i,6)*60)+'ms'; io.observe(el); });
</script>""" + LANGSEL_JS

# ── Chrome partagé (header + footer) des pages légales ────────────────────────────────────
# THÉMING PARTAGÉ AVEC LA LANDING (SSOT = _src/landing.html) : les pages légales réutilisent le
# design system COMPLET de la landing — LANDING_STYLE (tokens light+dark, base, header .nav sticky,
# footer grid riche, responsive) est extrait tel quel du <style> de la landing, puis LEGAL_CSS
# n'ajoute QUE la colonne de lecture + la typo du corps légal, rebasée sur les mêmes variables
# (--ink/--accent/--muted/--line/--surface). Le logo (symbole SVG) et le footer (markup traduit par
# langue) sont déjà extraits de la landing → header/footer strictement identiques à la home.
LOGO_SVG = re.search(r'<svg[^>]*>\s*<symbol id="aloumi-logo".*?</symbol>\s*</svg>',
                     (SITE / TEMPLATE).read_text(encoding="utf-8"), re.S).group(0)

# CSS du design system de la landing (tokens, base, header, footer, dark mode) — SSOT.
LANDING_STYLE = re.search(r"<style>(.*?)</style>",
                          (SITE / TEMPLATE).read_text(encoding="utf-8"), re.S).group(1)

PLAY_LABEL = {"fr": "Sur Google Play", "en": "On Google Play", "de": "Bei Google Play", "it": "Su Google Play", "es": "En Google Play"}

# ── Sélecteur de langue (header) ────────────────────────────────────────────────────────────────
# `<details>` NATIF, pas un composant JS : le site est statique (GitHub Pages), donc les liens
# doivent rester de vrais <a href> crawlables et la page utilisable sans JS. Le natif fournit en
# prime le clavier et l'ARIA. Remplace la rangée de liens à plat (illisible à 5 langues, et qui ne
# disait pas laquelle était active) ET le bouton qui CYCLAIT vers la suivante (jusqu'à 4 taps).
LANG_WORD = {"fr": "Langue", "en": "Language", "de": "Sprache", "it": "Lingua", "es": "Idioma"}
_GLOBE = ('<svg class="globe" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
          'aria-hidden="true"><circle cx="12" cy="12" r="9"/>'
          '<path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></svg>')
_CHEV = ('<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" '
         'aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>')


def lang_selector(current, href):
    """Sélecteur du header pour `current`. `href(lang)` donne l'URL de la MÊME page dans `lang`.

    ⚠️ Toutes les langues sont listées, mais l'URL passe par l'appelant : sur une page légale il
    doit utiliser `legal_href`, qui replie sur [LEGAL_FALLBACK] tant que le texte n'est pas traduit.
    L'ancienne version fabriquait `/{l}/{slug}/` en dur — un 404 en attente pour toute langue dont
    le juridique n'aurait pas encore été écrit.
    """
    items = "".join(
        '<a href="%s" lang="%s" hreflang="%s"%s>%s</a>'
        % (href(l), l, l, ' aria-current="true"' if l == current else "", LANG_LABEL[l])
        for l in LANGS)
    return (
        '<details class="langsel"><summary aria-label="%s">%s'
        '<span class="langsel-full">%s</span><span class="langsel-code">%s</span>%s</summary>'
        '<div class="langsel-menu">%s</div></details>'
        % (LANG_WORD[current], _GLOBE, LANG_LABEL[current], current.upper(), _CHEV, items))

# Spécifique aux pages légales : colonne de lecture étroite + typo du corps, sur les tokens landing.
# `.legal .wrap` (plus spécifique que `.wrap`) rétrécit UNIQUEMENT le contenu ; header/footer gardent
# le `.wrap` pleine largeur de la landing (--maxw) → chrome pixel-identique à la home.
LEGAL_CSS = """
  main.legal .wrap { max-width: 768px; padding: 56px 24px 76px; }
  main.legal h1 { font-size: 2.1rem; letter-spacing: -.02em; margin-bottom: 6px; }
  main.legal .updated { color: var(--muted); font-size: .92rem; margin-bottom: 6px; }
  main.legal h2 { font-family: var(--display); font-size: 1.35rem; font-weight: 800; color: var(--accent); margin: 36px 0 12px; }
  main.legal p, main.legal li { margin-bottom: 9px; }
  main.legal ul { padding-left: 20px; margin-bottom: 14px; }
  main.legal a { color: var(--accent); font-weight: 600; }
  main.legal a:hover { color: var(--accent-ink); }
  main.legal .warn { background: color-mix(in srgb, var(--accent-soft) 14%, var(--surface)); border: 1px solid var(--line); border-radius: 16px; padding: 18px 20px; margin: 18px 0; }
  main.legal .table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 14px 0; }
  main.legal table { border-collapse: collapse; width: 100%; min-width: 620px; font-size: .94rem; }
  main.legal th, main.legal td { border: 1px solid var(--line); padding: 9px 12px; text-align: left; vertical-align: top; }
  main.legal th { background: var(--surface-2); }
  @media (max-width: 600px) {
    main.legal .wrap { padding: 40px 16px 60px; }
    main.legal table { font-size: .85rem; }
    main.legal th, main.legal td { padding: 7px 9px; }
  }
"""

HDR_SCROLL_JS = ("<script>var h=document.getElementById('hdr');"
                 "var s=function(){h&&h.classList.toggle('scrolled',scrollY>8)};"
                 "s();addEventListener('scroll',s,{passive:true});</script>" + LANGSEL_JS)


def jsonld(lang):
    m = META[lang]
    graph = [
        {"@type": "Organization", "@id": BASE + "/#org", "name": "JEYLAB", "url": BASE + "/",
         "logo": BASE + "/icon-512.png", "email": "aloumiapp@gmail.com",
         "brand": {"@type": "Brand", "name": "Aloumi"}},
        {"@type": "WebSite", "@id": BASE + "/#website", "name": "Aloumi",
         "url": f"{BASE}/{lang}/", "inLanguage": lang, "publisher": {"@id": BASE + "/#org"}},
        {"@type": "MobileApplication", "@id": BASE + "/#app", "name": "Aloumi",
         "operatingSystem": "Android 8.0+", "applicationCategory": "LifestyleApplication",
         "url": f"{BASE}/{lang}/", "downloadUrl": PLAY, "installUrl": PLAY,
         "inLanguage": list(LANGS), "description": m["appdesc"],
         "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"},
         "featureList": m["features"], "publisher": {"@id": BASE + "/#org"}},
        {"@type": "FAQPage", "@id": BASE + "/#faq",
         "mainEntity": [{"@type": "Question", "name": q,
                         "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in m["faq"]]},
    ]
    return json.dumps({"@context": "https://schema.org", "@graph": graph},
                      ensure_ascii=False, indent=2)


def langs_for(page=""):
    """Langues où CETTE page existe réellement — jamais `LANGS` en aveugle.

    ⚠️ Le landing existe dans toutes les langues, mais le LÉGAL n'existe que là où le texte a été
    écrit (`LEGAL_LANGS`). Boucler sur `LANGS` partout produisait trois défauts d'un coup :
    le routeur `/privacy/` (l'URL donnée à Google Play, qui négocie la langue du navigateur)
    redirigeait un Allemand vers un **404** ; les `hreflang` déclaraient des pages inexistantes ;
    le sitemap les soumettait à Search Console. Trouvé le 29/07/2026.
    """
    slug = page.rstrip("/")
    if slug in LEGAL:
        return [l for l in LANGS if l in LEGAL_LANGS]
    return LANGS


def default_for(page=""):
    """Langue du `x-default` (et du repli sans JS) pour CETTE page.

    Page disponible partout (le landing) → politique du site (`X_DEFAULT`, le marché principal).
    Page à couverture PARTIELLE (le légal) → `LEGAL_FALLBACK` (anglais) : c'est la langue qui sera
    servie à un visiteur dont la langue n'existe pas encore (allemand, italien…), et l'anglais lui
    est plus lisible que le français. Le visiteur francophone, lui, est de toute façon apparié
    directement sur `/fr/` par la négociation — ce repli ne le concerne pas.
    """
    avail = langs_for(page)
    if avail == LANGS:
        return X_DEFAULT
    return LEGAL_FALLBACK if LEGAL_FALLBACK in avail else avail[0]


def hreflang_block(page=""):
    """page = '' pour le landing, 'privacy/' etc. pour le légal."""
    lines = [f'<link rel="alternate" hreflang="{l}" href="{BASE}/{l}/{page}">' for l in langs_for(page)]
    lines.append(f'<link rel="alternate" hreflang="x-default" href="{BASE}/{default_for(page)}/{page}">')
    return "\n".join(lines)


def esc(s):
    return s.replace("&", "&amp;").replace('"', "&quot;")


def render_lang(url, lang):
    """Chrome --dump-dom : rend _landing.html?lang=XX et renvoie le DOM (corps traduit)."""
    out = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
         "--virtual-time-budget=4000", "--dump-dom", f"{url}?lang={lang}"],
        capture_output=True, text=True, encoding="utf-8", timeout=60)
    dom = out.stdout
    if "<html" not in dom:
        sys.exit(f"[build] dump-dom vide pour {lang} :\n{out.stderr[:500]}")
    return dom


def post_process_landing(dom, lang):
    h = dom
    m = META[lang]
    # 1) <html lang>
    h = re.sub(r'<html[^>]*>', f'<html lang="{lang}">', h, count=1)
    # 2) <head> — remplacements ciblés par attribut (robuste au réordonnancement Chrome)
    h = re.sub(r'<title>.*?</title>', f'<title>{m["title"]}</title>', h, flags=re.S)
    h = re.sub(r'<meta[^>]*name="description"[^>]*>',
               f'<meta name="description" content="{esc(m["desc"])}">', h)
    h = re.sub(r'<meta[^>]*name="robots"[^>]*>',
               '<meta name="robots" content="index,follow,max-image-preview:large">', h)
    h = re.sub(r'<meta[^>]*property="og:title"[^>]*>',
               f'<meta property="og:title" content="{esc(m["title"])}">', h)
    h = re.sub(r'<meta[^>]*property="og:description"[^>]*>',
               f'<meta property="og:description" content="{esc(m["ogdesc"])}">', h)
    h = re.sub(r'<meta[^>]*property="og:url"[^>]*>',
               f'<meta property="og:url" content="{BASE}/{lang}/">', h)
    h = re.sub(r'<meta[^>]*property="og:locale"(?![:])[^>]*>',
               f'<meta property="og:locale" content="{OG_LOCALE[lang]}">', h)
    alt = [OG_LOCALE[l] for l in LANGS if l != lang]
    h = re.sub(r'<meta[^>]*property="og:locale:alternate"[^>]*>',
               "\n".join(f'<meta property="og:locale:alternate" content="{a}">' for a in alt), h)
    h = re.sub(r'<meta[^>]*name="twitter:title"[^>]*>',
               f'<meta name="twitter:title" content="{esc(m["title"])}">', h)
    h = re.sub(r'<meta[^>]*name="twitter:description"[^>]*>',
               f'<meta name="twitter:description" content="{esc(m["ogdesc"])}">', h)
    # La carte de partage est la SEULE surface du site où l'image porte du TEXTE : « Aloumi »,
    # le slogan et la phrase de résumé y sont DESSINÉS. Elle se localise donc comme un texte,
    # sinon un partage depuis la page allemande affiche une accroche en français. Un seul
    # fichier par langue, dérivé de store/feature_graphic_<lang>.png — il n'existe pas de
    # og-image.png sans suffixe : un fichier par défaut que plus personne ne référence est
    # exactement ce qui a laissé la bannière Savoria en ligne après le rebranding.
    h = re.sub(r'<meta[^>]*property="og:image"(?![:])[^>]*>',
               f'<meta property="og:image" content="{BASE}/og-image-{lang}.png">', h)
    h = re.sub(r'<meta[^>]*name="twitter:image"[^>]*>',
               f'<meta name="twitter:image" content="{BASE}/og-image-{lang}.png">', h)
    # canonical auto-référent + hreflang (retire tous les alternate hreflang existants, réinjecte)
    h = re.sub(r'<link[^>]*rel="canonical"[^>]*>',
               f'<link rel="canonical" href="{BASE}/{lang}/">', h)
    h = re.sub(r'\s*<link[^>]*hreflang="[^"]*"[^>]*>', "", h)
    h = h.replace('<link rel="canonical" href="%s/%s/">' % (BASE, lang),
                  '<link rel="canonical" href="%s/%s/">\n%s' % (BASE, lang, hreflang_block("")))
    # JSON-LD par langue
    h = re.sub(r'<script type="application/ld\+json">.*?</script>',
               '<script type="application/ld+json">\n%s\n</script>' % jsonld(lang), h, flags=re.S)
    # 3) sélecteur runtime -> vrais liens <a> (marche sans JS, crawlable)
    h, n = re.subn(r'<details class="langsel" id="langSel">.*?</details>',
                   lambda _m: lang_selector(lang, lambda l: f"/{l}/"), h, flags=re.S)
    if n != 1:
        raise SystemExit(f"landing {lang} : sélecteur de langue substitué {n} fois (attendu 1) — "
                         "le markup de _src/landing.html a bougé")
    # 4) liens de page internes -> nouvelle taxonomie /{lang}/slug/
    for old, slug in PAGE_LINKS.items():
        h = h.replace(f'href="{old}"', f'href="{legal_href(lang, slug)}"')
    # 5) retire le script i18n runtime (contenu déjà figé), garde le reveal
    # ⚠️ Garde-fou OBLIGATOIRE depuis que l'étape 3 remplace le sélecteur : ce script référence
    # `langSelLabel`/`langSelCode`/`langSelMenu`, des ids qui N'EXISTENT PLUS après l'étape 3. S'il
    # survivait (regex qui ne matche plus parce que le markup de _src a bougé), chaque page publiée
    # lèverait une TypeError au chargement. Échouer bruyamment vaut mieux que publier des pages
    # dont le JS casse — même posture que le garde-fou de l'étape 3.
    h, n = re.subn(r'<script>\s*const I18N.*?</script>', lambda _m: REVEAL_JS, h, flags=re.S)
    if n != 1:
        raise SystemExit(f"landing {lang} : script i18n runtime retiré {n} fois (attendu 1) — "
                         "il resterait dans la page publiée en référençant des ids supprimés")
    # 6) chemins d'assets relatifs -> root-absolute (badges/, screens/, icon-512.png…)
    h = re.sub(r'(href|src)="(?!https?://|/|#|mailto:|tel:|data:)', r'\1="/', h)
    # 7) fige l'unique bloc `.reveal` (le hero) à l'état RÉVÉLÉ.
    # ⚠️ Sans ça le générateur n'est PAS idempotent, contrairement à ce qu'annonce son en-tête :
    # `.in` est posé par l'IntersectionObserver, donc `--dump-dom` capture tantôt `reveal`,
    # tantôt `reveal in` selon que l'observer a eu le temps de tourner. Constaté le 30/08/2026 —
    # une régénération qui ne changeait QUE l'og:image a fait basculer le français seul, et une
    # page aurait été publiée avec un comportement différent des quatre autres, sans que rien
    # ne le signale. On fige à `in` (l'état déjà publié) plutôt qu'à `reveal` : le hero porte le
    # <h1> au-dessus de la ligne de flottaison, le peindre tout de suite vaut mieux que le
    # laisser à opacity 0 en attendant le JS. Un seul élément est concerné — rien à animer.
    h = re.sub(r'class="reveal(?! in)"', 'class="reveal in"', h)
    return "<!DOCTYPE html>\n" + h.lstrip()


def router_html(page=""):
    """Routeur négociant : hreflang statique (découverte crawler) + redirection JS (commodité user).
    page='' = home ('/'), page='privacy/' etc. = routeur légal ('/privacy/')."""
    hl = hreflang_block(page)
    avail = langs_for(page)      # jamais LANGS en aveugle : le légal n'existe pas dans toutes
    dflt = default_for(page)
    links = " · ".join(f'<a href="/{l}/{page}">{LANG_LABEL[l]}</a>' for l in avail)
    js_langs = json.dumps(avail)
    return f"""<!DOCTYPE html>
<html lang="{X_DEFAULT}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Aloumi</title>
<link rel="icon" type="image/png" href="/icon-512.png">
{hl}
<meta name="robots" content="noindex,follow">
<meta http-equiv="refresh" content="0; url=/{dflt}/{page}">
<script>
  // Redirection de commodité vers la langue de l'utilisateur. Les crawlers ignorent ce JS
  // et découvrent chaque langue via les hreflang ci-dessus (contenu pré-rendu, pas de JS requis).
  var LANGS = {js_langs};
  var stored; try {{ stored = localStorage.getItem('aloumi_lang'); }} catch(e) {{}}
  var param = new URLSearchParams(location.search).get('lang');
  var nav = (navigator.language || '').toLowerCase();
  var browser = LANGS.filter(function(l){{ return nav.indexOf(l) === 0; }})[0];
  var pick = [param, stored, browser].filter(function(l){{ return LANGS.indexOf(l) >= 0; }})[0] || '{dflt}';
  location.replace('/' + pick + '/{page}' + location.hash);
</script>
</head>
<body>
<p style="font:16px system-ui;padding:24px">Aloumi — {links}</p>
</body>
</html>
"""


def build_legal(footers):
    """Pages légales par langue depuis les sources bilingues (blocs data-lang, sans Chrome).
    `footers` = {lang: markup <footer> extrait de la landing rendue} → chrome de marque cohérent."""
    for slug, src in LEGAL.items():
        raw = (SITE / src).read_text(encoding="utf-8")
        blocks = {}
        for part in raw.split('<div class="langblock" data-lang=')[1:]:
            m = re.match(r'"([a-z]{2})">(.*?)</div>', part, re.S)
            if not m or m.group(1) not in LANGS:      # ignore le marqueur dans le commentaire JS
                continue
            blocks[m.group(1)] = m.group(2).strip()
        for lang in LANGS:
            content = blocks.get(lang)
            if content is None:
                # BRUYANT, jamais silencieux : sans ça, la landing de cette langue liait un 404.
                # ASCII pur : la console Windows (cp1252) plante sur une fleche ou un accent ici.
                print(f"legal      /{lang}/{slug}/ ABSENT - les liens {lang} pointent vers "
                      f"/{LEGAL_FALLBACK}/{slug}/ (texte juridique non traduit)")
                continue
            h1 = re.search(r"<h1>(.*?)</h1>", content, re.S)
            title = re.sub("<[^>]+>", "", h1.group(1)).strip() if h1 else "Aloumi"
            for old, dst in PAGE_LINKS.items():
                content = content.replace(f'href="{old}"', f'href="{legal_href(lang, dst)}"')
            # Sélecteur de langue dans la nav du header (comme la landing), pas flottant dans le
            # corps. `legal_href` replie sur LEGAL_FALLBACK si la langue n'a pas encore son texte.
            lang_links = lang_selector(lang, lambda l: legal_href(l, f"{slug}/"))
            header = (
                f'<header id="hdr"><div class="wrap nav">'
                f'<a class="brand" href="/{lang}/" aria-label="Aloumi">'
                f'<svg class="brand-mark" viewBox="0 0 1024 1024" aria-hidden="true"><use href="#aloumi-logo"></use></svg> Aloumi'
                f'</a><nav class="nav-right">{lang_links}'
                f'<a class="badge-play" href="{PLAY}" target="_blank" rel="noopener">{PLAY_LABEL[lang]}</a>'
                f'</nav></div></header>'
            )
            footer = footers.get(lang, "")
            page = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Aloumi</title>
<meta name="robots" content="index,follow">
<link rel="canonical" href="{BASE}/{lang}/{slug}/">
{hreflang_block(slug + "/")}
<style>
{LANDING_STYLE}
{LEGAL_CSS}
</style>
</head>
<body>
{LOGO_SVG}
{header}
<main class="legal">
<div class="wrap">
{content}
</div>
</main>
{footer}
{HDR_SCROLL_JS}
</body>
</html>
"""
            out = SITE / lang / slug / "index.html"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(page, encoding="utf-8")
            print(f"legal      /{lang}/{slug}/")


def build_sitemap():
    today = datetime.date.today().isoformat()
    pages = [("", "weekly", "1.0")] + [(f"{s}/", LEGAL_FREQ[s], "0.3") for s in LEGAL]
    urls = []
    for page, freq, prio in pages:
        avail = langs_for(page)      # ne pas soumettre de 404 à Search Console
        alts = "".join(
            f'\n    <xhtml:link rel="alternate" hreflang="{l}" href="{BASE}/{l}/{page}"/>'
            for l in avail)
        alts += f'\n    <xhtml:link rel="alternate" hreflang="x-default" href="{BASE}/{default_for(page)}/{page}"/>'
        for lang in avail:
            urls.append(f"""  <url>
    <loc>{BASE}/{lang}/{page}</loc>{alts}
    <lastmod>{today}</lastmod>
    <changefreq>{freq}</changefreq>
    <priority>{prio}</priority>
  </url>""")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
           '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
           + "\n".join(urls) + "\n</urlset>\n")
    (SITE / "sitemap.xml").write_text(xml, encoding="utf-8")
    print("sitemap.xml")


def start_server(directory):
    handler = lambda *a, **k: SimpleHTTPRequestHandler(*a, directory=str(directory), **k)
    for port in range(8140, 8180):
        try:
            httpd = TCPServer(("127.0.0.1", port), handler)
            break
        except OSError:
            continue
    else:
        sys.exit("[build] aucun port libre")
    Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def main():
    httpd, port = start_server(SITE)
    base = f"http://127.0.0.1:{port}/{TEMPLATE}"
    footers = {}
    try:
        for lang in LANGS:
            dom = render_lang(base, lang)
            page = post_process_landing(dom, lang)
            out = SITE / lang / "index.html"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(page, encoding="utf-8")
            fm = re.search(r"<footer>.*?</footer>", page, re.S)   # réutilisé par les pages légales
            footers[lang] = fm.group(0) if fm else ""
            print(f"landing    /{lang}/  ({len(page):,} o)")
        (SITE / "index.html").write_text(router_html(), encoding="utf-8")
        print("routeur    /")
    finally:
        httpd.shutdown()
    build_legal(footers)
    for slug in LEGAL:                       # routeurs légaux négociants (/privacy/ …)
        out = SITE / slug / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(router_html(f"{slug}/"), encoding="utf-8")
        print(f"routeur    /{slug}/")
    build_sitemap()


if __name__ == "__main__":
    main()
