from dotenv import load_dotenv
load_dotenv()
import os

print(f"✅ POSTHOG_API_KEY loaded: {os.environ.get('POSTHOG_API_KEY', 'NOT FOUND')[:20]}...")

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from user import register_user, login_user, get_user_by_email, get_user_by_id, set_user_premium_by_email
from secrets import token_urlsafe
from datetime import datetime, timedelta

from preferences import (save_preferences, get_preferences,
                          GOALS, BACKGROUNDS, STYLES, TONES, GENRES,
                          READING_TIMES, LANGUAGES, LANGUAGE_NAMES)

from Books_api import search_book, get_book_suggestions
from recommendations import get_personalized_suggestions
from firebase_auth import handle_google_login
from llm import generate_summary, generate_key_point_detail

from cache import (build_cache_key, get_cached_summary, save_summary,
                   get_full_result, save_book, save_chat_history,
                   get_user_history, get_cached_key_point,
                   save_key_point_detail, parse_key_point_detail)

import json
from flask import jsonify
from db import get_connection, get_cursor
from werkzeug.security import generate_password_hash

from analytics import (
    track_signup,
    track_login,
    track_language_selected,
    track_book_searched,
    track_book_selected,
    track_summary_success,
    track_summary_failed,
    track_summary_viewed,
    track_keypoint_viewed,
    track_preferences_saved,
    start_timer,
    end_timer,
)

import stripe
stripe.api_key = os.environ.get("SECRET_KEY_stripe")

print("POSTHOG KEY:", os.environ.get("POSTHOG_API_KEY", "NOT FOUND"))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fallback-dev-key")

@app.context_processor
def inject_globals():
    return {
        "firebase_api_key": os.environ.get("FIREBASE_API_KEY", ""),
        "firebase_auth_domain": os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
        "firebase_project_id": os.environ.get("FIREBASE_PROJECT_ID", ""),
        "posthog_key": os.environ.get("POSTHOG_API_KEY", ""),
    }


@app.route("/auth/google", methods=["POST"])
def google_auth():
    data = request.get_json()

    full_name  = data.get("name", "").strip()
    email      = data.get("email", "").strip()
    google_uid = data.get("google_uid", "").strip()

    if not full_name or not email or not google_uid:
        return jsonify({"error": "Missing required fields"}), 400

    result = handle_google_login(full_name, email, google_uid)

    if result is None:
        return jsonify({"error": "Failed to create account"}), 500

    session["user_id"]   = result["user_id"]
    session["user_name"] = result["full_name"]
    session["user_email"] = email
    session["is_premium"] = result.get("is_premium", False)
    

    if result.get("is_new"):
        track_signup(result["user_id"], result["full_name"], email)
    else:
        track_login(result["user_id"], email)

    if result.get("is_new"):
        return jsonify({"redirect": url_for("onboarding")})
    else:
        return jsonify({"redirect": url_for("books")})

TRANSLATIONS = {
    "en": {
        "whats_inside":  "What's Inside?",
        "youll_learn":   "You Will Learn",
        "key_points":    "Key Points",
        "conclusion":    "Conclusion",
        "about_author":  "About the Author",
        "quote":         "Memorable Quote",
        "genre":         "Genre",
        "more_books":    "More Books Like This",
        "read_detail":   "Read Full Detail →",
    },
    "hi": {
        "whats_inside":  "अंदर क्या है?",
        "youll_learn":   "आप क्या सीखेंगे",
        "key_points":    "मुख्य बिंदु",
        "conclusion":    "निष्कर्ष",
        "about_author":  "लेखक के बारे में",
        "quote":         "यादगार उद्धरण",
        "genre":         "शैली",
        "more_books":    "इस तरह की और किताबें",
        "read_detail":   "पूरा विवरण पढ़ें →",
    },
    "es": {
        "whats_inside":  "¿Qué hay dentro?",
        "youll_learn":   "Aprenderás",
        "key_points":    "Puntos Clave",
        "conclusion":    "Conclusión",
        "about_author":  "Sobre el Autor",
        "quote":         "Cita Memorable",
        "genre":         "Género",
        "more_books":    "Más Libros Como Este",
        "read_detail":   "Leer detalle completo →",
    },
}


