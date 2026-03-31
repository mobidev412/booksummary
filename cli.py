import os
import sys
import json

from db import test_connection
from user import register_user, login_user
from preferences import (
    save_preferences, get_preferences,
    GOALS, BACKGROUNDS, STYLES, TONES, GENRES,
)
from Books_api import search_book, get_book_suggestions
from llm import generate_summary, suggest_books
from cache import (
    build_cache_key, get_cached_summary, save_summary,
    save_book, save_chat_history, save_rating, get_user_history,
)



def clear():
    os.system("cls" if os.name == "nt" else "clear")


def banner():
    print("\n" + "=" * 50)
    print(" AI Book Summary Generator")
    print("=" * 50)


def choose(prompt_text, options, multi=False, max_select=2):

    print(f"\n{prompt_text}")
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")

    while True:
        if multi:
            raw = input(f"\nEnter {max_select} numbers separated by comma (e.g. 1,3): ").strip()
            try:
                indices = [int(x.strip()) for x in raw.split(",")]
                if len(indices) != max_select:
                    print(f" Please select exactly {max_select} options.")
                    continue
                if any(i < 1 or i > len(options) for i in indices):
                    print(f" Numbers must be between 1 and {len(options)}.")
                    continue
                return [options[i - 1] for i in indices]
            except ValueError:
                print(" Invalid input. Try again.")
        else:
            raw = input("\nEnter choice number: ").strip()
            try:
                idx = int(raw)
                if 1 <= idx <= len(options):
                    return options[idx - 1]
                print(f" Please enter a number between 1 and {len(options)}.")
            except ValueError:
                print(" Invalid input. Try again.")


def press_enter():
    input("\nPress Enter to continue...")



def screen_welcome():
    banner()
    print("\n  1. Register")
    print("  2. Login")
    print("  3. Exit")
    while True:
        choice = input("\nEnter choice: ").strip()
        if choice in ("1", "2", "3"):
            return choice
        print("  Please enter 1, 2, or 3.")


def screen_register():
    print("\n--- REGISTER ---")
    name = input("Full Name   : ").strip()
    email = input("Email       : ").strip()
    password = input("Password    : ").strip()

    if not name or not email or not password:
        print(" All fields are required.")
        return None

    user_id = register_user(name, email, password)
    if user_id is None:
        print("Email already exists. Please login instead.")
        return None

    print(f"\n Account created! Welcome, {name}.")
    return user_id


def screen_login():
    print("\n--- LOGIN ---")
    email = input("Email    : ").strip()
    password = input("Password : ").strip()

    user = login_user(email, password)
    if user is None:
        print(" Invalid email or password.")
        return None

    print(f"\n Welcome back, {user['full_name']}!")
    return user["id"]


def screen_onboarding(user_id):
    print("\n--- ONBOARDING (Tell us about yourself) ---")

    goal       = choose("What is your reading goal?", GOALS)
    background = choose("What is your background?", BACKGROUNDS)
    style      = choose("Preferred summary style?", STYLES)
    tone       = choose("Preferred tone?", TONES)
    genres     = choose("Select exactly 2 genres:", GENRES, multi=True, max_select=2)

    profile = save_preferences(user_id, goal, background, style, tone, genres[0], genres[1])
    print(f"\n Preferences saved!")
    print(f"\n Your Profile:\n   {profile}")
    press_enter()
    return profile


def screen_book_menu(user_id):
    prefs = get_preferences(user_id)
    if not prefs:
        print("\n  No preferences found. Please complete onboarding first.")
        screen_onboarding(user_id)
        prefs = get_preferences(user_id)

    while True:
        banner()
        print(f"\nHello! Your genres: {prefs['genre_1']} & {prefs['genre_2']}")
        print("\n  1. Enter a book name")
        print("  2. Suggest a book based on my preferences")
        print("  3. View my previous summaries")
        print("  4. Update preferences")
        print("  5. Logout")

        choice = input("\nEnter choice: ").strip()

        if choice == "1":
            screen_manual_book(user_id, prefs)
        elif choice == "2":
            screen_suggest_book(user_id, prefs)
        elif choice == "3":
            screen_history(user_id)
        elif choice == "4":
            screen_onboarding(user_id)
            prefs = get_preferences(user_id)
        elif choice == "5":
            print("\n Logged out. Goodbye!")
            return
        else:
            print(" Invalid choice.")


