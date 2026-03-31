"""
recommendations.py
─────────────────────────────────────────────────────────────────────────────
Hybrid book recommendation engine.

Priority:
  1. Books already in the `books` table that match the genre (DB-first).
  2. Fill any remaining slots (up to 4) from the Google Books API.

No external dependencies beyond what the project already uses.
"""

from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from db import get_connection, get_cursor
from Books_api import fetch_books_for_genre


# Number of book suggestions to return per genre
SUGGESTIONS_PER_GENRE = 4


def _query_db_books(genre: str) -> List[dict]:
    """
    Query the books table for books that match the given genre.
    Uses case-insensitive partial match (ILIKE) so that stored genres like
    "Fiction, Adventure" still match a preference of "Fiction & Storytelling".
    Returns up to SUGGESTIONS_PER_GENRE books ordered by most recent first.
    """
    conn = get_connection()
    cursor = get_cursor(conn)
    try:
        # Use the first word of the genre for a broader match
        # e.g. "Self-help & Psychology" → search for "Self"
        # Full genre is also tried so exact matches are preferred.
        genre_keyword = genre.split("&")[0].split("-")[0].strip()

        cursor.execute(
            """
            SELECT id, title, author, genre, cover_image, description, published_year
            FROM   books
            WHERE  LOWER(genre) LIKE LOWER(%s)
               OR  LOWER(genre) LIKE LOWER(%s)
            ORDER  BY created_at DESC
            LIMIT  %s
            """,
            (
                f"%{genre}%",          # exact genre phrase match
                f"%{genre_keyword}%",  # keyword-based fallback
                SUGGESTIONS_PER_GENRE,
            ),
        )
        rows = cursor.fetchall()
        books = []
        for row in rows:
            books.append({
                "title":          row["title"],
                "author":         row["author"],
                "genre":          row["genre"],
                "cover_image":    row["cover_image"] or "",
                "description":    row["description"] or "",
                "published_year": row["published_year"] or "",
                "source":         "db",
            })
        return books
    except Exception as e:
        print(f"[recommendations] DB query error for genre '{genre}': {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def _deduplicate(api_books: List[dict], db_titles: set) -> List[dict]:
    """
    Remove API books whose titles already exist in the DB result set.
    Comparison is case-insensitive.
    Also removes duplicates within the API results themselves.
    """
    seen_titles = set(t.lower() for t in db_titles)
    unique = []
    for book in api_books:
        norm_title = book["title"].lower().strip()
        if norm_title not in seen_titles:
            seen_titles.add(norm_title)
            unique.append(book)
    return unique


def _process_genre(genre: str) -> tuple:
    """
    Process a single genre: DB lookup first, then API fill if needed.
    Returns (genre, list_of_books) tuple for use with ThreadPoolExecutor.
    Core logic is identical — only wrapped in a function for parallel execution.
    """
    t0 = time.time()

    # ── Step 1: DB lookup ────────────────────────────────────────────────
    db_books = _query_db_books(genre)
    print(f"[recommendations] Genre '{genre}' → {len(db_books)} DB book(s)")

    if len(db_books) >= SUGGESTIONS_PER_GENRE:
        elapsed = round((time.time() - t0) * 1000)
        print(f"[recommendations] '{genre}' served fully from DB ({elapsed}ms)")
        return genre, db_books[:SUGGESTIONS_PER_GENRE]

    # ── Step 2: Fill remaining slots from API ────────────────────────────
    slots_needed  = SUGGESTIONS_PER_GENRE - len(db_books)
    db_titles     = {b["title"] for b in db_books}

    # Request a few extra from API to account for post-dedup losses
    api_books_raw = fetch_books_for_genre(genre, count=slots_needed + 4)
    api_books     = _deduplicate(api_books_raw, db_titles)[:slots_needed]

    elapsed = round((time.time() - t0) * 1000)
    print(
        f"[recommendations] Genre '{genre}' → "
        f"{len(api_books)} API book(s) added "
        f"(after dedup, needed {slots_needed}, total {elapsed}ms)"
    )

    return genre, db_books + api_books


def get_personalized_suggestions(genres: List[str]) -> Dict[str, List[dict]]:
    """
    For each genre, return up to SUGGESTIONS_PER_GENRE (4) books.

    Priority:
      1. Books already in the database (most recent first).
      2. Books from Google Books API if DB has fewer than 4 results.

    Both genres are processed IN PARALLEL using ThreadPoolExecutor so the
    total wait time equals the slowest genre, not the sum of all genres.

    Args:
        genres: list of genre strings, e.g. ["Thriller", "Self-help & Psychology"]

    Returns:
        A dict mapping each genre to its list of up to 4 book dicts.
    """
    result: Dict[str, List[dict]] = {}
    active_genres = [g for g in genres if g]

    if not active_genres:
        return result

    # Run each genre in a thread — DB + API calls run concurrently
    with ThreadPoolExecutor(max_workers=len(active_genres)) as executor:
        futures = {
            executor.submit(_process_genre, genre): genre
            for genre in active_genres
        }
        for future in as_completed(futures):
            try:
                genre, books = future.result()
                result[genre] = books
            except Exception as e:
                genre = futures[future]
                print(f"[recommendations] Error processing genre '{genre}': {e}")
                result[genre] = []

    return result
