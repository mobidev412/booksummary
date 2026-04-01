import re
import json
from db import get_connection, get_cursor


def _normalize_title(title: str) -> str:
    """
    Strip subtitle so that title variations map to the same cache key.
    e.g. 'Rich Dad Poor Dad - What the Rich Teach...' → 'Rich Dad Poor Dad'
         'Atomic Habits: An Easy & Proven Way...'    → 'Atomic Habits'
    """
    for sep in (" - ", ": ", " : ", " – ", " — "):
        if sep in title:
            title = title.split(sep)[0]
    return title.strip()


def _normalize_author(author: str) -> str:
    """
    Take the first author only to avoid cache misses when the API returns
    'Author A, Author B' vs just 'Author A'.
    Also strips middle initials: 'Robert T. Kiyosaki' → 'Robert Kiyosaki'
    """
    first_author = author.split(",")[0].strip()
    # Remove single-letter middle initials (e.g. "T." -> "")
    parts = [p for p in first_author.split() if not re.match(r"^[A-Z]\.$", p)]
    return " ".join(parts)


def build_cache_key(title, author, genre_1, genre_2, goal, tone,
                    reading_time, language="en"):
    norm_title  = _normalize_title(title)
    norm_author = _normalize_author(author)
    raw = f"{norm_title}_{norm_author}_{genre_1}_{genre_2}_{goal}_{tone}_{reading_time}_{language}"
    key = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    return key


def get_cached_summary(cache_key):

    conn   = get_connection()
    cursor = get_cursor(conn)
    cursor.execute(
        "SELECT * FROM summaries WHERE cache_key = %s", (cache_key,)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def save_summary(book_id, result, cache_key, language="en"):
    conn   = get_connection()
    cursor = get_cursor(conn)

    cursor.execute("""
        INSERT INTO summaries
        (book_id, language, whats_inside, youll_learn,
         key_points, about_author, quote, conclusion, cache_key)
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)
        ON CONFLICT (book_id, language, cache_key)
            DO UPDATE SET
                whats_inside = EXCLUDED.whats_inside,
                youll_learn  = EXCLUDED.youll_learn,
                key_points   = EXCLUDED.key_points,
                about_author = EXCLUDED.about_author,
                quote        = EXCLUDED.quote,
                conclusion   = EXCLUDED.conclusion
        RETURNING id
    """, (
        book_id,
        language,
        result.get("whats_inside", ""),
        json.dumps(result.get("youll_learn", [])),
        json.dumps(result.get("key_points",  [])),
        result.get("about_author", ""),
        result.get("quote", ""),
        result.get("conclusion", ""),
        cache_key,
    ))

    summary_id = cursor.fetchone()["id"]
    conn.commit()
    conn.close()
    return summary_id


def get_full_result(cached, original_result_meta):
    key_points  = cached["key_points"]
    youll_learn = cached["youll_learn"]

    if isinstance(key_points, str):
        key_points = json.loads(key_points)
    if isinstance(youll_learn, str):
        youll_learn = json.loads(youll_learn)

    return {
        "whats_inside":  cached["whats_inside"],
        "youll_learn":   youll_learn,
        "key_points":    key_points,
        "about_author":  cached["about_author"],
        "quote":         cached["quote"],
        "conclusion":    cached.get("conclusion", ""),
        "genre":          original_result_meta.get("genre", ""),
        "reading_time":   original_result_meta.get("reading_time", 10),
        "low_confidence": original_result_meta.get("low_confidence", False),
    }

def get_cached_key_point(book_id, reading_time, point_index, language):
    conn = get_connection()
    cursor = get_cursor(conn)
    try:
        cursor.execute("""
            SELECT * FROM key_point_details
            WHERE book_id      = %s
              AND reading_time = %s
              AND point_index  = %s
              AND language     = %s
        """, (book_id, reading_time, point_index, language))

        row = cursor.fetchone()
        return dict(row) if row else None

    finally:
        cursor.close()
        conn.close()


def save_key_point_detail(book_id, reading_time, point_index, title, detail_result, language):
    conn = get_connection()
    cursor = get_cursor(conn)

    try:
        cursor.execute("""
            INSERT INTO key_point_details
            (book_id, reading_time, point_index, title, full_detail, language)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (book_id, reading_time, point_index, language)
            DO UPDATE SET 
                full_detail = EXCLUDED.full_detail,
                title       = EXCLUDED.title
            RETURNING id
        """, (
            book_id,
            reading_time,
            point_index,
            title,
            json.dumps(detail_result),
            language,
        ))

        row = cursor.fetchone()
        conn.commit()

        return row["id"] if row else None

    except Exception as e:
        conn.rollback()
        raise e

    finally:
        cursor.close()
        conn.close()


        




def parse_key_point_detail(cached_row):
    """
    Extract the full_detail JSONB from a key_point_details DB row.
    Returns a dict with: deep_explanation
    """
    full_detail = cached_row["full_detail"]
    if isinstance(full_detail, str):
        full_detail = json.loads(full_detail)
    return full_detail


# ─────────────────────────────────────────────────────────────────────────────
# Book saving — unchanged
# ─────────────────────────────────────────────────────────────────────────────

def save_book(book_data):
    """
    Insert a book into the books table if it does not already exist.
    Returns book_id whether newly inserted or already existing.
    """
    conn   = get_connection()
    cursor = get_cursor(conn)

    norm_title  = _normalize_title(book_data["title"])
    norm_author = _normalize_author(book_data.get("author", ""))

    cursor.execute(
        "SELECT id FROM books WHERE title = %s AND author = %s",
        (norm_title, norm_author)
    )
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return existing["id"]

    cursor.execute("""
        INSERT INTO books
        (title, author, genre, cover_image, description, published_year)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
    norm_title,
    norm_author,
    book_data.get("genre", ""),
    book_data.get("cover_image", ""),
    book_data.get("description", ""),
    book_data.get("published_year", ""),
))
    book_id = cursor.fetchone()["id"]
    conn.commit()
    conn.close()
    return book_id


# ─────────────────────────────────────────────────────────────────────────────
# Chat history — CHANGED to match your new chat_history table structure
# Your new table has: user_message, ai_response instead of action column
# ─────────────────────────────────────────────────────────────────────────────

def save_chat_history(user_id, book_id, summary_id, user_message="", ai_response=""):
    """
    Log to chat_history table.
    CHANGED: your new table uses user_message + ai_response instead of action.
    """
    conn   = get_connection()
    cursor = get_cursor(conn)
    cursor.execute("""
        INSERT INTO chat_history
        (user_id, book_id, summary_id, user_message, ai_response)
        VALUES (%s, %s, %s, %s, %s)
    """, (user_id, book_id, summary_id, user_message, ai_response))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# History — CHANGED: no rating column in new summaries table
# ─────────────────────────────────────────────────────────────────────────────

def get_user_history(user_id):
    """
    Fetch all past summaries for a user for the history page.
    CHANGED: joined through chat_history since summaries no longer has user_id.
    Deduplicates by summary id so each book appears once.
    """
    conn   = get_connection()
    cursor = get_cursor(conn)
    cursor.execute("""
        SELECT DISTINCT ON (s.id)
               s.id, b.title, b.author,
               s.whats_inside, s.language, s.created_at
        FROM chat_history ch
        JOIN summaries s ON ch.summary_id = s.id
        JOIN books b     ON s.book_id     = b.id
        WHERE ch.user_id = %s
        ORDER BY s.id, s.created_at DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]