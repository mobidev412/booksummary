from db import get_connection, get_cursor


def save_preferences(user_id, goal, background, style, tone,
                     genre_1, genre_2, reading_time,
                     language="en"):  
    profile_summary = (
        f"The user is a {background} who wants to {goal}. "
        f"They prefer a {style} summary in a {tone} tone. "
        f"They are interested in {genre_1} and {genre_2} books."
        f"Their preferred reading time is {reading_time} minutes."
    )
 
    conn = get_connection()
    cursor = get_cursor(conn)
 
    cursor.execute("DELETE FROM user_preferences WHERE user_id = %s", (user_id,))

    cursor.execute("""
        INSERT INTO user_preferences
        (user_id, goal, background, style, tone,
         genre_1, genre_2, profile_summary, reading_time, preferred_language)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (user_id, goal, background, style, tone,
          genre_1, genre_2, profile_summary, reading_time, language))
 
    conn.commit()
    conn.close()
    return profile_summary


def get_preferences(user_id):

    conn = get_connection()
    cursor = get_cursor(conn)
    cursor.execute(
        "SELECT * FROM user_preferences WHERE user_id = %s", (user_id,)
    )
    prefs = cursor.fetchone()
    conn.close()
    return dict(prefs) if prefs else None



GOALS = [
    "Learn a new skill",
    "Get inspired",
    "Understand a topic deeply",
    "Apply ideas to my career",
]

BACKGROUNDS = [
    "Student",
    "Entrepreneur",
    "Professional",
    "Creative",
    "General Reader",
]

STYLES = [
    "Quick & concise",
    "Balanced",
    "Deep & detailed",
]

TONES = [
    "Simple & casual",
    "Professional",
    "Motivational",
]

GENRES = [
    "Business & Finance",
    "Self-help & Psychology",
    "Science & Technology",
    "Fiction & Storytelling",
    "Health & Wellness",
    "History & Philosophy",
    "Productivity & Leadership",
]

READING_TIMES = [5, 10, 15]

LANGUAGES = [
    ("English", "en"),
    ("Hindi",   "hi"),
    ("Spanish", "es"),
]

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "es": "Spanish",
}