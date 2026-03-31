# import os
# import time
# import posthog

# # ── Initialize PostHog using official Flask approach ──────────────────────────
# posthog.project_api_key = os.environ.get("POSTHOG_API_KEY", "")
# posthog.host = os.environ.get("POSTHOG_HOST", "https://us.posthog.com")

# # Auto-disable if no API key found so app never crashes
# if not os.environ.get("POSTHOG_API_KEY"):
#     posthog.disabled = True
# # ─────────────────────────────────────────────────────────────────────────────


# # ── Helper ────────────────────────────────────────────────────────────────────
# def _capture(user_id, event, properties=None):
#     """
#     Central capture function.
#     Wrapped in try/except so PostHog NEVER crashes your app.
#     """
#     try:
#         posthog.capture(
#             distinct_id=str(user_id),
#             event=event,
#             properties=properties or {},
#         )
#     except Exception as e:
#         print(f"Error capturing {event}: {e}")


# # ── Group 1: User Behavior ────────────────────────────────────────────────────

# def track_signup(user_id, name, email):
#     """Fired when a new user registers."""
#     _capture(user_id, "user_signed_up", {
#         "name":  name,
#         "email": 
#         posthog.identify(
#             distinct_id=str(user_id),
#             properties={
#                 "name":  name,
#                 "email": email,
#             }
#         )
#     except Exception as e:
#         print(f"Error identifying user: {e}")


# def track_login(user_id, email):
#     """Fired when a user logs in."""
#     _capture(user_id, "user_logged_in", {
#         "email": email,
#     })


# def track_language_selected(user_id, language):
#     """Fired when user selects a language in onboarding or preferences."""
#     _capture(user_id, "language_selected", {
#         "language": language,
#     })


# def track_book_searched(user_id, title, author=None):
#     """Fired when user searches for a book."""
#     _capture(user_id, "book_searched", {
#         "title":  title,
#         "author": author or "not provided",
#     })


# def track_book_selected(user_id, title, author):
#     """Fired when user selects a book to summarize."""
#     _capture(user_id, "book_selected", {
#         "title":  title,
#         "author": author,
#     })


# # ── Group 2: AI Performance ───────────────────────────────────────────────────

# def track_summary_success(user_id, title, author, generation_time, from_cache, language):
#     """Fired when summary is successfully generated or served from cache."""
#     _capture(user_id, "summary_generated_success", {
#         "title":           title,
#         "author":          author,
#         "generation_time": round(generation_time, 2),
#         "from_cache":      from_cache,
#         "language":        language,
#     })



# def track_keypoint_viewed(user_id, book_title, point_index, generation_time, from_cache, language):
#     """Fired when user opens a key point deep dive."""
#     _capture(user_id, "keypoint_viewed", {
#         "book_title":      book_title,
#         "point_index":     point_index,
#         "generation_time": round(generation_time, 2),
#         "from_cache":      from_cache,
#         "language":        language,
#     })


# # ── Group 3: Engagement ───────────────────────────────────────────────────────

# def track_summary_viewed(user_id, title, author, language, reading_time):
#     """Fired when user lands on the summary page."""
#     _capture(user_id, "summary_viewed", {
#         "title":        title,
#         "author":       author,
#         "language":     language,
#         "reading_time": reading_time,
#     })


# def track_preferences_saved(user_id, goal, genre_1, genre_2, reading_time, language):
#     """Fired when user saves onboarding or edited preferences."""
#     _capture(user_id, "preferences_saved", {
#         "goal":         goal,
#         "genre_1":      genre_1,
#         "genre_2":      genre_2,
#         "reading_time": reading_time,
#         "language":     language,
#     })


# # ── Timer Utility ─────────────────────────────────────────────────────────────

# def start_timer():
#     """Call this before Gemini generation. Returns start time."""
#     return time.time()


# def end_timer(start_time):
#     """Call this after Gemini generation. Returns elapsed seconds."""
#     return round(time.time() - start_time, 2)


import os
import time
import requests
import json

# Get API key from environment
POSTHOG_API_KEY = os.environ.get("POSTHOG_API_KEY", "")
POSTHOG_HOST = os.environ.get("POSTHOG_HOST", "https://us.posthog.com")

