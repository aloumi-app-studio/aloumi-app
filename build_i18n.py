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
BASE = "https://savoria.jeylab.fr"
PLAY = "https://play.google.com/store/apps/details?id=com.savoria.app"
LANGS = ["fr", "en"]            # ordre = ordre du cycle du switcher ; ajouter "de" ici + dans META
LANG_LABEL = {"fr": "Français", "en": "English", "de": "Deutsch"}
OG_LOCALE = {"fr": "fr_FR", "en": "en_US", "de": "de_DE"}
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
        "title": "Savoria — Tes recettes adaptées à ta cuisine, avec un chef IA",
        "desc": "Savoria importe tes recettes (lien, photo, PDF, Instagram, TikTok, YouTube) et les adapte à ton four et ta plaque. Assistant cuisine IA pas à pas, sur Google Play.",
        "ogdesc": "Importe tes recettes (lien, photo, PDF, Instagram, TikTok, YouTube) et laisse le Chef IA les adapter à ton four et ta plaque. Sur Google Play.",
        "appdesc": "App de recettes boostée à l'IA : importe depuis un lien, une photo, un PDF, Instagram, TikTok ou YouTube, adapte les recettes à ton four et ta plaque, guide pas à pas et gère la liste de courses.",
        "features": [
            "Import de recettes depuis un lien, du texte, une photo, un PDF, Instagram, TikTok et YouTube",
            "Adaptation des recettes à l'équipement de cuisine (four, plaque, air fryer, robots)",
            "Assistant IA culinaire contextuel",
            "Mode cuisine pas à pas avec minuteurs par étape",
            "Liste de courses avec catégorisation automatique par rayon",
            "Partage de recettes, courses et adresses en temps réel",
        ],
        "faq": [
            ("Savoria est-elle gratuite ?", "Oui. Savoria est disponible gratuitement sur Google Play pendant sa phase de test ouvert."),
            ("Peut-on importer une recette depuis Instagram, TikTok ou YouTube ?", "Oui. Colle le lien ou partage la publication vers Savoria : le Chef IA récupère la recette et la structure automatiquement, y compris depuis une vidéo."),
            ("Savoria adapte-t-elle les recettes à mon four et ma plaque ?", "Oui. Tu configures ton équipement (four, plaque, air fryer, robots) une fois, et Savoria adapte les étapes de cuisson à ton matériel réel."),
            ("Peut-on importer une recette depuis une photo ou un PDF ?", "Oui. Photographie une recette manuscrite ou une page de livre, ou importe un PDF : Savoria en extrait les ingrédients et les étapes."),
            ("Sur quelles plateformes Savoria est-elle disponible ?", "Savoria est disponible sur Android via Google Play. Une version iOS est à l'étude."),
            ("Comment fonctionne le mode cuisine ?", "Le mode cuisine affiche la recette étape par étape, avec des minuteurs par étape, le rappel des ingrédients et un assistant IA qui connaît la recette en cours."),
            ("Pourquoi adapter une recette à ma cuisine ?", "Chaque équipement cuit différemment : un four, une plaque à induction, un air fryer ou un robot n'ont ni la même puissance ni les mêmes réglages d'un modèle à l'autre. Une recette écrite pour un autre matériel peut rater chez toi. Savoria réécrit temps, températures et réglages pour ton équipement réel — pour réussir du premier coup."),
        ],
    },
    "en": {
        "title": "Savoria — Your recipes, adapted to your kitchen, with an AI chef",
        "desc": "Savoria imports your recipes (link, photo, PDF, Instagram, TikTok, YouTube) and adapts them to your oven and cooktop. Step-by-step AI cooking assistant, on Google Play.",
        "ogdesc": "Import your recipes (link, photo, PDF, Instagram, TikTok, YouTube) and let the AI Chef adapt them to your oven and cooktop. On Google Play.",
        "appdesc": "AI-powered recipe app: import from a link, a photo, a PDF, Instagram, TikTok or YouTube, adapt recipes to your oven and cooktop, cook step by step and manage your shopping list.",
        "features": [
            "Recipe import from a link, text, a photo, a PDF, Instagram, TikTok and YouTube",
            "Recipe adaptation to your kitchen equipment (oven, cooktop, food processors, air fryer)",
            "Contextual AI cooking assistant",
            "Step-by-step cooking mode with per-step timers",
            "Shopping list with automatic sorting by aisle",
            "Real-time sharing of recipes, shopping lists and addresses",
        ],
        "faq": [
            ("Is Savoria free?", "Yes. Savoria is available for free on Google Play during its open testing phase."),
            ("Can I import a recipe from Instagram, TikTok or YouTube?", "Yes. Paste the link or share the post to Savoria: the AI Chef fetches the recipe and structures it automatically, even from a video."),
            ("Does Savoria adapt recipes to my oven and cooktop?", "Yes. Set up your equipment (oven, cooktop, food processors, air fryer) once, and Savoria adapts the cooking steps to your actual gear."),
            ("Can I import a recipe from a photo or PDF?", "Yes. Snap a handwritten recipe or a cookbook page, or import a PDF: Savoria extracts the ingredients and steps."),
            ("Which platforms is Savoria available on?", "Savoria is available on Android via Google Play. An iOS version is under consideration."),
            ("How does cooking mode work?", "Cooking mode shows the recipe step by step, with per-step timers, ingredient reminders and an AI assistant that knows the current recipe."),
            ("Why adapt a recipe to my kitchen?", "Every appliance cooks differently: an oven, an induction cooktop, an air fryer or a food processor don't share the same power or settings from one model to the next. A recipe written for other equipment can flop in your kitchen. Savoria rewrites times, temperatures and settings for your actual gear — so it comes out right the first time."),
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

REVEAL_JS = """<script>
  const hdr = document.getElementById('hdr');
  const onScroll = () => hdr && hdr.classList.toggle('scrolled', window.scrollY > 8);
  onScroll(); addEventListener('scroll', onScroll, { passive:true });
  const io = new IntersectionObserver((es) => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { threshold:.12 });
  document.querySelectorAll('.reveal').forEach((el,i) => { el.style.transitionDelay = (Math.min(i,6)*60)+'ms'; io.observe(el); });
</script>"""

# ── Chrome partagé (header + footer) des pages légales ────────────────────────────────────
# THÉMING PARTAGÉ AVEC LA LANDING (SSOT = _src/landing.html) : les pages légales réutilisent le
# design system COMPLET de la landing — LANDING_STYLE (tokens light+dark, base, header .nav sticky,
# footer grid riche, responsive) est extrait tel quel du <style> de la landing, puis LEGAL_CSS
# n'ajoute QUE la colonne de lecture + la typo du corps légal, rebasée sur les mêmes variables
# (--ink/--accent/--muted/--line/--surface). Le logo (symbole SVG) et le footer (markup traduit par
# langue) sont déjà extraits de la landing → header/footer strictement identiques à la home.
LOGO_SVG = re.search(r'<svg[^>]*>\s*<symbol id="savoria-logo".*?</symbol>\s*</svg>',
                     (SITE / TEMPLATE).read_text(encoding="utf-8"), re.S).group(0)

# CSS du design system de la landing (tokens, base, header, footer, dark mode) — SSOT.
LANDING_STYLE = re.search(r"<style>(.*?)</style>",
                          (SITE / TEMPLATE).read_text(encoding="utf-8"), re.S).group(1)

PLAY_LABEL = {"fr": "Sur Google Play", "en": "On Google Play", "de": "Bei Google Play"}

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
                 "s();addEventListener('scroll',s,{passive:true});</script>")


def jsonld(lang):
    m = META[lang]
    graph = [
        {"@type": "Organization", "@id": BASE + "/#org", "name": "JEYLAB", "url": BASE + "/",
         "logo": BASE + "/icon-512.png", "email": "savoriaapp@gmail.com",
         "brand": {"@type": "Brand", "name": "Savoria"}},
        {"@type": "WebSite", "@id": BASE + "/#website", "name": "Savoria",
         "url": f"{BASE}/{lang}/", "inLanguage": lang, "publisher": {"@id": BASE + "/#org"}},
        {"@type": "MobileApplication", "@id": BASE + "/#app", "name": "Savoria",
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


def hreflang_block(page=""):
    """page = '' pour le landing, 'privacy/' etc. pour le légal."""
    lines = [f'<link rel="alternate" hreflang="{l}" href="{BASE}/{l}/{page}">' for l in LANGS]
    lines.append(f'<link rel="alternate" hreflang="x-default" href="{BASE}/{X_DEFAULT}/{page}">')
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
    # canonical auto-référent + hreflang (retire tous les alternate hreflang existants, réinjecte)
    h = re.sub(r'<link[^>]*rel="canonical"[^>]*>',
               f'<link rel="canonical" href="{BASE}/{lang}/">', h)
    h = re.sub(r'\s*<link[^>]*hreflang="[^"]*"[^>]*>', "", h)
    h = h.replace('<link rel="canonical" href="%s/%s/">' % (BASE, lang),
                  '<link rel="canonical" href="%s/%s/">\n%s' % (BASE, lang, hreflang_block("")))
    # JSON-LD par langue
    h = re.sub(r'<script type="application/ld\+json">.*?</script>',
               '<script type="application/ld+json">\n%s\n</script>' % jsonld(lang), h, flags=re.S)
    # 3) switcher runtime -> vrais liens <a> (marche sans JS, crawlable)
    others = "".join(
        f'<a class="lang" href="/{l}/">{LANG_LABEL[l]}</a>' for l in LANGS if l != lang)
    h = re.sub(r'<button class="lang" id="langToggle"[^>]*>.*?</button>', others, h, flags=re.S)
    # 4) liens de page internes -> nouvelle taxonomie /{lang}/slug/
    for old, slug in PAGE_LINKS.items():
        h = h.replace(f'href="{old}"', f'href="/{lang}/{slug}"')
    # 5) retire le script i18n runtime (contenu déjà figé), garde le reveal
    h = re.sub(r'<script>\s*const I18N.*?</script>', REVEAL_JS, h, flags=re.S)
    # 6) chemins d'assets relatifs -> root-absolute (badges/, screens/, icon-512.png…)
    h = re.sub(r'(href|src)="(?!https?://|/|#|mailto:|tel:|data:)', r'\1="/', h)
    return "<!DOCTYPE html>\n" + h.lstrip()


def router_html(page=""):
    """Routeur négociant : hreflang statique (découverte crawler) + redirection JS (commodité user).
    page='' = home ('/'), page='privacy/' etc. = routeur légal ('/privacy/')."""
    hl = hreflang_block(page)
    links = " · ".join(f'<a href="/{l}/{page}">{LANG_LABEL[l]}</a>' for l in LANGS)
    js_langs = json.dumps(LANGS)
    return f"""<!DOCTYPE html>
<html lang="{X_DEFAULT}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Savoria</title>
<link rel="icon" type="image/png" href="/icon-512.png">
{hl}
<meta name="robots" content="noindex,follow">
<meta http-equiv="refresh" content="0; url=/{X_DEFAULT}/{page}">
<script>
  // Redirection de commodité vers la langue de l'utilisateur. Les crawlers ignorent ce JS
  // et découvrent chaque langue via les hreflang ci-dessus (contenu pré-rendu, pas de JS requis).
  var LANGS = {js_langs};
  var stored; try {{ stored = localStorage.getItem('savoria_lang'); }} catch(e) {{}}
  var param = new URLSearchParams(location.search).get('lang');
  var nav = (navigator.language || '').toLowerCase();
  var browser = LANGS.filter(function(l){{ return nav.indexOf(l) === 0; }})[0];
  var pick = [param, stored, browser].filter(function(l){{ return LANGS.indexOf(l) >= 0; }})[0] || '{X_DEFAULT}';
  location.replace('/' + pick + '/{page}' + location.hash);
</script>
</head>
<body>
<p style="font:16px system-ui;padding:24px">Savoria — {links}</p>
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
                continue
            h1 = re.search(r"<h1>(.*?)</h1>", content, re.S)
            title = re.sub("<[^>]+>", "", h1.group(1)).strip() if h1 else "Savoria"
            for old, dst in PAGE_LINKS.items():
                content = content.replace(f'href="{old}"', f'href="/{lang}/{dst}"')
            # Switcher de langue dans la nav du header (comme la landing), pas flottant dans le corps.
            lang_links = "".join(
                f'<a class="lang" href="/{l}/{slug}/">{LANG_LABEL[l]}</a>'
                for l in LANGS if l != lang)
            header = (
                f'<header id="hdr"><div class="wrap nav">'
                f'<a class="brand" href="/{lang}/" aria-label="Savoria">'
                f'<svg class="brand-mark" viewBox="0 0 1024 1024" aria-hidden="true"><use href="#savoria-logo"></use></svg> Savoria'
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
<title>{title} — Savoria</title>
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
        alts = "".join(
            f'\n    <xhtml:link rel="alternate" hreflang="{l}" href="{BASE}/{l}/{page}"/>'
            for l in LANGS)
        alts += f'\n    <xhtml:link rel="alternate" hreflang="x-default" href="{BASE}/{X_DEFAULT}/{page}"/>'
        for lang in LANGS:
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
