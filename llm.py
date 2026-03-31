import os
import json
# from google import genai
# from google.genai import types



# def _get_client():
#     api_key = os.environ.get("GEMINI_API_KEY", "")
#     if not api_key:
#         raise ValueError(
#             "GEMINI_API_KEY environment variable is not set.\n"
#             "Run: export GEMINI_API_KEY=your_key_here"
#         )
#     return genai.Client(api_key=api_key)


# def _call_gemini(prompt, system_prompt="", max_tokens=3000):
#     client      = _get_client()
#     full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
#     response    = client.models.generate_content(
#         model="gemini-2.5-flash-lite", 
#         contents=full_prompt,
#         config=types.GenerateContentConfig(
#             max_output_tokens=max_tokens,
#             temperature=0.7,
#         ),
#     )
#     return response.text



import os
from google import genai
from google.genai import types

# Module-level singleton — created once on first use, reused for all calls.
_gemini_client = None

def _get_client():
    global _gemini_client
    if _gemini_client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable is not set.\n"
                "Run: export GEMINI_API_KEY=your_key_here"
            )
        _gemini_client = genai.Client(api_key=api_key)
        print("[llm] ✅ Gemini client initialized (singleton)")
    return _gemini_client


def _call_gemini(prompt, system_prompt="", max_tokens=3000):
    client = _get_client()

    contents = []
    if system_prompt:
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=f"{system_prompt}\n\n{prompt}")]
        ))
    else:
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=prompt)]
        ))

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=contents,
        config=types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=0.7,
        ),
    )
    return response.text






def _parse_json_response(raw):
    clean = raw.strip()

    if "```" in clean:
        parts = clean.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                clean = part
                break

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        start = clean.find("{")
        end   = clean.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No valid JSON found in LLM response.")
        return json.loads(clean[start:end])

def _validate_summary_result(result, key_point_count):
    required_fields = [
        "low_confidence", "reading_time", "genre",
        "whats_inside", "youll_learn", "key_points",
        "conclusion", "about_author", "quote"
    ]
    for field in required_fields:
        if field not in result:
            raise ValueError(
                f"LLM response is missing required field: '{field}'. "
                f"Fields present: {list(result.keys())}"
            )

    if not isinstance(result["low_confidence"], bool):
        raise ValueError("'low_confidence' must be true or false")

    if not isinstance(result["whats_inside"], str) or len(result["whats_inside"].strip()) < 20:
        raise ValueError("'whats_inside' must be a non-empty string (min 20 chars)")

    if not isinstance(result["youll_learn"], list) or len(result["youll_learn"]) < 2:
        raise ValueError("'youll_learn' must be a list with at least 2 items")

    if not isinstance(result["key_points"], list):
        raise ValueError("'key_points' must be a list")

    if len(result["key_points"]) < 1:
        raise ValueError("'key_points' must have at least 1 item")

    for i, kp in enumerate(result["key_points"]):
        if not isinstance(kp, dict):
            raise ValueError(f"key_points[{i}] must be a dict, got {type(kp)}")
        for sub_field in ["title", "detail", "insight"]:
            if sub_field not in kp:
                raise ValueError(f"key_points[{i}] is missing '{sub_field}' field")
            if not isinstance(kp[sub_field], str) or len(kp[sub_field].strip()) == 0:
                raise ValueError(f"key_points[{i}]['{sub_field}'] must be a non-empty string")

    if not isinstance(result["conclusion"], str) or len(result["conclusion"].strip()) < 20:
        raise ValueError("'conclusion' must be a non-empty string (min 20 chars)")

    if not isinstance(result["about_author"], str) or len(result["about_author"].strip()) < 20:
        raise ValueError("'about_author' must be a non-empty string (min 20 chars)")

    if not isinstance(result["genre"], str) or len(result["genre"].strip()) == 0:
        raise ValueError("'genre' must be a non-empty string")

    if not isinstance(result["quote"], str):
        raise ValueError("'quote' must be a string (can be empty)")

    return True


def _validate_keypoint_result(result):
    if "deep_explanation" not in result:
        raise ValueError(
            f"Missing field: 'deep_explanation'. "
            f"Fields found: {list(result.keys())}"
        )
    if not isinstance(result["deep_explanation"], str) or len(result["deep_explanation"].strip()) < 20:
        raise ValueError("'deep_explanation' must be a non-empty string (min 20 chars)")
    return True