def screen_manual_book(user_id, prefs):
    print("\n--- ENTER BOOK ---")
    title = input("Book title  : ").strip()
    author = input("Author (optional, press Enter to skip): ").strip()

    if not title:
        print(" Title cannot be empty.")
        return

    print("\n Searching Google Books API...")
    book_data = search_book(title, author if author else None)

    if not book_data:
        print(" Book not found in Google Books. Cannot generate summary to avoid inaccurate results.")
        print("  Try checking the spelling or adding the author name.")
        press_enter()
        return

    print(f"\nFound: '{book_data['title']}' by {book_data['author']}")
    screen_generate_summary(user_id, prefs, book_data)


def screen_suggest_book(user_id, prefs):
    print("\n Fetching suggestions based on your profile...")

    # First try Google Books API suggestions
    api_books = get_book_suggestions(prefs["genre_1"], prefs["genre_2"], prefs["goal"])

    # Also ask LLM for personalized suggestions
    print(" Getting AI-powered recommendations...")
    llm_books = suggest_books(prefs["profile_summary"], prefs["genre_1"], prefs["genre_2"])

    # Merge: LLM suggestions first (more personalized), then API results
    suggestions = []
    for b in llm_books:
        suggestions.append({
            "title":  b["title"],
            "author": b["author"],
            "reason": b.get("reason", "Recommended for your profile"),
            "source": "AI",
        })
    for b in api_books[:3]:
        suggestions.append({
            "title":  b["title"],
            "author": b["author"],
            "reason": f"Found in {prefs['genre_1']} & {prefs['genre_2']}",
            "source": "Google Books",
        })

    if not suggestions:
        print(" No suggestions available right now. Try entering a book manually.")
        press_enter()
        return

    print("\n Suggested Books:\n")
    for i, s in enumerate(suggestions, 1):
        print(f"  {i}. {s['title']} — {s['author']}")
        print(f"      {s['reason']}\n")

    while True:
        raw = input(f"Select a book (1-{len(suggestions)}) or 0 to go back: ").strip()
        try:
            idx = int(raw)
            if idx == 0:
                return
            if 1 <= idx <= len(suggestions):
                selected = suggestions[idx - 1]
                break
            print(f" Enter a number between 1 and {len(suggestions)}.")
        except ValueError:
            print(" Invalid input.")

    print(f"\n Fetching details for '{selected['title']}'...")
    book_data = search_book(selected["title"], selected["author"])

    if not book_data:
        # Use LLM suggestion data as fallback book_data
        book_data = {
            "title":          selected["title"],
            "author":         selected["author"],
            "description":    "",
            "genre":          f"{prefs['genre_1']}, {prefs['genre_2']}",
            "cover_image":    "",
            "published_year": "",
        }
        print("  Couldn't fetch full details. Generating summary from AI knowledge only.")

    screen_generate_summary(user_id, prefs, book_data)


