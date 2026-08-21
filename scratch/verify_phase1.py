import os
import sys
import sqlite3

sys.path.insert(0, os.path.abspath("."))

from app import app
from database import DATABASE_NAME, init_db, get_db_connection

def test_database():
    print("=== Testing Database ===")
    conn = get_db_connection(DATABASE_NAME)
    cursor = conn.cursor()
    
    tables = [row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;").fetchall()]
    print("Tables found:", tables)
    assert "users" in tables, "users table missing"
    assert "events" in tables, "events table missing"
    assert "registrations" in tables, "registrations table missing"

    users_cols = [row[1] for row in cursor.execute("PRAGMA table_info(users);").fetchall()]
    assert set(["id", "name", "email", "password_hash", "role"]).issubset(set(users_cols)), "users columns mismatch"

    events_cols = [row[1] for row in cursor.execute("PRAGMA table_info(events);").fetchall()]
    assert set(["id", "name", "event_date", "capacity", "created_by"]).issubset(set(events_cols)), "events columns mismatch"

    reg_cols = [row[1] for row in cursor.execute("PRAGMA table_info(registrations);").fetchall()]
    assert set(["id", "event_id", "user_id", "qr_token", "registered_at", "checked_in_at"]).issubset(set(reg_cols)), "registrations columns mismatch"

    cursor.execute("INSERT INTO users (name, email, password_hash) VALUES ('Sara', 'sara_test_p1@example.com', 'hash123');")
    user_id = cursor.lastrowid
    cursor.execute("INSERT INTO events (name, event_date, capacity, created_by) VALUES ('MIC Hackathon', '2026-09-01', 100, ?);", (user_id,))
    event_id = cursor.lastrowid
    cursor.execute("INSERT INTO registrations (event_id, user_id, qr_token) VALUES (?, ?, 'token_abc');", (event_id, user_id))
    
    duplicate_failed = False
    try:
        cursor.execute("INSERT INTO registrations (event_id, user_id, qr_token) VALUES (?, ?, 'token_xyz');", (event_id, user_id))
    except sqlite3.IntegrityError:
        duplicate_failed = True
    assert duplicate_failed, "Uniqueness constraint for (event_id, user_id) failed to trigger"
    print("Uniqueness constraint verified: duplicate registration rejected as expected.")

    conn.rollback()
    conn.close()
    print("Database verification passed successfully!\n")

def test_flask_app():
    print("=== Testing Flask Application ===")
    client = app.test_client()
    
    res_index = client.get("/")
    print(f"GET / -> Status: {res_index.status_code}")
    assert res_index.status_code == 200, "GET / did not return 200"
    html_content = res_index.get_data(as_text=True)
    assert "MIC Event Check-In System" in html_content, "Missing title in index.html"
    print("GET / passed!")

    res_health = client.get("/health")
    print(f"GET /health -> Status: {res_health.status_code}")
    assert res_health.status_code == 200, "GET /health did not return 200"
    json_data = res_health.get_json()
    print(f"GET /health JSON response: {json_data}")
    assert json_data == {"status": "ok"}, "GET /health returned unexpected JSON"
    print("GET /health passed!")
    print("Flask application verification passed successfully!\n")

if __name__ == "__main__":
    test_database()
    test_flask_app()
    print("ALL PHASE 1 REGRESSION CHECKS PASSED!")
