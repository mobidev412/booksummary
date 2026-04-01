from werkzeug.security import generate_password_hash, check_password_hash
from db import get_connection, get_cursor
from datetime import datetime
import firebase_admin
from firebase_admin import auth, credentials
import os
import json

# Initialize Firebase Admin SDK (singleton)
if not firebase_admin._apps:
    service_account_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if service_account_json:
        cred_dict = json.loads(service_account_json)
        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(cred_dict)
    else:
        cred_path = os.path.join(os.path.dirname(__file__), 'firebase_service_account.json')
        cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)


def register_user(full_name, email, password):
    # 1. Create user in Firebase Auth
    try:
        user_record = auth.create_user(
            email=email,
            password=password,
            display_name=full_name
        )
        firebase_uid = user_record.uid
    except auth.EmailAlreadyExistsError:
        return None
    except Exception as e:
        print(f"Firebase registration error: {e}")
        return None

    # 2. Store user in local DB
    conn = get_connection()
    cursor = get_cursor(conn)
    try:
        password_hash = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (full_name, email, password_hash, firebase_uid, is_premium) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (full_name, email, password_hash, firebase_uid, False)
        )
        user_id = cursor.fetchone()["id"]
        conn.commit()
        return user_id
    except Exception as e:
        print(f"DB registration error: {e}")
        conn.rollback()
        # Rollback Firebase user if DB fails
        try:
            auth.delete_user(firebase_uid)
        except Exception:
            pass
        return None
    finally:
        conn.close()


def _verify_via_firebase(email, password):
    """
    Verify email+password against Firebase using the REST sign-in endpoint.
    This is the only way to check passwords after a Firebase password reset,
    because Firebase reset does NOT update our local password_hash.
    """
    import requests
    api_key = os.environ.get("FIREBASE_API_KEY")
    if not api_key:
        print("[DEBUG] No FIREBASE_API_KEY in environment!")
        return False
    try:
        resp = requests.post(
            f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}",
            json={"email": email, "password": password, "returnSecureToken": False},
            timeout=5
        )
        print(f"[DEBUG] Firebase REST login status: {resp.status_code}, body: {resp.text}")
        return resp.status_code == 200
    except Exception as e:
        print(f"Firebase REST verify error: {e}")
        return False


def login_user(email, password):
    conn = get_connection()
    cursor = get_cursor(conn)
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    print(f"[DEBUG] login_user: user row for {email}: {user}")
    if not user:
        conn.close()
        return None

    # Only use Firebase for authentication if firebase_uid exists
    if user.get("firebase_uid"):
        verified = _verify_via_firebase(email, password)
        print(f"[DEBUG] Firebase verify for {email}: {verified}")
        if not verified:
            conn.close()
            return None
        conn.close()
        return dict(user)

    # Fallback: legacy users without firebase_uid
    from werkzeug.security import check_password_hash
    if user.get("password_hash") and check_password_hash(user["password_hash"], password):
        conn.close()
        return dict(user)

    conn.close()
    return None



def get_user_by_id(user_id):
    """Fetch user by ID."""
    conn = get_connection()
    cursor = get_cursor(conn)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None




## google auth

def get_user_by_google_uid(google_uid):
    """Fetch user by Google UID."""
    conn = get_connection()
    cursor = get_cursor(conn)
    cursor.execute("SELECT * FROM users WHERE google_uid = %s", (google_uid,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_email(email):
    """
    Find a user by email address.
    Used to check if a Google user's email already exists
    as an email/password account — so we can link them.
    """
    conn   = get_connection()
    cursor = get_cursor(conn)
    cursor.execute(
        "SELECT * FROM users WHERE email = %s", (email,)
    )
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None


def create_google_user(full_name, email, google_uid, is_premium):
    """
    Create a new user who signed in with Google.
    No password — password_hash is NULL for Google users.
    Returns user_id or None if creation failed.
    """
    conn   = get_connection()
    cursor = get_cursor(conn)
    try:
        cursor.execute("""
            INSERT INTO users (full_name, email, google_uid, is_premium)
            VALUES (%s, %s, %s, FALSE)
            RETURNING id
        """, (full_name, email, google_uid))
        user_id = cursor.fetchone()["id"]
        conn.commit()
        return user_id
    except Exception:
        conn.rollback()
        return None
    finally:
        conn.close()
 
 
def link_google_to_existing_user(user_id, google_uid):
    """
    Link a Google UID to an existing email/password account.
    Called when a user who registered with email
    later signs in with Google using the same email.
    """
    conn   = get_connection()
    cursor = get_cursor(conn)
    try:
        cursor.execute(
            "UPDATE users SET google_uid = %s WHERE id = %s",
            (google_uid, user_id)
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()
 
 
def update_last_login(user_id):
    conn = get_connection()
    cursor = get_cursor(conn)
    from datetime import datetime
    try:
        cursor.execute(
            "UPDATE users SET last_login = %s WHERE id = %s",
            (datetime.now(), user_id)
        )
        conn.commit()
    except Exception as e:
        print(f"update_last_login error: {e}")
    finally:
        conn.close()


def get_user_by_firebase_uid(firebase_uid):
    """Fetch user by Firebase UID."""
    conn = get_connection()
    cursor = get_cursor(conn)
    cursor.execute("SELECT * FROM users WHERE firebase_uid = %s", (firebase_uid,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def create_user_from_firebase(full_name, email, firebase_uid, is_premium):
    """
    Create a new user authenticated via Firebase.
    Password is NOT stored in our DB.
    """
    conn = get_connection()
    cursor = get_cursor(conn)

    try:
        cursor.execute("""
            INSERT INTO users (full_name, email, firebase_uid, is_premium)
            VALUES (%s, %s, %s, FALSE)
            RETURNING id
        """, (full_name, email, firebase_uid))

        user_id = cursor.fetchone()["id"]
        conn.commit()
        return user_id

    except Exception:
        conn.rollback()
        return None

    finally:
        conn.close()

def link_firebase_to_existing_user(user_id, firebase_uid):
    """
    Link Firebase UID to an existing user (email/password user).
    """
    conn = get_connection()
    cursor = get_cursor(conn)

    try:
        cursor.execute(
            "UPDATE users SET firebase_uid = %s WHERE id = %s",
            (firebase_uid, user_id)
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()

def set_user_premium_by_email(email):
    """
    Set is_premium = TRUE for the user with the given email.
    """
    conn = get_connection()
    cursor = get_cursor(conn)
    try:
        cursor.execute(
            "UPDATE users SET is_premium = TRUE WHERE email = %s",
            (email,)
        )
        conn.commit()
        print(f"User {email} set to premium.")
    except Exception as e:
        print(f"Error setting user premium: {e}")
        conn.rollback()
    finally:
        conn.close()

def increment_summary_count(user_id):
    """
    Increment the summary_count for the user with the given user_id.
    """
    conn = get_connection()
    cursor = get_cursor(conn)
    try:
        cursor.execute(
            "UPDATE users SET summary_count = summary_count + 1 WHERE id = %s",
            (user_id,)
        )
        conn.commit()
    except Exception as e:
        print(f"Error incrementing summary_count: {e}")
        conn.rollback()
    finally:
        conn.close()