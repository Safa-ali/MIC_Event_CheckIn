import os
import sys
import sqlite3

# Ensure project directory is on sys.path
sys.path.insert(0, os.path.abspath("."))

from app import app
from database import DATABASE_NAME, get_db_connection
from werkzeug.security import generate_password_hash

def run_phase3_tests():
    print("==================================================")
    print("  MIC Event Check-In System - Phase 3 Test Suite  ")
    print("==================================================")

    # Setup test users in database
    conn = get_db_connection(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registrations WHERE event_id IN (SELECT id FROM events WHERE name LIKE 'P3 Test%');")
    cursor.execute("DELETE FROM events WHERE name LIKE 'P3 Test%';")
    cursor.execute("DELETE FROM users WHERE email IN ('org1@test.com', 'org2@test.com', 'att1@test.com');")
    
    # Create Organizer 1
    cursor.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("Organizer One", "org1@test.com", generate_password_hash("OrgPass1!"), "organizer")
    )
    org1_id = cursor.lastrowid

    # Create Organizer 2
    cursor.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("Organizer Two", "org2@test.com", generate_password_hash("OrgPass2!"), "organizer")
    )
    org2_id = cursor.lastrowid

    # Create Attendee 1
    cursor.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("Attendee One", "att1@test.com", generate_password_hash("AttPass1!"), "attendee")
    )
    att1_id = cursor.lastrowid

    conn.commit()
    conn.close()

    # ----------------------------------------------------
    # Helper Clients
    # ----------------------------------------------------
    org1_client = app.test_client()
    org1_client.post("/login", data={"email": "org1@test.com", "password": "OrgPass1!"})

    org2_client = app.test_client()
    org2_client.post("/login", data={"email": "org2@test.com", "password": "OrgPass2!"})

    att1_client = app.test_client()
    att1_client.post("/login", data={"email": "att1@test.com", "password": "AttPass1!"})

    anon_client = app.test_client()

    # ----------------------------------------------------
    # 1. Organizer can open the create-event page
    # ----------------------------------------------------
    print("\n[Test 1] Organizer opening GET /events/create...")
    res = org1_client.get("/events/create")
    assert res.status_code == 200, f"Expected 200 on /events/create, got {res.status_code}"
    assert "Create Event" in res.get_data(as_text=True), "Missing 'Create Event' in page content"
    print("  -> Passed: Organizer successfully opened create-event page.")

    # ----------------------------------------------------
    # 2. Organizer can create a valid event
    # ----------------------------------------------------
    print("\n[Test 2] Organizer creating valid event via POST /events/create...")
    res = org1_client.post("/events/create", data={
        "name": "P3 Test Hackathon",
        "event_date": "2026-10-15",
        "capacity": "150"
    }, follow_redirects=False)
    assert res.status_code == 302, f"Expected 302 redirect after creation, got {res.status_code}"
    assert "/organizer/events" in res.headers["Location"], f"Expected redirect to /organizer/events, got {res.headers['Location']}"
    print("  -> Passed: Event creation succeeded and redirected to /organizer/events.")

    # ----------------------------------------------------
    # 3. Created event appears in organizer's event list
    # ----------------------------------------------------
    print("\n[Test 3] Verifying created event in GET /organizer/events...")
    res = org1_client.get("/organizer/events")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    html = res.get_data(as_text=True)
    assert "P3 Test Hackathon" in html, "Event name missing from organizer events list"
    assert "2026-10-15" in html, "Event date missing from organizer events list"
    assert "150" in html, "Event capacity missing from organizer events list"
    print("  -> Passed: Event correctly rendered in organizer's event list.")

    # ----------------------------------------------------
    # 4. Event is actually stored in SQLite with created_by
    # ----------------------------------------------------
    print("\n[Test 4] Verifying event record in SQLite database...")
    conn = get_db_connection(DATABASE_NAME)
    row = conn.execute("SELECT * FROM events WHERE name = 'P3 Test Hackathon'").fetchone()
    conn.close()
    assert row is not None, "Event not found in SQLite events table"
    assert row["event_date"] == "2026-10-15", f"Date mismatch: {row['event_date']}"
    assert row["capacity"] == 150, f"Capacity mismatch: {row['capacity']}"
    assert row["created_by"] == org1_id, f"created_by mismatch: expected {org1_id}, got {row['created_by']}"
    print(f"  -> Passed: Event stored with correct id={row['id']} and created_by={row['created_by']}.")

    # ----------------------------------------------------
    # 5. Invalid blank event name is rejected
    # ----------------------------------------------------
    print("\n[Test 5] Testing rejection of blank event name...")
    res = org1_client.post("/events/create", data={
        "name": "   ",
        "event_date": "2026-10-15",
        "capacity": "100"
    })
    assert res.status_code == 400, f"Expected 400 Bad Request for blank name, got {res.status_code}"
    assert "All fields are required" in res.get_data(as_text=True), "Missing validation error message"
    print("  -> Passed: Blank event name rejected with HTTP 400.")

    # ----------------------------------------------------
    # 6. Invalid capacity (0 and negative) rejected
    # ----------------------------------------------------
    print("\n[Test 6] Testing rejection of capacity <= 0...")
    res_zero = org1_client.post("/events/create", data={
        "name": "P3 Test Zero Cap",
        "event_date": "2026-10-15",
        "capacity": "0"
    })
    assert res_zero.status_code == 400, f"Expected 400 for capacity 0, got {res_zero.status_code}"

    res_neg = org1_client.post("/events/create", data={
        "name": "P3 Test Neg Cap",
        "event_date": "2026-10-15",
        "capacity": "-25"
    })
    assert res_neg.status_code == 400, f"Expected 400 for negative capacity, got {res_neg.status_code}"
    print("  -> Passed: Capacity of 0 and negative capacities rejected with HTTP 400.")

    # ----------------------------------------------------
    # 7. Invalid capacity text is rejected
    # ----------------------------------------------------
    print("\n[Test 7] Testing rejection of non-integer capacity...")
    res_txt = org1_client.post("/events/create", data={
        "name": "P3 Test Text Cap",
        "event_date": "2026-10-15",
        "capacity": "one_hundred"
    })
    assert res_txt.status_code == 400, f"Expected 400 for text capacity, got {res_txt.status_code}"
    assert "whole number" in res_txt.get_data(as_text=True) or "positive" in res_txt.get_data(as_text=True)
    print("  -> Passed: Non-integer capacity rejected with HTTP 400.")

    # ----------------------------------------------------
    # 8. Invalid date format rejected
    # ----------------------------------------------------
    print("\n[Test 8] Testing rejection of invalid event date...")
    res_date = org1_client.post("/events/create", data={
        "name": "P3 Test Bad Date",
        "event_date": "not-a-valid-date",
        "capacity": "50"
    })
    assert res_date.status_code == 400, f"Expected 400 for bad date, got {res_date.status_code}"
    print("  -> Passed: Invalid date format rejected with HTTP 400.")

    # ----------------------------------------------------
    # 9. Attendee can view available events
    # ----------------------------------------------------
    print("\n[Test 9] Attendee viewing available events via GET /events...")
    res_att = att1_client.get("/events")
    assert res_att.status_code == 200, f"Expected 200 on /events, got {res_att.status_code}"
    html_att = res_att.get_data(as_text=True)
    assert "Available Events" in html_att, "Missing 'Available Events' heading"
    assert "P3 Test Hackathon" in html_att, "Created event missing from attendee view"
    assert "Create Event" not in html_att, "Attendee view should not have 'Create Event' button"
    print("  -> Passed: Attendee can view events (read-only without creation controls).")

    # ----------------------------------------------------
    # 10. Attendee cannot access /events/create (403 Forbidden)
    # ----------------------------------------------------
    print("\n[Test 10] Attendee attempting to access /events/create...")
    res_forbid_create = att1_client.get("/events/create")
    assert res_forbid_create.status_code == 403, f"Expected 403 on attendee /events/create, got {res_forbid_create.status_code}"

    res_forbid_post = att1_client.post("/events/create", data={
        "name": "Malicious Attendee Event",
        "event_date": "2026-10-20",
        "capacity": "10"
    })
    assert res_forbid_post.status_code == 403, f"Expected 403 on attendee POST /events/create, got {res_forbid_post.status_code}"
    print("  -> Passed: Attendee blocked from GET/POST /events/create with HTTP 403 Forbidden.")

    # ----------------------------------------------------
    # 11. Attendee cannot access /organizer/events (403 Forbidden)
    # ----------------------------------------------------
    print("\n[Test 11] Attendee attempting to access /organizer/events...")
    res_forbid_org_list = att1_client.get("/organizer/events")
    assert res_forbid_org_list.status_code == 403, f"Expected 403 on attendee /organizer/events, got {res_forbid_org_list.status_code}"
    print("  -> Passed: Attendee blocked from /organizer/events with HTTP 403 Forbidden.")

    # ----------------------------------------------------
    # 12. Organizer cannot access /events (attendee-only route)
    # ----------------------------------------------------
    print("\n[Test 12] Organizer attempting to access /events...")
    res_org_on_att_route = org1_client.get("/events")
    assert res_org_on_att_route.status_code == 403, f"Expected 403 on organizer accessing /events, got {res_org_on_att_route.status_code}"
    print("  -> Passed: Organizer blocked from attendee-only /events with HTTP 403 Forbidden.")

    # ----------------------------------------------------
    # 13. Organizer isolation: Organizer 2 creates an event; Org 1 cannot see it
    # ----------------------------------------------------
    print("\n[Test 13] Verifying organizer event isolation...")
    org2_client.post("/events/create", data={
        "name": "P3 Test Org2 Exclusive Event",
        "event_date": "2026-11-01",
        "capacity": "75"
    })
    res_org1_list = org1_client.get("/organizer/events")
    res_org2_list = org2_client.get("/organizer/events")
    assert "P3 Test Org2 Exclusive Event" not in res_org1_list.get_data(as_text=True), "Organizer 1 can see Organizer 2's event!"
    assert "P3 Test Org2 Exclusive Event" in res_org2_list.get_data(as_text=True), "Organizer 2 cannot see their own event"
    print("  -> Passed: Organizers only see events they created in /organizer/events.")

    # ----------------------------------------------------
    # 14. Unauthenticated users redirected to login
    # ----------------------------------------------------
    print("\n[Test 14] Unauthenticated access to /events/create, /organizer/events, /events...")
    for route in ["/events/create", "/organizer/events", "/events"]:
        res_anon = anon_client.get(route, follow_redirects=False)
        assert res_anon.status_code == 302 and "/login" in res_anon.headers["Location"], f"Route {route} not protected"
    print("  -> Passed: Unauthenticated access properly redirected to /login.")

    # ----------------------------------------------------
    # 15. Health Check & Phase 1/2 Regressions
    # ----------------------------------------------------
    print("\n[Test 15] Checking Phase 1 /health endpoint...")
    res_health = anon_client.get("/health")
    assert res_health.status_code == 200 and res_health.get_json() == {"status": "ok"}
    print("  -> Passed: /health returns 200 and status ok.")

    print("\n==================================================")
    print("  ALL 15 PHASE 3 TESTS PASSED SUCCESSFULLY!       ")
    print("==================================================")

if __name__ == "__main__":
    run_phase3_tests()