def screen_generate_summary(user_id, prefs, book_data):
    """Core: check cache → generate → display → save → rate."""
    cache_key = build_cache_key(
        book_data["title"], book_data.get("author", ""),
        prefs["genre_1"], prefs["genre_2"],
        prefs["goal"], prefs["tone"],
    )

    cached = get_cached_summary(cache_key)
    if cached:
        print("\n⚡ Loaded from cache (no API call needed)!")
        display_summary(book_data, cached["summary_text"],
                        json.loads(cached["key_points"]),
                        json.loads(cached["takeaways"]),
                        cached["quote"])


        book_id = save_book(book_data)
        save_chat_history(user_id, book_id, cached["id"], "viewed_cached")
        screen_rate(cached["id"])
        return

    print("\n🤖 Generating your personalized summary...")
    print("⏳ Please wait (this may take 10–20 seconds)...\n")

    try:
        result = generate_summary(
            book_data["title"],
            book_data.get("author", ""),
            book_data.get("description", ""),
            prefs["profile_summary"],
        )
    except Exception as e:
        print(f" Failed to generate summary: {e}")
        press_enter()
        return

    book_id = save_book(book_data)
    summary_id = save_summary(
        user_id, book_id,
        result["summary_text"],
        result["key_points"],
        result["takeaways"],
        result["quote"],
        cache_key,
    )
    save_chat_history(user_id, book_id, summary_id, "generated")

  
    display_summary(book_data, result["summary_text"],
                    result["key_points"], result["takeaways"], result["quote"])


    if result["summary_text"].startswith("[LOW CONFIDENCE]"):
        print("\n  WARNING: The AI has limited knowledge of this book.")
        print("   Some details may be inaccurate. Use with caution.")

    print("\n Summary saved to your history!")
    screen_rate(summary_id)


def display_summary(book_data, summary_text, key_points, takeaways, quote):
    """Pretty-print the summary in Headway style."""
    title  = book_data.get("title", "Unknown")
    author = book_data.get("author", "Unknown")
    year   = book_data.get("published_year", "")

    print("\n" + "=" * 55)
    print(f"   {title.upper()}")
    print(f"     {author}" + (f" ({year})" if year else ""))
    print("=" * 55)

    print("\n SUMMARY:")
    clean = summary_text.replace("[LOW CONFIDENCE]", "").strip()
    words = clean.split()
    line, lines = [], []
    for w in words:
        line.append(w)
        if len(" ".join(line)) > 70:
            lines.append(" ".join(line[:-1]))
            line = [w]
    if line:
        lines.append(" ".join(line))
    for l in lines:
        print(f"  {l}")

    print("\n KEY IDEAS:")
    for kp in key_points:
        print(f"  • {kp}")

    print("\n ACTIONABLE TAKEAWAYS:")
    for ta in takeaways:
        print(f"  ✔  {ta}")

    if quote:
        print(f'\n QUOTE:\n  "{quote}"')

    print("\n" + "-" * 55)


def screen_rate(summary_id):
    while True:
        raw = input("\nRate this summary (1–5) or press Enter to skip: ").strip()
        if raw == "":
            return
        try:
            rating = int(raw)
            if 1 <= rating <= 5:
                save_rating(summary_id, rating)
                print(" Rating saved. Thank you!")
                return
            print("  Enter a number between 1 and 5.")
        except ValueError:
            print("  Invalid input.")


def screen_history(user_id):
    print("\n--- YOUR SUMMARY HISTORY ---")
    history = get_user_history(user_id)

    if not history:
        print("  No summaries generated yet.")
        press_enter()
        return

    for i, row in enumerate(history, 1):
        rating = f" {row['rating']}/5" if row["rating"] else "Not rated"
        print(f"  {i}. {row['title']} — {row['author']}  |  {rating}  |  {row['created_at'][:10]}")

    press_enter()



def main():
    if not test_connection():
        sys.exit(1)

    while True:
        clear()
        choice = screen_welcome()

        if choice == "1":
            user_id = screen_register()
            if user_id:
                screen_onboarding(user_id)
                screen_book_menu(user_id)

        elif choice == "2":
            user_id = screen_login()
            if user_id:
                prefs = get_preferences(user_id)
                if not prefs:
                    print("\n Let's set up your preferences first.")
                    screen_onboarding(user_id)
                screen_book_menu(user_id)

        elif choice == "3":
            print("\n Goodbye!")
            sys.exit(0)


if __name__ == "__main__":
    main()