@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("books"))
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not name or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for("register"))

        user_id = register_user(name, email, password)
        if user_id is None:
            flash("Email already exists. Please login.", "error")
            return redirect(url_for("register"))

        session["user_id"]   = user_id
        session["user_name"] = name
        session["user_email"] = email
        session["is_premium"] = False  

        track_signup(user_id, name, email)

        # Redirect to pricing after registration
        return redirect(url_for("pricing"))
    
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not email or not password:
            flash("Email and password are required.", "error")
            return redirect(url_for("login"))

        user = login_user(email, password)
        if user is None:
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

        session["user_id"]   = user["id"]
        session["user_name"] = user["full_name"]
        session["user_email"] = user["email"]
        session["is_premium"] = user.get("is_premium", False)

        track_login(user["id"], email)

        # Redirect to pricing if not premium
        if not session.get("is_premium"):
            return redirect(url_for("pricing"))

        prefs = get_preferences(user["id"])
        if not prefs:
            return redirect(url_for("onboarding"))
        return redirect(url_for("books"))

    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()

        if not email:
            flash("Please enter your email address.", "error")
            return redirect(url_for("forgot_password"))

        try:
            from firebase_admin import auth as firebase_auth
            firebase_auth.generate_password_reset_link(email)
            print(f"✅ Firebase reset email sent to {email}")
        except Exception as e:
            print(f"⚠️ Firebase reset error: {e}")

        flash("If that email exists, you'll receive a reset link shortly.", "success")
        return redirect(url_for("login"))

    return render_template("forgot_password.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    token = request.args.get("token", "").strip()

    if not token:
        flash("Invalid reset link.", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        new_password     = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not new_password or not confirm_password:
            flash("Please fill in all fields.", "error")
            return redirect(url_for("reset_password", token=token))

        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("reset_password", token=token))

        if len(new_password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for("reset_password", token=token))

        conn   = get_connection()
        cursor = get_cursor(conn)
        cursor.execute(
            "SELECT * FROM users WHERE reset_token = %s AND reset_expires > %s",
            (token, datetime.now())
        )
        user = cursor.fetchone()

        if not user:
            flash("Invalid or expired reset link.", "error")
            conn.close()
            return redirect(url_for("forgot_password"))

        firebase_ok = True
        try:
            from firebase_admin import auth as firebase_auth
            if user["firebase_uid"]:
                firebase_auth.update_user(user["firebase_uid"], password=new_password)
                print(f"✅ Firebase password updated for {user['email']}")
        except Exception as e:
            print(f"⚠️ Firebase password update failed: {e}")
            firebase_ok = False
            flash("Password reset failed. Please try again later.", "error")
            conn.close()
            return redirect(url_for("reset_password", token=token))

        if firebase_ok:
            password_hash = generate_password_hash(new_password)
            try:
                cursor.execute(
                    "UPDATE users SET password_hash = %s, reset_token = NULL, reset_expires = NULL WHERE id = %s",
                    (password_hash, user["id"])
                )
                conn.commit()
                print(f"✅ Local password updated for user {user['id']}")
            except Exception as e:
                print(f"❌ Error updating local password: {e}")
                flash("An error occurred. Please try again.", "error")
                conn.close()
                return redirect(url_for("reset_password", token=token))
            finally:
                conn.close()

            flash("Password reset successful! Please login with your new password.", "success")
            return redirect(url_for("login"))

    return render_template("reset_password.html", token=token)


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("login"))


@app.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        goal         = request.form.get("goal", "").strip()
        background   = request.form.get("background", "").strip()
        style        = request.form.get("style", "").strip()
        tone         = request.form.get("tone", "").strip()
        genres       = request.form.getlist("genres")
        reading_time = request.form.get("reading_time", "10").strip()
        language     = request.form.get("language", "en").strip()

        if not goal:
            flash("Please select a reading goal.", "error")
            return redirect(url_for("onboarding"))
        if not background:
            flash("Please select your background.", "error")
            return redirect(url_for("onboarding"))
        if not style:
            flash("Please select a summary style.", "error")
            return redirect(url_for("onboarding"))
        if not tone:
            flash("Please select a tone.", "error")
            return redirect(url_for("onboarding"))
        if not reading_time:
            flash("Please select a reading time.", "error")
            return redirect(url_for("onboarding"))
        if not language or language not in LANGUAGE_NAMES:
            flash("Please select a language.", "error")
            return redirect(url_for("onboarding"))

        if len(genres) < 1:
            flash("Please select at least one genre.", "error")
            return redirect(url_for("onboarding"))

        reading_time = int(reading_time)

        track_preferences_saved(
            session["user_id"],
            goal, background, style, tone,
            genres, reading_time, language
        )

        save_preferences(
            session["user_id"],
            goal, background, style, tone,
            genres[0], genres[1] if len(genres) > 1 else genres[0],
            reading_time, language
        )
        # Redirect to pricing if not premium
        if not session.get("is_premium"):
            return redirect(url_for("pricing"))
        return redirect(url_for("books"))

    prefs = get_preferences(session["user_id"])
    return render_template(
        "onboarding.html",
        prefs=prefs,
        goals=GOALS,
        backgrounds=BACKGROUNDS,
        styles=STYLES,
        tones=TONES,
        genres=GENRES,
        reading_times=READING_TIMES,
        languages=LANGUAGES
    )