def generate_summary(book_title, author, description, profile_summary,
                     reading_time=10, language="English"): 
    if reading_time == 5:
        key_point_count = 3
        detail_length   = "2 to 3 sentences"
    elif reading_time == 15:
        key_point_count = 7
        detail_length   = "5 to 6 sentences"
    else:
        key_point_count = 5
        detail_length   = "3 to 4 sentences"

    system_prompt = (
        "You are a friendly book summarizer. "
        "You explain books in simple, clear language that anyone can understand — "
        "like you are explaining to a friend, not writing an essay. "
        "Use short sentences. Avoid complicated words. "
        "IMPORTANT: Respond ONLY with a single valid JSON object. "
        "Do NOT include any markdown, backticks, or text outside the JSON."
    )

    prompt = f"""
Create a book summary for the following book.

User Profile:
{profile_summary}

Book Details:
Title:        {book_title}
Author:       {author}
Description:  {description}
Reading Time: {reading_time} minutes

RULES — follow every rule exactly:

1. If you do not know enough about this book, set "low_confidence" to true.
   Otherwise set it to false.

2. LANGUAGE RULE — This is the most important rule:
   Write ALL text content in {language}.
   This applies to: whats_inside, every item in youll_learn,
   every title/detail/insight in key_points, conclusion, about_author, quote.
   The JSON keys (whats_inside, youll_learn, key_points, etc.) must stay in English exactly.
   Only the text VALUES inside the keys should be in {language}.

3. Write everything in simple, easy-to-understand language.
   Imagine you are explaining this book to a friend over coffee.
   No complicated words. Short sentences. Friendly tone.
   If writing in Hindi or Spanish, use everyday words — not formal or literary language.

4. "whats_inside"
   Write 2 to 3 simple sentences in {language}.
   Answer: What is this book about? Why should someone read it?

5. "youll_learn"
   Write exactly 3 short bullet points in {language}.
   Each bullet = one specific thing the reader will gain from this book.
   Keep each bullet under 15 words.

6. "key_points"
   Write exactly {key_point_count} key points.
   Each key point must have exactly 3 parts — all text written in {language}:
   - "title"   : A short heading, 4 to 6 words only
   - "detail"  : {detail_length} explaining this idea simply.
                 Use plain language. Give a simple example if possible.
   - "insight" : One powerful sentence — the single most important
                 takeaway from this key point. Make it memorable.

7. "conclusion"
   Write 2 to 3 sentences in {language} wrapping up the book.
   Include one simple action the reader can take today.

8. "about_author"
   Write 2 to 3 sentences in {language} about who wrote this book.
   Who are they? Why should the reader trust them on this topic?

9. "quote"
   One real, memorable quote from this book written in {language}.
   If translating, keep the meaning intact.
   If you are not sure of the exact quote, write an empty string "".

10. "genre"
    One word only in English. Pick the best match from:
    Business, Self-help, Science, History, Fiction,
    Health, Psychology, Productivity, Biography, Philosophy

11. "reading_time"
    Return exactly: {reading_time}

Respond with ONLY this JSON structure — nothing else before or after:
{{
  "low_confidence": false,
  "reading_time":   {reading_time},
  "genre":          "...",
  "whats_inside":   "...",
  "youll_learn": [
    "...",
    "...",
    "..."
  ],
  "key_points": [
    {{
      "title":   "...",
      "detail":  "...",
      "insight": "..."
    }}
  ],
  "conclusion":    "...",
  "about_author":  "...",
  "quote":         "..."
}}
"""

    last_error = None
    for attempt in range(1, 3):
        try:
            raw    = _call_gemini(prompt, system_prompt, max_tokens=3000)
            result = _parse_json_response(raw)
            _validate_summary_result(result, key_point_count)
            return result

        except (ValueError, KeyError) as e:
            last_error = e
            print(f"  Summary attempt {attempt} failed: {e}. Retrying...")
            continue

        except Exception as e:
            raise e

    raise ValueError(
        f"Failed to generate a valid summary after 2 attempts. "
        f"Last error: {last_error}"
    )

def generate_key_point_detail(book_title, author, key_point_title,
                               key_point_detail, language="English"): 
    system_prompt = (
        "You are a friendly book explainer. "
        "You take one idea from a book and explain it deeply but simply. "
        "Write like you are talking to a curious friend — "
        "clear, warm, and easy to follow. No jargon. No complicated words. "
        "IMPORTANT: Respond ONLY with a single valid JSON object. "
        "Do NOT include any markdown, backticks, or text outside the JSON."
    )

    prompt = f"""
Write a detailed, easy-to-read explanation of one key idea from a book.

Book: {book_title}
Author: {author}

Key Point Title: {key_point_title}
Brief Summary of this Point: {key_point_detail}

RULES — follow every rule exactly:

1. LANGUAGE RULE — Write ALL text content in {language}.
   If writing in Hindi or Spanish, use everyday conversational words.
   Not formal or literary language — keep it simple and friendly.

2. Write everything in very simple, friendly language.
   Imagine you are explaining this to a 16-year-old who is smart but new to this topic.
   Use short paragraphs. Use examples from everyday life.
   No complicated words. No academic language.

3. "deep_explanation"
   Write 4 to 5 paragraphs in {language} that fully explain this key idea.
   - Paragraph 1: What is this idea? Explain it simply in 2-3 sentences.
   - Paragraph 2: Why does this idea matter? What problem does it solve?
   - Paragraph 3: How does this idea work in real life? Give a simple example.
   - Paragraph 4: What happens if you ignore this idea?
   - Paragraph 5 (optional): One final thought or takeaway.
   Make each paragraph at least 6 sentences long.
   Separate each paragraph with a blank line.

Respond with ONLY this JSON structure — nothing else before or after:
{{
  "deep_explanation": "..."
}}
"""

    last_error = None
    for attempt in range(1, 3):
        try:
            raw    = _call_gemini(prompt, system_prompt, max_tokens=2000)
            result = _parse_json_response(raw)
            _validate_keypoint_result(result)
            return result

        except (ValueError, KeyError) as e:
            last_error = e
            print(f" Key point attempt {attempt} failed: {e}. Retrying...")
            continue

        except Exception as e:
            raise e

    raise ValueError(
        f"Failed to generate a valid key point detail after 2 attempts. "
        f"Last error: {last_error}"
    )