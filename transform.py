"""Transformation des données extraites, avant leur insertion en base.

Traitements, dans l'ordre :
  - nettoie_texte()  : enlève le bruit (HTML, marqueur NewsAPI, espaces).
  - normalise()      : met les champs dans une forme standard cohérente.
  - valide_et_telecharge_image() : vérifie que l'image est exploitable et la télécharge.
  - genere_colonnes(): calcule des colonnes dérivées utiles pour l'IA.

Une publication sans image valide est écartée (le détecteur est multimodal).
"""
import html
import io
import logging
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests
from PIL import Image

log = logging.getLogger(__name__)

IMAGES_DIR = Path("images")
_TAG_RE = re.compile(r"<[^>]+>")
_TRUNC_RE = re.compile(r"\[\+\d+\s*chars?\]")
_TRACKING = ("utm_", "fbclid", "gclid", "mc_")   # paramètres de tracking à retirer des URL


# ---------------------------------------------------------------------------
# 1. Nettoyage du texte (enlever le bruit)
# ---------------------------------------------------------------------------
def nettoie_texte(texte):
    """Entités HTML, balises, marqueur '[+123 chars]', espaces multiples."""
    if not texte:
        return None
    texte = html.unescape(texte)
    texte = _TAG_RE.sub(" ", texte)
    texte = _TRUNC_RE.sub("", texte)
    texte = re.sub(r"\s+", " ", texte).strip()
    return texte or None


# ---------------------------------------------------------------------------
# 2. Normalisation (forme standard cohérente)
# ---------------------------------------------------------------------------
def _normalise_texte(texte):
    """Forme Unicode canonique (NFC) : deux écritures d'un même accent deviennent identiques."""
    return unicodedata.normalize("NFC", texte) if texte else None


def _normalise_url(url):
    """Retire les paramètres de tracking (utm_*, fbclid...) pour une URL stable."""
    if not url:
        return url
    parts = urlparse(url)
    if not parts.query:
        return url
    params = [p for p in parts.query.split("&")
              if p and not p.lower().startswith(_TRACKING)]
    return urlunparse(parts._replace(query="&".join(params)))


def normalise(pub):
    """Applique les normalisations à une publication (dict) et la renvoie."""
    pub["title"] = _normalise_texte(pub.get("title"))
    pub["content"] = _normalise_texte(pub.get("content"))
    if pub.get("language"):
        pub["language"] = pub["language"].lower()      # code langue homogène (ISO minuscule)
    pub["url"] = _normalise_url(pub.get("url"))
    return pub


# ---------------------------------------------------------------------------
# 3. Validation + téléchargement de l'image
# ---------------------------------------------------------------------------
def valide_et_telecharge_image(url, nom_fichier, dossier=IMAGES_DIR, timeout=15):
    """Télécharge l'image, vérifie que c'en est bien une, l'enregistre.
    Renvoie le chemin local (str) ou None si échec/invalide."""
    dossier.mkdir(parents=True, exist_ok=True)
    try:
        reponse = requests.get(url, timeout=timeout)
        reponse.raise_for_status()
        donnees = reponse.content
        image = Image.open(io.BytesIO(donnees))
        extension = (image.format or "JPEG").lower()
        image.verify()
    except Exception as exc:
        log.warning("image ignorée (%s) : %s", url, exc)
        return None

    if extension == "jpeg":
        extension = "jpg"
    chemin = dossier / f"{nom_fichier}.{extension}"
    chemin.write_bytes(donnees)
    return str(chemin)


# ---------------------------------------------------------------------------
# 4. Génération de colonnes dérivées (features simples pour l'IA)
# ---------------------------------------------------------------------------
def genere_colonnes(pub):
    """Ajoute des colonnes calculées à partir du contenu, utiles en classification NLP."""
    contenu = pub.get("content") or ""
    pub["content_length"] = len(contenu)          # longueur du texte (caractères)
    pub["word_count"] = len(contenu.split())      # nombre de mots
    return pub


# ---------------------------------------------------------------------------
# 5. Transformation d'une liste de publications
# ---------------------------------------------------------------------------
def transforme(publications):
    """Nettoyage -> normalisation -> image -> génération de colonnes.
    Écarte les publications sans image exploitable. Renvoie la liste transformée."""
    resultat = []
    for pub in publications:
        pub["title"] = nettoie_texte(pub.get("title"))
        pub["content"] = nettoie_texte(pub.get("content"))
        pub = normalise(pub)

        chemin = valide_et_telecharge_image(pub["image_url"], pub["id"])
        if chemin is None:
            continue
        pub["image_path"] = chemin

        pub = genere_colonnes(pub)
        resultat.append(pub)

    log.info("transformation : %d/%d publications conservées",
             len(resultat), len(publications))
    return resultat


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from extract import fetch_newsapi
    propres = transforme(fetch_newsapi(page_size=5))
    print(f"\n{len(propres)} publications transformées.")
    if propres:
        p = propres[0]
        for cle in ("title", "content", "language", "url", "image_path",
                    "content_length", "word_count"):
            print(f"  {cle:15} : {p.get(cle)}")