@app.route("/books", methods=["GET", "POST"])
def books():
    if "user_id" not in session:
        return redirect(url_for("login"))
    # Redirect to pricing if not premium
    if not session.get("is_premium"):
        return redirect(url_for("pricing"))

    prefs = get_preferences(session["user_id"])
    suggestions = {"genre_1": [], "genre_2": []}
    search_results = []
    query = None

    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "search":
            title  = request.form.get("title", "").strip()
            author = request.form.get("author", "").strip()
            query  = f"{title} {author}".strip()
            track_book_searched(session["user_id"], query)
            book = search_book(query)
            if book:
                # Save book data and redirect to summary directly
                session["book_data"] = book
                track_book_selected(session["user_id"], book["title"], book["author"])
                book_id = save_book(book)
                reading_time = prefs.get("reading_time", 10) if prefs else 10
                return redirect(url_for("summary", book_id=book_id, reading_time=reading_time))
            else:
                flash("No book found for your search.", "error")
                return redirect(url_for("books"))

        elif action == "suggest":
            genre_1 = prefs.get("genre_1", "")
            genre_2 = prefs.get("genre_2", "")
            # Build genre list (skip empty strings)
            genres = [g for g in [genre_1, genre_2] if g]
            # Hybrid DB-first + API recommendations
            personalized = get_personalized_suggestions(genres)
            suggestions["genre_1"] = personalized.get(genre_1, [])
            suggestions["genre_2"] = personalized.get(genre_2, [])

    # Insert last summarized book at the start of the relevant genre's suggestions if it matches
    last_book = session.get("last_summarized_book")
    if last_book and last_book.get("genre"):
        for genre_key in ["genre_1", "genre_2"]:
            user_genre = prefs.get(genre_key, "")
            if user_genre and last_book["genre"].lower() == user_genre.lower():
                # Only add if not already present (by title and author)
                already = any(
                    b["title"].lower() == last_book["title"].lower() and b["author"].lower() == last_book["author"].lower()
                    for b in suggestions[genre_key]
                )
                if not already:
                    suggestions[genre_key] = [last_book] + suggestions[genre_key]
                # Always keep only 4 books per genre
                suggestions[genre_key] = suggestions[genre_key][:4]

    return render_template("books.html", prefs=prefs, suggestions=suggestions, search_results=search_results, query=query)


# @app.route("/select-book", methods=["POST"])
# def select_book():
#     if "user_id" not in session:
#         return redirect(url_for("login"))

#     # Try to get all book data from form (search result selection)
#     title          = request.form.get("title", "").strip()
#     author         = request.form.get("author", "").strip()
#     description    = request.form.get("description", "").strip()
#     genre          = request.form.get("genre", "").strip()
#     published_year = request.form.get("published_year", "").strip()
#     cover_image    = request.form.get("cover_image", "").strip()

#     if not title:
#         flash("No book selected.", "error")
#         return redirect(url_for("books"))

#     prefs        = get_preferences(session["user_id"])
#     reading_time = prefs.get("reading_time", 10) if prefs else 10

#     # If description or genre is missing, fallback to search_book
#     if description or genre or cover_image:
#         book_data = {
#             "title": title,
#             "author": author,
#             "description": description,
#             "genre": genre,
#             "published_year": published_year,
#             "cover_image": cover_image,
#         }
#     else:
#         book_data = search_book(f"{title} {author}")
#         if not book_data:
#             book_data = {"title": title, "author": author}

#     session["book_data"] = book_data
#     track_book_selected(session["user_id"], title, author)
#     book_id = save_book(session["book_data"])
#     return redirect(url_for("summary", book_id=book_id, reading_time=reading_time))


