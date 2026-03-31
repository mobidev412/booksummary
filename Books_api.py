import urllib.request
import urllib.parse
import urllib.error
import json
import os
import re

GOOGLE_BOOKS_API     = "https://www.googleapis.com/books/v1/volumes"
GOOGLE_BOOKS_API_KEY = os.environ.get("GOOGLE_BOOKS_API_KEY")


# ─────────────────────────────────────────────────────────────────────────────
# Normalizers — applied to every book returned from the API so the data is
# clean at the source (DB, session, and cache key all stay consistent).
# ─────────────────────────────────────────────────────────────────────────────

def _clean_title(title: str) -> str:
    """
    Strip subtitle from book title.
    'Rich Dad Poor Dad - What the Rich Teach...' → 'Rich Dad Poor Dad'
    'Atomic Habits: An Easy & Proven Way...'     → 'Atomic Habits'
    """
    for sep in (" - ", ": ", " : "):
        if sep in title:
            title = title.split(sep)[0]
    return title.strip()


def _clean_author(author: str) -> str:
    """
    Keep only the first author and remove single-letter middle initials.
    'Robert T. Kiyosaki, Sharon Lechter' → 'Robert Kiyosaki'
    """
    first = author.split(",")[0].strip()
    parts = [p for p in first.split() if not re.match(r"^[A-Z]\.$", p)]
    return " ".join(parts)


def search_book(title, author=None):

    query = title
    if author:
        query += f" inauthor:{author}"

    params = urllib.parse.urlencode({
        "q":          query,
        "maxResults": 1,
        "key":        GOOGLE_BOOKS_API_KEY,
    })
    url = f"{GOOGLE_BOOKS_API}?{params}"

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode())

        if data.get("totalItems", 0) == 0:
            return None

        item = data["items"][0]
        info = item.get("volumeInfo", {})

        return {
            "title":          _clean_title(info.get("title", title)),
            "author":         _clean_author(", ".join(info.get("authors", ["Unknown"]))),
            "description":    info.get("description", ""),
            "genre":          ", ".join(info.get("categories", ["General"])),
            "published_year": info.get("publishedDate", "")[:4],
            "cover_image":    info.get("imageLinks", {}).get("thumbnail", "").replace("http://", "https://"),
        }

    except Exception as e:
        print(f" Google Books API error: {e}")
        return None


def get_book_suggestions(genre_1, genre_2, goal, count=5):

    query  = f"{genre_1} {genre_2} {goal} best books"
    params = urllib.parse.urlencode({
        "q":          query,
        "maxResults": count,
        "orderBy":    "relevance",
        "key":        GOOGLE_BOOKS_API_KEY,
    })
    url = f"{GOOGLE_BOOKS_API}?{params}"

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode())

        books = []
        for item in data.get("items", []):
            info = item.get("volumeInfo", {})
            books.append({
                "title":          _clean_title(info.get("title", "Unknown")),
                "author":         _clean_author(", ".join(info.get("authors", ["Unknown"]))),
                "description":    info.get("description", ""),
                "genre":          ", ".join(info.get("categories", ["General"])),
                "published_year": info.get("publishedDate", "")[:4],
                "cover_image":    info.get("imageLinks", {}).get("thumbnail", "").replace("http://", "https://"),
            })
        return books

    except Exception as e:
        print(f" Google Books API error: {e}")
        return []


def fetch_books_for_genre(genre: str, count: int = 8) -> list:
    """
    Fetch books from Google Books API using a single genre as the search query.
    Used exclusively by the recommendation engine to fill slots not covered by DB.

    Args:
        genre: genre string, e.g. "Thriller" or "Self-help & Psychology"
        count: max number of results to request (fetches a few extra for dedup buffer)

    Returns:
        List of book dicts with 'source' set to 'api'.
    """
    params = urllib.parse.urlencode({
        "q":          f"subject:{genre}",
        "maxResults": min(count, 40),   # Google Books API max is 40
        "orderBy":    "relevance",
        "key":        GOOGLE_BOOKS_API_KEY,
    })
    url = f"{GOOGLE_BOOKS_API}?{params}"

    try:
        with urllib.request.urlopen(url, timeout=7) as response:
            data = json.loads(response.read().decode())

        books = []
        for item in data.get("items", []):
            info = item.get("volumeInfo", {})
            raw_title = info.get("title", "").strip()
            if not raw_title:
                continue
            books.append({
                "title":          _clean_title(raw_title),
                "author":         _clean_author(", ".join(info.get("authors", ["Unknown"]))),
                "description":    info.get("description", ""),
                "genre":          ", ".join(info.get("categories", [genre])),
                "published_year": info.get("publishedDate", "")[:4],
                "cover_image":    info.get("imageLinks", {}).get("thumbnail", "").replace("http://", "https://"),
                "source":         "api",
            })
        return books

    except Exception as e:
        print(f"[Books_api] fetch_books_for_genre error (genre='{genre}'): {e}")
        return []