#!/usr/bin/env python3
"""Dérive les captures web du site depuis la SOURCE UNIQUE des mockups store.

Entrée  : ../store/raw/<lang>/*.png   (mockups 1620×3270 générés par langue — SSOT, partagés avec la fiche Play Store)
Sortie  : ./screens/<lang>/*.png      (mêmes captures redimensionnées à 800 px de large pour le web)

Le landing sert screens/<lang>/… selon la langue de la page (data-i18n-src), donc une page EN
montre les mockups EN, une page FR les mockups FR. Une capture ne se redessine jamais pour le web :
elle est le mockup store réduit. Ajouter une langue = ajouter store/raw/<lang>/ + la pousser dans LANGS.

Redimensionnement via Chrome headless (aucune lib image type PIL/ImageMagick sur la machine),
même dépendance que build_i18n.py. Idempotent. Lancer : python build_screens.py
"""
import os, struct, subprocess, sys, tempfile, pathlib

SITE = pathlib.Path(__file__).parent
STORE_RAW = (SITE / ".." / "store" / "raw").resolve()
LANGS = ["fr", "en"]            # miroir de build_i18n.py — garder synchronisé
SHOTS = ["01_import.png", "02_collection.png", "03_inspiration.png",
         "04_cooking.png", "05_equipment.png", "06_shopping.png"]
WIDTH = 1000                    # largeur cible web. Le landing affiche les captures à ~250px CSS max
                                # (hero .phone 266px − 16px padding = 250px ; galerie .shot 200px, non
                                # agrandis sur mobile) → 1000px = 4× au hero (250×4), 5× en galerie,
                                # DOWNSCALE net du mockup source 1620px, jamais upscalé sur AUCUN DPI
                                # (retina 2× MacBook/iPad, 3× iPhone Pro, marge pour un hypothétique 4×).
                                # Historique : 520px était upscalé 3× sur mobile (flou), 800px couvrait
                                # déjà le 3× ; 1000px = marge de sécurité explicite. Ne pas descendre
                                # sous ~800. Poids ~1 Mo/image (PNG lossless, hero photo) — assumé pour
                                # la netteté, la page ne charge que les 6 captures de sa langue.

CHROME = next((p for p in [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
] if os.path.exists(p)), None)
assert CHROME, "Chrome introuvable — ajuste le chemin"


def png_size(path):
    with open(path, "rb") as fh:
        fh.read(16)
        return struct.unpack(">II", fh.read(8))  # (w, h)


def file_uri(path):
    return pathlib.Path(path).resolve().as_uri()


def resize(src, dst):
    w, h = png_size(src)
    out_h = round(h * WIDTH / w)
    html = ('<!doctype html><meta charset="utf-8">'
            '<style>*{margin:0;padding:0}html,body{background:#000;line-height:0}'
            f'img{{width:{WIDTH}px;height:auto;display:block}}</style>'
            f'<img src="{file_uri(src)}">')
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tf:
        tf.write(html)
        tmp = tf.name
    try:
        subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
             "--force-device-scale-factor=1", f"--window-size={WIDTH},{out_h}",
             "--default-background-color=00000000", f"--screenshot={dst}", file_uri(tmp)],
            capture_output=True, timeout=60)
    finally:
        os.unlink(tmp)
    if not os.path.exists(dst):
        sys.exit(f"[build] échec capture {dst}")
    return png_size(dst)


def main():
    for lang in LANGS:
        srcdir = STORE_RAW / lang
        outdir = SITE / "screens" / lang
        outdir.mkdir(parents=True, exist_ok=True)
        for shot in SHOTS:
            src = srcdir / shot
            if not src.exists():
                sys.exit(f"[build] source manquante : {src}")
            w, h = resize(str(src), str(outdir / shot))
            print(f"screens/{lang}/{shot}  {w}x{h}")


if __name__ == "__main__":
    main()