@app.route("/select-book", methods=["POST"])
def select_book():
    if "user_id" not in session:
        return redirect(url_for("login"))

    # ── GATE: Free plan limit ──────────────────────────────────────
    if not session.get("is_premium"):
        conn = get_connection()
        cursor = get_cursor(conn)
        cursor.execute(
            "SELECT COUNT(*) FROM summaries WHERE user_id = %s",
            (session["user_id"],)
        )
        count = cursor.fetchone()[0]
        conn.close()

        if count >= 1:
            flash("You've used your free summary. Upgrade to generate unlimited summaries.", "error")
            return redirect(url_for("pricing"))
    # ──────────────────────────────────────────────────────────────

    title          = request.form.get("title", "").strip()
    author         = request.form.get("author", "").strip()
    description    = request.form.get("description", "").strip()
    genre          = request.form.get("genre", "").strip()
    published_year = request.form.get("published_year", "").strip()
    cover_image    = request.form.get("cover_image", "").strip()

    if not title:
        flash("No book selected.", "error")
        return redirect(url_for("books"))

    prefs        = get_preferences(session["user_id"])
    reading_time = prefs.get("reading_time", 10) if prefs else 10

    if description or genre or cover_image:
        book_data = {
            "title": title,
            "author": author,
            "description": description,
            "genre": genre,
            "published_year": published_year,
            "cover_image": cover_image,
        }
    else:
        book_data = search_book(f"{title} {author}")
        if not book_data:
            book_data = {"title": title, "author": author}

    session["book_data"] = book_data
    track_book_selected(session["user_id"], title, author)
    book_id = save_book(session["book_data"])
    # Increment summary count for free users
    if not session.get("is_premium"):
        from user import increment_summary_count
        increment_summary_count(session["user_id"])
    return redirect(url_for("summary", book_id=book_id, reading_time=reading_time))




@app.route("/search", methods=["GET"])
def search():
    if "user_id" not in session:
        return redirect(url_for("login"))

    query = request.args.get("q", "").strip()
    if not query or len(query) > 100:
        flash("Please enter a valid search query.", "error")
        return redirect(url_for("books"))

    track_book_searched(session["user_id"], query)
    book = search_book(query)
    search_results = [book] if book else []
    prefs = get_preferences(session["user_id"])
    suggestions = {"genre_1": [], "genre_2": []}
    return render_template("books.html", prefs=prefs, suggestions=suggestions, search_results=search_results, query=query)


@app.route("/summary/<int:book_id>/<int:reading_time>", methods=["GET"])
def summary(book_id, reading_time):
    if "user_id" not in session:
        return redirect(url_for("login"))

    if reading_time not in READING_TIMES:
        flash("Invalid reading time.", "error")
        return redirect(url_for("books"))

    book_data = session.get("book_data", {})
    if not book_data:
        flash("No book data found. Please search again.", "error")
        return redirect(url_for("books"))

    prefs     = get_preferences(session["user_id"])
    lang_code = prefs.get("preferred_language", "en")
    lang_name = LANGUAGE_NAMES.get(lang_code, "English")
    labels    = TRANSLATIONS.get(lang_code, TRANSLATIONS["en"])

    cache_key = build_cache_key(
        book_data.get("title", ""),
        book_data.get("author", ""),
        prefs["genre_1"],
        prefs["genre_2"],
        prefs["goal"],
        prefs["tone"],
        reading_time,
        lang_code,
    )

    cached = get_cached_summary(cache_key)
    if cached:
        print(f"[cache] ✅ HIT  — '{book_data.get('title', '')}' served from DB cache (cache_key={cache_key})")
        result = get_full_result(cached, session.get("last_result_meta", {}))

        track_summary_success(
            session["user_id"],
            book_data["title"],
            book_data.get("author", ""),
            generation_time=0,
            from_cache=True,
            language=lang_code
        )

        return render_template("summary.html",
                               book=book_data,
                               result=result,
                               summary_id=cached["id"],
                               book_id=cached["book_id"],
                               reading_time=reading_time,
                               labels=labels,
                               prefs=prefs,
                               from_cache=True)

    print(f"[cache] ❌ MISS — '{book_data.get('title', '')}' not in cache, calling LLM...")
    t = start_timer()

    try:
        result = generate_summary(
            book_data["title"],
            book_data.get("author", ""),
            book_data.get("description", ""),
            prefs["profile_summary"],
            reading_time,
            lang_name,
        )
    except Exception as e:
        track_summary_failed(session["user_id"], book_data["title"], error=str(e))
        flash(f"Failed to generate summary: {str(e)}", "error")
        return redirect(url_for("books"))

    generation_time = end_timer(t)
    track_summary_success(
        session["user_id"],
        book_data["title"],
        book_data.get("author", ""),
        generation_time=generation_time,
        from_cache=False,
        language=lang_code
    )
    track_summary_viewed(
        session["user_id"],
        book_data["title"],
        book_data.get("author", ""),
        lang_code,
        reading_time
    )

    session["last_result_meta"] = {
        "genre":          result.get("genre", ""),
        "reading_time":   result.get("reading_time", reading_time),
        "low_confidence": result.get("low_confidence", False),
    }

    book_id    = save_book(book_data)
    summary_id = save_summary(book_id, result, cache_key, lang_code)

    # Store the last summarized book and its genre in the session
    session["last_summarized_book"] = {
        "title": book_data.get("title", ""),
        "author": book_data.get("author", ""),
        "description": book_data.get("description", ""),
        "genre": result.get("genre", ""),
        "published_year": book_data.get("published_year", ""),
        "cover_image": book_data.get("cover_image", "")
    }

    save_chat_history(
        session["user_id"], book_id, summary_id,
        user_message=f"Generated summary for '{book_data['title']}'",
        ai_response="Summary generated successfully"
    )

    session["current_book_id"] = book_id

    return render_template("summary.html",
                           book=book_data,
                           result=result,
                           summary_id=summary_id,
                           book_id=book_id,
                           reading_time=reading_time,
                           labels=labels,
                           prefs=prefs,
                           from_cache=False)


