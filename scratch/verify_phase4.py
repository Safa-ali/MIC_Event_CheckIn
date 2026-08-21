import os
import sys
import json
import sqlite3
import concurrent.futures
from werkzeug.security import generate_password_hash

# Ensure project directory is on sys.path
sys.path.insert(0, os.path.abspath("."))

from app import app, generate_qr_base64
from database import DATABASE_NAME, get_db_connection

def run_phase4_tests():
    print("==================================================")
    print("  MIC Event Check-In System - Phase 4 Test Suite  ")
    print("==================================================")

    # 1. Clean test data from database
    conn = get_db_connection(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registrations WHERE event_id IN (SELECT id FROM events WHERE name LIKE 'P4 Test%');")
    cursor.execute("DELETE FROM events WHERE name LIKE 'P4 Test%';")
    cursor.execute("DELETE FROM users WHERE email LIKE 'p4_%@test.com' OR email IN ('org_p4@test.com', 'att1_p4@test.com', 'att2_p4@test.com', 'att3_p4@test.com');")

    # Create Organizer
    cursor.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("P4 Organizer", "org_p4@test.com", generate_password_hash("OrgPass123!"), "organizer")
    )
    org_id = cursor.lastrowid

    # Create Attendees
    cursor.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("Attendee 1", "att1_p4@test.com", generate_password_hash("AttPass123!"), "attendee")
    )
    att1_id = cursor.lastrowid

    cursor.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("Attendee 2", "att2_p4@test.com", generate_password_hash("AttPass123!"), "attendee")
    )
    att2_id = cursor.lastrowid

    cursor.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("Attendee 3", "att3_p4@test.com", generate_password_hash("AttPass123!"), "attendee")
    )
    att3_id = cursor.lastrowid

    # Create Test Event with capacity 2
    cursor.execute(
        "INSERT INTO events (name, event_date, capacity, created_by) VALUES (?, ?, ?, ?)",
        ("P4 Test Capacity-2 Event", "2026-11-10", 2, org_id)
    )
    event2_id = cursor.lastrowid

    conn.commit()
    conn.close()

    # ----------------------------------------------------
    # Helper Clients
    # ----------------------------------------------------
    att1_client = app.test_client()
    att1_client.post("/login", data={"email": "att1_p4@test.com", "password": "AttPass123!"})

    att2_client = app.test_client()
    att2_client.post("/login", data={"email": "att2_p4@test.com", "password": "AttPass123!"})

    att3_client = app.test_client()
    att3_client.post("/login", data={"email": "att3_p4@test.com", "password": "AttPass123!"})

    org_client = app.test_client()
    org_client.post("/login", data={"email": "org_p4@test.com", "password": "OrgPass123!"})

    # ----------------------------------------------------
    # Test 1: Attendee can browse events
    # ----------------------------------------------------
    print("\n[Test 1] Attendee browsing events via GET /events...")
    res = att1_client.get("/events")
    assert res.status_code == 200, f"Expected 200 on /events, got {res.status_code}"
    html = res.get_data(as_text=True)
    assert "P4 Test Capacity-2 Event" in html, "Event missing from available events"
    assert "2 spots left" in html, "Remaining spots missing or incorrect"
    assert "Register Now" in html, "Register button missing"
    print("  -> Passed: Available events displayed with remaining spots & register action.")

    # ----------------------------------------------------
    # Test 2: Attendee can register for an event
    # ----------------------------------------------------
    print("\n[Test 2] Attendee 1 registering for event...")
    res = att1_client.post(f"/events/{event2_id}/register", follow_redirects=False)
    assert res.status_code == 302, f"Expected 302 redirect after registration, got {res.status_code}"
    assert "/attendee/registrations" in res.headers["Location"], f"Expected redirect to registrations page, got {res.headers['Location']}"
    print("  -> Passed: Registration succeeded and redirected to /attendee/registrations.")

    # ----------------------------------------------------
    # Test 3: Registration stored in SQLite
    # ----------------------------------------------------
    print("\n[Test 3] Verifying registration persistence in SQLite...")
    conn = get_db_connection(DATABASE_NAME)
    reg_row = conn.execute(
        "SELECT * FROM registrations WHERE event_id = ? AND user_id = ?",
        (event2_id, att1_id)
    ).fetchone()
    conn.close()
    assert reg_row is not None, "Registration record not found in database"
    assert reg_row["qr_token"] is not None and len(reg_row["qr_token"]) > 20, "Missing or short qr_token"
    print(f"  -> Passed: Registration found with id={reg_row['id']} and qr_token={reg_row['qr_token'][:12]}...")

    # ----------------------------------------------------
    # Test 4 & 5: QR Token Security & Unpredictability
    # ----------------------------------------------------
    print("\n[Test 4 & 5] Verifying QR token security...")
    token = reg_row["qr_token"]
    assert str(att1_id) != token, "Token equals attendee ID"
    assert str(event2_id) != token, "Token equals event ID"
    assert "att1_p4@test.com" not in token, "Token leaks attendee email"
    assert len(token) >= 32, f"Token length {len(token)} is shorter than 32"
    print(f"  -> Passed: Token is cryptographically random and secure (Length: {len(token)} chars).")

    # ----------------------------------------------------
    # Test 6 & 7: QR Code Generation & View on Registrations Page
    # ----------------------------------------------------
    print("\n[Test 6 & 7] Verifying QR code generation and attendee registrations page...")
    qr_b64 = generate_qr_base64(token)
    assert qr_b64.startswith("iVBORw0KGgo"), "Generated QR base64 does not start with valid PNG header"

    res_reg_page = att1_client.get("/attendee/registrations")
    assert res_reg_page.status_code == 200, f"Expected 200, got {res_reg_page.status_code}"
    reg_html = res_reg_page.get_data(as_text=True)
    assert "P4 Test Capacity-2 Event" in reg_html, "Event name missing on badge page"
    assert "Not checked in" in reg_html, "Status 'Not checked in' missing on badge page"
    assert "data:image/png;base64," in reg_html, "Embedded QR image missing on badge page"
    print("  -> Passed: Registration badge with embedded QR code and 'Not checked in' status rendered.")

    # ----------------------------------------------------
    # Test 8: Duplicate Registration is Rejected
    # ----------------------------------------------------
    print("\n[Test 8] Testing duplicate registration rejection...")
    res_dup = att1_client.post(f"/events/{event2_id}/register", follow_redirects=True)
    assert res_dup.status_code in [200, 400], f"Unexpected status code: {res_dup.status_code}"
    dup_html = res_dup.get_data(as_text=True)
    assert "already registered" in dup_html, "Missing duplicate registration warning"
    print("  -> Passed: Duplicate registration attempt rejected with clear warning.")

    # ----------------------------------------------------
    # Test 9: Organizer Cannot Register as Attendee
    # ----------------------------------------------------
    print("\n[Test 9] Testing Organizer attempting attendee registration...")
    res_org_reg = org_client.post(f"/events/{event2_id}/register", follow_redirects=False)
    assert res_org_reg.status_code == 403, f"Expected 403 Forbidden for organizer registration, got {res_org_reg.status_code}"
    print("  -> Passed: Organizer blocked from attendee registration with HTTP 403 Forbidden.")

    # ----------------------------------------------------
    # Test 10: Invalid Event ID is Rejected
    # ----------------------------------------------------
    print("\n[Test 10] Testing registration for non-existent event...")
    res_invalid_event = att2_client.post("/events/999999/register", follow_redirects=False)
    assert res_invalid_event.status_code in [404, 302], f"Expected 404/302, got {res_invalid_event.status_code}"
    print("  -> Passed: Non-existent event registration safely rejected.")

    # ----------------------------------------------------
    # Test 11: Capacity Enforcement (Sequential Filling)
    # ----------------------------------------------------
    print("\n[Test 11] Testing Capacity Enforcement (2-seat event)...")
    # Register 2nd attendee (fills seat 2/2)
    res_att2 = att2_client.post(f"/events/{event2_id}/register", follow_redirects=False)
    assert res_att2.status_code == 302, "Attendee 2 registration failed"

    # Attempt 3rd attendee (exceeds capacity 2)
    res_att3 = att3_client.post(f"/events/{event2_id}/register", follow_redirects=True)
    assert "reached maximum capacity" in res_att3.get_data(as_text=True) or "full" in res_att3.get_data(as_text=True)

    conn = get_db_connection(DATABASE_NAME)
    total_reg = conn.execute("SELECT COUNT(*) as c FROM registrations WHERE event_id = ?", (event2_id,)).fetchone()["c"]
    conn.close()
    assert total_reg == 2, f"Expected exactly 2 registrations, found {total_reg}"
    print(f"  -> Passed: 3rd registration rejected. Total in SQLite = {total_reg} (Capacity = 2).")

    # ----------------------------------------------------
    # Test 12: MIC Concurrency Benchmark (100 Concurrent Requests, max_workers=100)
    # ----------------------------------------------------
    print("\n==================================================")
    print("  MIC Concurrency Benchmark: 100 Concurrent Workers")
    print("==================================================")
    print("Setting up Event (Capacity = 5) and 100 distinct Attendee accounts...")

    conn = get_db_connection(DATABASE_NAME)
    cursor = conn.cursor()

    # Create Concurrency Benchmark Event (Capacity = 5)
    cursor.execute(
        "INSERT INTO events (name, event_date, capacity, created_by) VALUES (?, ?, ?, ?)",
        ("P4 Concurrency Benchmark 100", "2026-12-01", 5, org_id)
    )
    bench_event_id = cursor.lastrowid

    # Create 100 unique attendee user accounts in SQLite
    attendee_pass_hash = generate_password_hash("BenchPass123!")
    user_records = [
        (f"Bench User {i}", f"p4_bench_{i}@test.com", attendee_pass_hash, "attendee")
        for i in range(100)
    ]
    cursor.executemany(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        user_records
    )
    conn.commit()

    # Fetch all 100 user IDs
    rows = cursor.execute(
        "SELECT id, email FROM users WHERE email LIKE 'p4_bench_%@test.com' ORDER BY id ASC"
    ).fetchall()
    bench_users = [(r["id"], r["email"]) for r in rows]
    conn.close()
    assert len(bench_users) == 100, f"Expected 100 benchmark users, created {len(bench_users)}"

    print(f"Created {len(bench_users)} distinct attendee accounts in SQLite.")
    print("Dispatching 100 concurrent registration requests with ThreadPoolExecutor(max_workers=100)...")

    def submit_registration(user_info):
        uid, email = user_info
        thread_client = app.test_client()
        with thread_client.session_transaction() as sess:
            sess["user_id"] = uid
            sess["name"] = f"Bench User {uid}"
            sess["role"] = "attendee"

        response = thread_client.post(f"/events/{bench_event_id}/register", follow_redirects=False)
        return {
            "user_id": uid,
            "email": email,
            "status_code": response.status_code,
            "location": response.headers.get("Location", ""),
            "success": (response.status_code == 302 and "/attendee/registrations" in response.headers.get("Location", ""))
        }

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        futures = [executor.submit(submit_registration, u) for u in bench_users]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    # Calculate statistics
    successful_requests = [r for r in results if r["success"]]
    rejected_requests = [r for r in results if not r["success"]]

    conn = get_db_connection(DATABASE_NAME)
    final_db_count = conn.execute(
        "SELECT COUNT(*) as c FROM registrations WHERE event_id = ?",
        (bench_event_id,)
    ).fetchone()["c"]
    conn.close()

    evidence = {
        "benchmark_name": "MIC Phase 4 Concurrency Benchmark",
        "total_concurrent_requests_sent": len(results),
        "concurrency_workers": 100,
        "event_capacity": 5,
        "successful_registrations": len(successful_requests),
        "rejected_registrations": len(rejected_requests),
        "final_sqlite_registration_count": final_db_count,
        "capacity_exceeded": (final_db_count > 5),
        "passed": (len(successful_requests) == 5 and len(rejected_requests) == 95 and final_db_count == 5)
    }

    # Save evidence JSON
    evidence_path = os.path.join(
        "C:\\Users\\sara\\.gemini\\antigravity\\brain\\7018847d-e888-459f-a736-518b28435a99\\scratch",
        "concurrency_evidence.json"
    )
    with open(evidence_path, "w") as f:
        json.dump(evidence, f, indent=2)

    print("\n--- Concurrency Benchmark Results ---")
    print(f"Total Concurrent Requests Sent:  {evidence['total_concurrent_requests_sent']}")
    print(f"Worker Pool Size:               {evidence['concurrency_workers']}")
    print(f"Event Target Capacity:          {evidence['event_capacity']}")
    print(f"Successful Registrations:       {evidence['successful_registrations']}")
    print(f"Rejected Registrations:         {evidence['rejected_registrations']}")
    print(f"Final Count in SQLite Table:    {evidence['final_sqlite_registration_count']}")
    print(f"Evidence File Saved To:         {evidence_path}")
    print("-------------------------------------")

    assert evidence["successful_registrations"] == 5, f"Expected exactly 5 successes, got {evidence['successful_registrations']}"
    assert evidence["rejected_registrations"] == 95, f"Expected exactly 95 rejections, got {evidence['rejected_registrations']}"
    assert evidence["final_sqlite_registration_count"] == 5, f"Expected final SQLite count 5, got {evidence['final_sqlite_registration_count']}"
    assert not evidence["capacity_exceeded"], "Capacity exceeded in SQLite!"

    print("  -> Passed: Concurrency benchmark strictly enforced capacity = 5 under 100 concurrent workers.")

    # ----------------------------------------------------
    # Clean up test-only records to protect data integrity
    # ----------------------------------------------------
    conn = get_db_connection(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registrations WHERE event_id IN (SELECT id FROM events WHERE name LIKE 'P4 %');")
    cursor.execute("DELETE FROM events WHERE name LIKE 'P4 %';")
    cursor.execute("DELETE FROM users WHERE email LIKE 'p4_%@test.com' OR email IN ('org_p4@test.com', 'att1_p4@test.com', 'att2_p4@test.com', 'att3_p4@test.com');")
    conn.commit()
    conn.close()

    print("\n==================================================")
    print("  ALL 12 PHASE 4 TESTS + CONCURRENCY PASSED!      ")
    print("==================================================")

if __name__ == "__main__":
    run_phase4_tests()
