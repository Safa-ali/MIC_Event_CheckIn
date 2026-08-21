import os
import sys
import sqlite3

# Ensure project directory is on sys.path
sys.path.insert(0, os.path.abspath("."))

from app import app
from database import DATABASE_NAME, get_db_connection

def run_tests():
    print("==================================================")
    print("  MIC Event Check-In System - Phase 2 Test Suite  ")
    print("==================================================")

    # Use test client with cookie/session jar enabled
    client = app.test_client()

    # Clean test users if they exist from prior test runs
    conn = get_db_connection(DATABASE_NAME)
    conn.execute("DELETE FROM users WHERE email IN ('org_test@mic.org', 'att_test@mic.org', 'dup_test@mic.org');")
    conn.commit()
    conn.close()

    # ----------------------------------------------------
    # 1. Organizer Registration
    # ----------------------------------------------------
    print("\n[Test 1] Registering new Organizer...")
    res = client.post("/register", data={
        "name": "Alice Organizer",
        "email": "org_test@mic.org",
        "password": "SecurePassword123!",
        "role": "organizer"
    }, follow_redirects=False)
    assert res.status_code == 302, f"Expected 302 redirect on register, got {res.status_code}"
    assert "/login" in res.headers["Location"], f"Expected redirect to /login, got {res.headers['Location']}"
    print("  -> Passed: Organizer registration redirected to /login.")

    # ----------------------------------------------------
    # 2. Attendee Registration
    # ----------------------------------------------------
    print("\n[Test 2] Registering new Attendee...")
    res = client.post("/register", data={
        "name": "Bob Attendee",
        "email": "att_test@mic.org",
        "password": "AttendeePass456!",
        "role": "attendee"
    }, follow_redirects=False)
    assert res.status_code == 302, f"Expected 302 redirect on register, got {res.status_code}"
    assert "/login" in res.headers["Location"], f"Expected redirect to /login, got {res.headers['Location']}"
    print("  -> Passed: Attendee registration redirected to /login.")

    # ----------------------------------------------------
    # 3. Verify Passwords Stored as Hashes, NOT Plain Text
    # ----------------------------------------------------
    print("\n[Test 3] Verifying password hashing in SQLite...")
    conn = get_db_connection(DATABASE_NAME)
    org_row = conn.execute("SELECT password_hash FROM users WHERE email = 'org_test@mic.org'").fetchone()
    att_row = conn.execute("SELECT password_hash FROM users WHERE email = 'att_test@mic.org'").fetchone()
    conn.close()

    assert org_row is not None, "Organizer record not found in DB"
    assert att_row is not None, "Attendee record not found in DB"

    org_hash = org_row["password_hash"]
    att_hash = att_row["password_hash"]

    assert org_hash != "SecurePassword123!", "Organizer password stored as plain text!"
    assert att_hash != "AttendeePass456!", "Attendee password stored as plain text!"
    assert org_hash.startswith("scrypt:") or org_hash.startswith("pbkdf2:"), f"Invalid hash format: {org_hash}"
    print(f"  -> Passed: Passwords properly hashed (Hash prefix: {org_hash.split('$')[0]}).")

    # ----------------------------------------------------
    # 4. Duplicate Email Registration Rejected
    # ----------------------------------------------------
    print("\n[Test 4] Testing duplicate email registration rejection...")
    res = client.post("/register", data={
        "name": "Duplicate User",
        "email": "org_test@mic.org",
        "password": "AnotherPassword789!",
        "role": "organizer"
    }, follow_redirects=True)
    assert res.status_code == 400, f"Expected 400 Bad Request on duplicate email, got {res.status_code}"
    assert "already exists" in res.get_data(as_text=True), "Expected duplicate error message"
    print("  -> Passed: Duplicate email registration rejected with clear error.")

    # ----------------------------------------------------
    # 5. Login with Incorrect Password Rejected
    # ----------------------------------------------------
    print("\n[Test 5] Testing login with incorrect password...")
    res = client.post("/login", data={
        "email": "org_test@mic.org",
        "password": "WrongPassword!"
    }, follow_redirects=True)
    assert res.status_code == 401, f"Expected 401 Unauthorized for wrong password, got {res.status_code}"
    assert "Invalid email or password" in res.get_data(as_text=True), "Expected invalid credentials error message"
    print("  -> Passed: Incorrect password rejected with HTTP 401.")

    # ----------------------------------------------------
    # 6. Organizer Login & Redirection to /organizer
    # ----------------------------------------------------
    print("\n[Test 6] Testing Organizer login and redirection...")
    org_client = app.test_client()
    res = org_client.post("/login", data={
        "email": "org_test@mic.org",
        "password": "SecurePassword123!"
    }, follow_redirects=False)
    assert res.status_code == 302, f"Expected 302 redirect on successful login, got {res.status_code}"
    assert "/organizer" in res.headers["Location"], f"Expected redirect to /organizer, got {res.headers['Location']}"

    # Follow redirect and verify content
    res_dash = org_client.get("/organizer")
    assert res_dash.status_code == 200, f"Expected 200 on /organizer, got {res_dash.status_code}"
    dash_html = res_dash.get_data(as_text=True)
    assert "Organizer Dashboard" in dash_html, "Dashboard missing 'Organizer Dashboard' text"
    assert "Alice Organizer" in dash_html, "Dashboard missing logged-in user name"
    print("  -> Passed: Organizer redirected to /organizer and user name displayed.")

    # ----------------------------------------------------
    # 7. Attendee Login & Redirection to /attendee
    # ----------------------------------------------------
    print("\n[Test 7] Testing Attendee login and redirection...")
    att_client = app.test_client()
    res = att_client.post("/login", data={
        "email": "att_test@mic.org",
        "password": "AttendeePass456!"
    }, follow_redirects=False)
    assert res.status_code == 302, f"Expected 302 redirect on successful login, got {res.status_code}"
    assert "/attendee" in res.headers["Location"], f"Expected redirect to /attendee, got {res.headers['Location']}"

    # Follow redirect and verify content
    res_area = att_client.get("/attendee")
    assert res_area.status_code == 200, f"Expected 200 on /attendee, got {res_area.status_code}"
    area_html = res_area.get_data(as_text=True)
    assert "Attendee Area" in area_html, "Area missing 'Attendee Area' text"
    assert "Bob Attendee" in area_html, "Area missing logged-in user name"
    print("  -> Passed: Attendee redirected to /attendee and user name displayed.")

    # ----------------------------------------------------
    # 8. Attendee Cannot Access /organizer (RBAC)
    # ----------------------------------------------------
    print("\n[Test 8] Testing Attendee attempting to access /organizer (Forbidden 403)...")
    res_forbidden = att_client.get("/organizer")
    assert res_forbidden.status_code == 403, f"Expected 403 Forbidden, got {res_forbidden.status_code}"
    assert "Access Denied" in res_forbidden.get_data(as_text=True) or "403 Forbidden" in res_forbidden.get_data(as_text=True)
    print("  -> Passed: Attendee blocked from /organizer with HTTP 403 Forbidden.")

    # ----------------------------------------------------
    # 9. Organizer Cannot Access /attendee (RBAC)
    # ----------------------------------------------------
    print("\n[Test 9] Testing Organizer attempting to access /attendee (Forbidden 403)...")
    res_forbidden2 = org_client.get("/attendee")
    assert res_forbidden2.status_code == 403, f"Expected 403 Forbidden, got {res_forbidden2.status_code}"
    assert "Access Denied" in res_forbidden2.get_data(as_text=True) or "403 Forbidden" in res_forbidden2.get_data(as_text=True)
    print("  -> Passed: Organizer blocked from /attendee with HTTP 403 Forbidden.")

    # ----------------------------------------------------
    # 10. Unauthenticated User Accessing Protected Routes
    # ----------------------------------------------------
    print("\n[Test 10] Testing Unauthenticated access to /organizer and /attendee...")
    anon_client = app.test_client()
    res_anon_org = anon_client.get("/organizer", follow_redirects=False)
    assert res_anon_org.status_code == 302, f"Expected 302 redirect for anon /organizer, got {res_anon_org.status_code}"
    assert "/login" in res_anon_org.headers["Location"], "Expected redirect to /login"

    res_anon_att = anon_client.get("/attendee", follow_redirects=False)
    assert res_anon_att.status_code == 302, f"Expected 302 redirect for anon /attendee, got {res_anon_att.status_code}"
    assert "/login" in res_anon_att.headers["Location"], "Expected redirect to /login"
    print("  -> Passed: Unauthenticated users redirected to /login.")

    # ----------------------------------------------------
    # 11. Logout Clears Session
    # ----------------------------------------------------
    print("\n[Test 11] Testing Logout functionality...")
    res_logout = org_client.get("/logout", follow_redirects=False)
    assert res_logout.status_code == 302, f"Expected 302 redirect on logout, got {res_logout.status_code}"
    assert "/login" in res_logout.headers["Location"], "Expected redirect to /login on logout"

    # Attempt accessing /organizer after logout -> should redirect to /login
    res_after_logout = org_client.get("/organizer", follow_redirects=False)
    assert res_after_logout.status_code == 302, "Session not cleared! Access was permitted after logout."
    assert "/login" in res_after_logout.headers["Location"], "Did not redirect to /login after logout"
    print("  -> Passed: Logout cleared session and protected routes are no longer accessible.")

    print("\n==================================================")
    print("  ALL 11 PHASE 2 VERIFICATION TESTS PASSED!       ")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