@app.route("/keypoint/<int:book_id>/<int:reading_time>/<int:point_index>")
def keypoint(book_id, reading_time, point_index):
    if "user_id" not in session:
        return redirect(url_for("login"))

    if point_index < 0 or point_index > 10:
        flash("Invalid key point.", "error")
        return redirect(url_for("books"))

    if reading_time not in READING_TIMES:
        flash("Invalid reading time.", "error")
        return redirect(url_for("books"))

    book_data = session.get("book_data", {})
    prefs     = get_preferences(session["user_id"])

    lang_code = prefs.get("preferred_language", "en")
    lang_name = LANGUAGE_NAMES.get(lang_code, "English")
    labels    = TRANSLATIONS.get(lang_code, TRANSLATIONS["en"])

    cache_key = build_cache_key(
        book_data.get("title", ""),
        book_data.get("author", ""),
        prefs["genre_1"],
        prefs["genre_2"],
        prefs["goal"],
        prefs["tone"],
        reading_time,
        lang_code,
    )

    cached_summary = get_cached_summary(cache_key)
    if not cached_summary:
        flash("Summary not found. Please generate the summary first.", "error")
        return redirect(url_for("books"))

    key_points = cached_summary["key_points"]
    if isinstance(key_points, str):
        key_points = json.loads(key_points)

    if point_index >= len(key_points):
        flash("Key point not found.", "error")
        return redirect(url_for("summary", book_id=book_id, reading_time=reading_time))

    this_kp = key_points[point_index]

    cached_kp = get_cached_key_point(book_id, reading_time, point_index, lang_code)
    if cached_kp:
        detail = parse_key_point_detail(cached_kp)

        track_keypoint_viewed(
            session["user_id"],
            book_data.get("title", ""),
            point_index,
            generation_time=0,
            from_cache=True,
            language=lang_code
        )

        return render_template("keypoint.html",
                               book=book_data,
                               key_point=this_kp,
                               detail=detail,
                               point_index=point_index,
                               total_points=len(key_points),
                               book_id=book_id,
                               reading_time=reading_time,
                               labels=labels,
                               from_cache=True)

    t = start_timer()

    try:
        detail = generate_key_point_detail(
            book_data.get("title", ""),
            book_data.get("author", ""),
            this_kp["title"],
            this_kp["detail"],
            lang_name,
        )
    except Exception as e:
        flash(f"Failed to generate key point detail: {str(e)}", "error")
        return redirect(url_for("summary", book_id=book_id, reading_time=reading_time))

    generation_time = end_timer(t)
    track_keypoint_viewed(
        session["user_id"],
        book_data.get("title", ""),
        point_index,
        generation_time=generation_time,
        from_cache=False,
        language=lang_code
    )

    save_key_point_detail(
        book_id, reading_time, point_index,
        this_kp["title"], detail, lang_code
    )

    return render_template("keypoint.html",
                           book=book_data,
                           key_point=this_kp,
                           detail=detail,
                           point_index=point_index,
                           total_points=len(key_points),
                           book_id=book_id,
                           reading_time=reading_time,
                           labels=labels,
                           from_cache=False)


