"""Extraction des données depuis les sources.

Deux fonctions, toutes deux renvoyant une LISTE DE DICTIONNAIRES au même format
(les colonnes de la table publications) :
  - fetch_newsapi() : articles de presse (label 'unknown').
  - fetch_rss()     : flux RSS de fact-checkers (label déduit du verdict).
"""
import hashlib
import logging
import os
import re
from datetime import datetime, timezone

import feedparser
import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

NEWSAPI_URL = "https://newsapi.org/v2/everything"

# Flux RSS de fact-checkers. VÉRIFIE chaque URL avant usage (voir la commande de test
# donnée par l'assistant) : un flux invalide renverra simplement 0 entrée.
FEEDS = {
    "lemonde-decodeurs": {"url": "https://www.lemonde.fr/les-decodeurs/rss_full.xml", "lang": "fr"},
    "snopes": {"url": "https://www.snopes.com/feed/", "lang": "en"},
}


# ---------------------------------------------------------------------------
# Utilitaires communs
# ---------------------------------------------------------------------------
def _fabrique_id(url):
    """Identifiant déterministe : même article -> même id (active l'anti-doublon)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _parse_date_iso(valeur):
    """Convertit une date ISO ('2026-08-26T10:00:00Z') en datetime. None si illisible."""
    if not valeur:
        return None
    try:
        return datetime.fromisoformat(valeur.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Source 1 : NewsAPI
# ---------------------------------------------------------------------------
def fetch_newsapi(query="actualité", language="fr", page_size=20):
    """Récupère des articles depuis NewsAPI (/v2/everything).
    On ne garde que les articles AVEC image. Label laissé à 'unknown'."""
    cle = os.getenv("CHECKIT_NEWSAPI_KEY")
    if not cle:
        raise RuntimeError("Clé NewsAPI absente : vérifie CHECKIT_NEWSAPI_KEY dans .env")

    params = {
        "q": query,
        "language": language,
        "sortBy": "publishedAt",
        "pageSize": page_size,
        "apiKey": cle,
    }
    try:
        reponse = requests.get(NEWSAPI_URL, params=params, timeout=15)
        reponse.raise_for_status()
    except requests.RequestException as exc:
        log.error("échec de l'appel NewsAPI : %s", exc)
        return []

    donnees = reponse.json()
    if donnees.get("status") != "ok":
        log.error("réponse NewsAPI en erreur : %s", donnees.get("message"))
        return []

    publications = []
    for article in donnees.get("articles", []):
        image_url = article.get("urlToImage")
        url = article.get("url")
        if not image_url or not url:
            continue
        publications.append({
            "id": _fabrique_id(url),
            "source": (article.get("source") or {}).get("name"),
            "url": url,
            "title": article.get("title"),
            "content": article.get("description"),
            "image_path": None,
            "image_url": image_url,
            "language": language,
            "label": "unknown",
            "published_at": _parse_date_iso(article.get("publishedAt")),
            "fetched_at": datetime.now(timezone.utc),
        })
    log.info("NewsAPI : %d articles avec image récupérés", len(publications))
    return publications


# ---------------------------------------------------------------------------
# Source 2 : flux RSS de fact-checkers
# ---------------------------------------------------------------------------
# Détection PRUDENTE du verdict. On ne classe que sur signaux explicites ;
# tout le reste reste 'unknown'. Opinion controversée != désinformation.
_FALSE = re.compile(r"\b(faux|fausse|infox|intox|infond[ée]e?|mensong\w*)\b", re.I)
_MIXED = re.compile(r"\b(trompeur|trompeuse|partiellement|en partie|hors contexte)\b", re.I)
_TRUE = re.compile(r"\b(vrai|vraie|authentique|exact)\b", re.I)
# mots-clés anglais (Snopes et autres fact-checkers anglophones)
_EN_FALSE = re.compile(r"\b(false|fake|hoax|debunk\w*|scam)\b", re.I)
_EN_MIXED = re.compile(r"\b(misleading|mostly false|mostly true|mixture|unproven|partly)\b", re.I)
_EN_TRUE = re.compile(r"\b(true|legit|accurate)\b", re.I)


def _rss_label(entry):
    """Déduit un label du titre + tags + résumé de l'article. Défaut prudent : 'unknown'.
    Gère le français et l'anglais. Opinion controversée != désinformation."""
    titre = getattr(entry, "title", "") or ""
    tags = " ".join(t.get("term", "") for t in getattr(entry, "tags", []) or [])
    resume = getattr(entry, "summary", "") or ""
    blob = f"{titre} {tags} {resume}"
    # Conventions FR : titre en "Non, ..." = faux ; "Oui, ..." = vrai
    if titre.strip().lower().startswith("non,"):
        return "false"
    if titre.strip().lower().startswith("oui,"):
        return "true"
    # Sinon, on cherche des signaux explicites (mixte avant faux/vrai)
    if _MIXED.search(blob) or _EN_MIXED.search(blob):
        return "mixed"
    if _FALSE.search(blob) or _EN_FALSE.search(blob):
        return "false"
    if _TRUE.search(blob) or _EN_TRUE.search(blob):
        return "true"
    return "unknown"


def _rss_image(entry):
    """Cherche une image dans l'entrée RSS (media:content, thumbnail, enclosure)."""
    for media in getattr(entry, "media_content", []) or []:
        if media.get("url"):
            return media["url"]
    for thumb in getattr(entry, "media_thumbnail", []) or []:
        if thumb.get("url"):
            return thumb["url"]
    for enc in getattr(entry, "enclosures", []) or []:
        if str(enc.get("type", "")).startswith("image") and enc.get("href"):
            return enc["href"]
    return None


def _rss_date(entry):
    """Convertit la date d'une entrée RSS en datetime UTC. None si absente."""
    st = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    return datetime(*st[:6], tzinfo=timezone.utc) if st else None


def fetch_rss(feeds=None):
    """Lit les flux RSS de fact-checkers et renvoie une liste de dicts.
    On ne garde que les entrées AVEC image. Le label est déduit du verdict."""
    feeds = feeds or FEEDS
    publications = []
    for nom, conf in feeds.items():
        parsed = feedparser.parse(conf["url"])
        if parsed.bozo:
            log.warning("flux %s mal formé ou inaccessible : %s", nom, parsed.bozo_exception)
        gardes = 0
        for entry in parsed.entries:
            image_url = _rss_image(entry)
            url = getattr(entry, "link", None)
            if not image_url or not url:
                continue
            publications.append({
                "id": _fabrique_id(url),
                "source": nom,
                "url": url,
                "title": getattr(entry, "title", None),
                "content": getattr(entry, "summary", None),
                "image_path": None,
                "image_url": image_url,
                "language": conf.get("lang", "fr"),
                "label": _rss_label(entry),
                "published_at": _rss_date(entry),
                "fetched_at": datetime.now(timezone.utc),
            })
            gardes += 1
        log.info("RSS %s : %d entrées avec image", nom, gardes)
    return publications


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    rss = fetch_rss()
    print(f"\n{len(rss)} entrées RSS récupérées.")
    for p in rss[:5]:
        print(f"  [{p['label']:8}] {p['source']:18} | {p['title']}")
