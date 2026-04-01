import os
import json
import firebase_admin
from firebase_admin import credentials, auth
from user import (get_user_by_google_uid, get_user_by_email,
                  create_google_user, link_google_to_existing_user,
                  update_last_login)


# Initialize Firebase only once
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
    print("✅ Firebase initialized successfully")


def handle_google_login(full_name, email, google_uid):
    """
    Handles Google login with proper security + linking.

    Cases:
    1. Existing Google user → login
    2. Existing email user → link Google (if safe)
    3. New user → create account
    """

    # 1️⃣ Existing Google user
    existing_google = get_user_by_google_uid(google_uid)
    if existing_google:
        update_last_login(existing_google["id"])
        return {
            "user_id": existing_google["id"],
            "full_name": existing_google["full_name"],
            "is_new": False,
            "is_premium": existing_google["is_premium"],
        }

    # 2️⃣ Existing email user
    existing_email = get_user_by_email(email)
    if existing_email:

        # 🚨 SECURITY CHECK (VERY IMPORTANT)
        if existing_email.get("google_uid") and existing_email["google_uid"] != google_uid:
            print("⚠️ Google UID mismatch for email:", email)
            return None

        # 🔗 Link only if not already linked
        if not existing_email.get("google_uid"):
            link_google_to_existing_user(existing_email["id"], google_uid)

        update_last_login(existing_email["id"])

        return {
            "user_id": existing_email["id"],
            "full_name": existing_email["full_name"],
            "is_new": False,
        }

    # 3️⃣ New user
    user_id = create_google_user(full_name, email, google_uid)
    if user_id is None:
        print("❌ Failed to create Google user")
        return None

    # ✅ IMPORTANT: update last login for new user
    update_last_login(user_id)

    return {
        "user_id": user_id,
        "full_name": full_name,
        "is_new": True,
    }