@app.route("/genre-books/<genre>")
def genre_books(genre):
    if "user_id" not in session:
        return redirect(url_for("login"))

    if not genre or len(genre) > 50:
        flash("Invalid genre.", "error")
        return redirect(url_for("books"))

    books_list = get_book_suggestions(genre, genre, f"best {genre} books", count=6)

    return render_template("genre_books.html",
                           genre=genre,
                           books=books_list)


@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect(url_for("login"))

    past_summaries = get_user_history(session["user_id"])
    return render_template("history.html", summaries=past_summaries)


@app.route("/edit-preferences", methods=["GET", "POST"])
def edit_preferences():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        goal         = request.form.get("goal", "").strip()
        background   = request.form.get("background", "").strip()
        style        = request.form.get("style", "").strip()
        tone         = request.form.get("tone", "").strip()
        genres       = request.form.getlist("genres")
        reading_time = request.form.get("reading_time", "10").strip()
        language     = request.form.get("language", "en").strip()

        if not goal or not background or not style or not tone or not reading_time:
            flash("All fields are required.", "error")
            return redirect(url_for("edit_preferences"))

        if len(genres) != 2:
            flash("Please select exactly 2 genres.", "error")
            return redirect(url_for("edit_preferences"))

        try:
            reading_time = int(reading_time)
        except ValueError:
            flash("Invalid reading time selected.", "error")
            return redirect(url_for("edit_preferences"))

        save_preferences(session["user_id"], goal, background, style, tone, genres[0], genres[1], reading_time, language)
        flash("Preferences updated!", "success")
        return redirect(url_for("books"))

    prefs = get_preferences(session["user_id"]) if "user_id" in session else None
    return render_template(
        "edit_preferences.html",
        prefs=prefs,
        goals=GOALS,
        backgrounds=BACKGROUNDS,
        styles=STYLES,
        tones=TONES,
        genres=GENRES,
        reading_times=READING_TIMES,
        languages=LANGUAGES
    )

PRICE_IDS = {
    "monthly": "price_1TGzWVBpSGQbWzE97BqBOiX2",
    "yearly":  "price_1TGzlzBpSGQbWzE9yYI4eWEF",
}

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    data = request.get_json() or {}
    user_email = data.get("email")
    plan = data.get("plan", "monthly")  # read plan from frontend

    if not user_email:
        return jsonify({"error": "Email required"}), 400

    price_id = PRICE_IDS.get(plan)
    if not price_id:
        return jsonify({"error": "Invalid plan"}), 400

    # Set mode based on plan type
    if plan in ["monthly", "yearly"]:
        checkout_mode = "subscription"
    else:
        checkout_mode = "payment"

    try:
        session = stripe.checkout.Session.create(
            line_items=[{"price": price_id, "quantity": 1}],
            mode=checkout_mode,
            success_url="https://yourdomain.com/success",
            cancel_url="https://yourdomain.com/pricing",
        )
        return jsonify({"url": session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("stripe-signature")
    endpoint_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    event = None
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except Exception as e:
        print(f"Webhook error: {e}")
        return "", 400

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        email = session_obj.get("customer_email")
        if email:
            set_user_premium_by_email(email)
            print(f"✅ User {email} upgraded to premium.")
    return "", 200


@app.route("/pricing", methods=["GET", "POST"])
def pricing():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if request.method == "POST":
        plan = request.form.get("plan") or request.json.get("plan") if request.is_json else None
        if plan == "free":
            # Optionally, set user as non-premium (already default)
            session["is_premium"] = False
            prefs = get_preferences(session["user_id"])
            if not prefs:
                return redirect(url_for("onboarding"))
            else:
                return redirect(url_for("books"))
        # After plan selection/payment, check if onboarding is complete
        prefs = get_preferences(session["user_id"])
        if not prefs:
            return redirect(url_for("onboarding"))
        else:
            return redirect(url_for("books"))
    return render_template("pricing.html")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)