if POSTHOG_API_KEY:
    print(f"✅ PostHog API key found: {POSTHOG_API_KEY[:20]}...")
else:
    print("⚠️  PostHog API key NOT found")


# ── Helper function to send events directly via HTTP ──────────────────────────
def _capture(user_id, event, properties=None):
    """
    Send event directly to PostHog via HTTP API.
    This bypasses any SDK issues.
    """
    if not POSTHOG_API_KEY:
        print(f"⚠️  Skipping event '{event}' - No API key configured")
        return
    
    try:
        payload = {
            "api_key": POSTHOG_API_KEY,
            "event": event,
            "distinct_id": str(user_id),
            "properties": properties or {},
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime()),
        }
        
        response = requests.post(
            f"{POSTHOG_HOST}/capture/",
            json=payload,
            timeout=5
        )
        
        if response.status_code in [200, 201]:
            print(f"✅ Event captured: {event}")
        else:
            print(f"❌ Error capturing {event}: {response.status_code} - {response.text}")
    
    except Exception as e:
        print(f"❌ Error capturing {event}: {e}")


# ── Group 1: User Behavior ────────────────────────────────────────────────────

def track_signup(user_id, name, email):
    """Fired when a new user registers."""
    _capture(user_id, "user_signed_up", {
        "name":  name,
        "email": email,
    })


def track_login(user_id, email):
    """Fired when a user logs in."""
    _capture(user_id, "user_logged_in", {
        "email": email,
    })


def track_language_selected(user_id, language):
    """Fired when user selects a language in onboarding or preferences."""
    _capture(user_id, "language_selected", {
        "language": language,
    })


def track_book_searched(user_id, title, author=None):
    """Fired when user searches for a book."""
    _capture(user_id, "book_searched", {
        "title":  title,
        "author": author or "not provided",
    })


def track_book_selected(user_id, title, author):
    """Fired when user selects a book to summarize."""
    _capture(user_id, "book_selected", {
        "title":  title,
        "author": author,
    })


# ── Group 2: AI Performance ───────────────────────────────────────────────────

def track_summary_success(user_id, title, author, generation_time, from_cache, language):
    """Fired when summary is successfully generated or served from cache."""
    _capture(user_id, "summary_generated_success", {
        "title":           title,
        "author":          author,
        "generation_time": round(generation_time, 2),
        "from_cache":      from_cache,
        "language":        language,
    })


def track_summary_failed(user_id, title, error):
    """Fired when summary generation fails."""
    _capture(user_id, "summary_generated_failed", {
        "title": title,
        "error": str(error),
    })


def track_keypoint_viewed(user_id, book_title, point_index, generation_time, from_cache, language):
    """Fired when user opens a key point deep dive."""
    _capture(user_id, "keypoint_viewed", {
        "book_title":      book_title,
        "point_index":     point_index,
        "generation_time": round(generation_time, 2),
        "from_cache":      from_cache,
        "language":        language,
    })


# ── Group 3: Engagement ───────────────────────────────────────────────────────

def track_summary_viewed(user_id, title, author, language, reading_time):
    """Fired when user lands on the summary page."""
    _capture(user_id, "summary_viewed", {
        "title":        title,
        "author":       author,
        "language":     language,
        "reading_time": reading_time,
    })


def track_preferences_saved(user_id, goal, background, style, tone, genres, reading_time, language):
    """Fired when user saves onboarding or edited preferences."""
    genre_1 = genres[0] if len(genres) > 0 else None
    genre_2 = genres[1] if len(genres) > 1 else genre_1
    _capture(user_id, "preferences_saved", {
        "goal":         goal,
        "background":   background,
        "style":        style,
        "tone":         tone,
        "genre_1":      genre_1,
        "genre_2":      genre_2,
        "reading_time": reading_time,
        "language":     language,
    })


# ── Timer Utility ─────────────────────────────────────────────────────────────

def start_timer():
    """Call this before Gemini generation. Returns start time."""
    return time.time()


def end_timer(start_time):
    """Call this after Gemini generation. Returns elapsed seconds."""
    return round(time.time() - start_time, 2)