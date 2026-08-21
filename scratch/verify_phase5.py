import os
import sys
import json
import sqlite3
import concurrent.futures
from werkzeug.security import generate_password_hash

# Ensure project directory is on sys.path
sys.path.insert(0, os.path.abspath("."))

from app import app
from database import DATABASE_NAME, get_db_connection

def run_phase5_tests():
    print("==================================================")
    print("  MIC Event Check-In System - Phase 5 Test Suite  ")
    print("==================================================")

    # Clean existing test records
    conn = get_db_connection(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registrations WHERE event_id IN (SELECT id FROM events WHERE name LIKE 'P5 Test%');")
    cursor.execute("DELETE FROM events WHERE name LIKE 'P5 Test%';")
    cursor.execute("DELETE FROM users WHERE email IN ('p5_org1@test.com', 'p5_org2@test.com', 'p5_att1@test.com', 'p5_att2@test.com');")

    # Create Organizer 1
    cursor.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("Organizer One", "p5_org1@test.com", generate_password_hash("OrgPass123!"), "organizer")
    )
    org1_id = cursor.lastrowid

    # Create Organizer 2
    cursor.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("Organizer Two", "p5_org2@test.com", generate_password_hash("OrgPass123!"), "organizer")
    )
    org2_id = cursor.lastrowid

    # Create Attendee 1
    cursor.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("Attendee Alice", "p5_att1@test.com", generate_password_hash("AttPass123!"), "attendee")
    )
    att1_id = cursor.lastrowid

    # Create Attendee 2
    cursor.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        ("Attendee Bob", "p5_att2@test.com", generate_password_hash("AttPass123!"), "attendee")
    )
    att2_id = cursor.lastrowid

    # Create Event for Organizer 1
    cursor.execute(
        "INSERT INTO events (name, event_date, capacity, created_by) VALUES (?, ?, ?, ?)",
        ("P5 Test Org1 Event", "2026-11-20", 50, org1_id)
    )
    event1_id = cursor.lastrowid

    # Create Event for Organizer 2
    cursor.execute(
        "INSERT INTO events (name, event_date, capacity, created_by) VALUES (?, ?, ?, ?)",
        ("P5 Test Org2 Event", "2026-11-21", 50, org2_id)
    )
    event2_id = cursor.lastrowid

    # Create Registration for Alice on Org1's event
    cursor.execute(
        "INSERT INTO registrations (event_id, user_id, qr_token) VALUES (?, ?, ?)",
        (event1_id, att1_id, "P5_TOKEN_ALICE_VALID_123456789012")
    )
    reg_alice_id = cursor.lastrowid

    # Create Registration for Bob on Org2's event
    cursor.execute(
        "INSERT INTO registrations (event_id, user_id, qr_token) VALUES (?, ?, ?)",
        (event2_id, att2_id, "P5_TOKEN_BOB_ORG2_12345678901234")
    )
    reg_bob_id = cursor.lastrowid

    conn.commit()
    conn.close()

    # Setup test clients
    org1_client = app.test_client()
    org1_client.post("/login", data={"email": "p5_org1@test.com", "password": "OrgPass123!"})

    org2_client = app.test_client()
    org2_client.post("/login", data={"email": "p5_org2@test.com", "password": "OrgPass123!"})

    att1_client = app.test_client()
    att1_client.post("/login", data={"email": "p5_att1@test.com", "password": "AttPass123!"})

    # ----------------------------------------------------
    # Test 1: Organizer can access scanner
    # ----------------------------------------------------
    print("\n[Test 1] Organizer accessing GET /organizer/scan...")
    res = org1_client.get("/organizer/scan")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    html = res.get_data(as_text=True)
    assert "Event Check-In Scanner" in html, "Scanner heading missing"
    assert "html5-qrcode" in html, "html5-qrcode script missing"
    assert "manual-token" in html, "Manual token input missing"
    print("  -> Passed: Organizer scanner page rendered with camera & manual entry.")

    # ----------------------------------------------------
    # Test 2: Attendee cannot access scanner
    # ----------------------------------------------------
    print("\n[Test 2] Attendee attempting to access GET /organizer/scan...")
    res_att_scan = att1_client.get("/organizer/scan")
    assert res_att_scan.status_code == 403, f"Expected 403 Forbidden, got {res_att_scan.status_code}"
    print("  -> Passed: Attendee blocked from scanner with HTTP 403 Forbidden.")

    # ----------------------------------------------------
    # Test 3 & 4: Valid QR Token Check-In & SQLite Persistence
    # ----------------------------------------------------
    print("\n[Test 3 & 4] Organizer 1 checking in Alice via POST /api/checkin...")
    res_checkin = org1_client.post(
        "/api/checkin",
        json={"qr_token": "P5_TOKEN_ALICE_VALID_123456789012"}
    )
    assert res_checkin.status_code == 200, f"Expected 200, got {res_checkin.status_code}"
    data = res_checkin.get_json()
    assert data["success"] is True, "Check-in failed"
    assert data["attendee_name"] == "Attendee Alice", f"Attendee mismatch: {data.get('attendee_name')}"
    assert data["event_name"] == "P5 Test Org1 Event", f"Event mismatch: {data.get('event_name')}"
    first_checkin_time = data["checked_in_at"]
    assert first_checkin_time is not None, "Missing checked_in_at timestamp in response"

    # Verify directly in SQLite
    conn = get_db_connection(DATABASE_NAME)
    row = conn.execute("SELECT checked_in_at FROM registrations WHERE id = ?", (reg_alice_id,)).fetchone()
    conn.close()
    assert row["checked_in_at"] == first_checkin_time, "Timestamp in SQLite does not match check-in response"
    print(f"  -> Passed: Check-in succeeded with timestamp {first_checkin_time}.")

    # ----------------------------------------------------
    # Test 5: Attendee Status Updated on Registrations Page
    # ----------------------------------------------------
    print("\n[Test 5] Checking Attendee Alice's registration badge status...")
    res_alice_page = att1_client.get("/attendee/registrations")
    assert res_alice_page.status_code == 200
    alice_html = res_alice_page.get_data(as_text=True)
    assert "Checked In" in alice_html, "Missing 'Checked In' status badge on attendee page"
    assert first_checkin_time in alice_html, "Missing confirmed check-in timestamp on attendee page"
    print("  -> Passed: Attendee registration shows 'Checked In' status and exact timestamp.")

    # ----------------------------------------------------
    # Test 6 & 7: Duplicate Check-In Rejected & Timestamp Unchanged
    # ----------------------------------------------------
    print("\n[Test 6 & 7] Testing duplicate scan of the same QR token...")
    res_dup = org1_client.post(
        "/api/checkin",
        json={"qr_token": "P5_TOKEN_ALICE_VALID_123456789012"}
    )
    assert res_dup.status_code == 400, f"Expected 400 Bad Request, got {res_dup.status_code}"
    dup_data = res_dup.get_json()
    assert dup_data["success"] is False, "Duplicate check-in was erroneously accepted"
    assert "Already checked in" in dup_data["message"], f"Unexpected message: {dup_data.get('message')}"

    # Verify SQLite timestamp was NOT altered
    conn = get_db_connection(DATABASE_NAME)
    row_after_dup = conn.execute("SELECT checked_in_at FROM registrations WHERE id = ?", (reg_alice_id,)).fetchone()
    conn.close()
    assert row_after_dup["checked_in_at"] == first_checkin_time, "Original timestamp was overwritten!"
    print(f"  -> Passed: Duplicate check-in rejected with clear warning. Timestamp preserved: {first_checkin_time}.")

    # ----------------------------------------------------
    # Test 8: Invalid QR Token is Rejected
    # ----------------------------------------------------
    print("\n[Test 8] Testing invalid non-existent QR token...")
    res_invalid = org1_client.post(
        "/api/checkin",
        json={"qr_token": "INVALID_GARBAGE_TOKEN_99999"}
    )
    assert res_invalid.status_code == 404, f"Expected 404 Not Found, got {res_invalid.status_code}"
    inv_data = res_invalid.get_json()
    assert inv_data["success"] is False and "Invalid QR code" in inv_data["message"]
    print("  -> Passed: Invalid QR token safely rejected with HTTP 404.")

    # ----------------------------------------------------
    # Test 9: Organizer Cannot Check In Another Organizer's Event
    # ----------------------------------------------------
    print("\n[Test 9] Testing Organizer 1 attempting check-in on Organizer 2's event...")
    # Org1 tries to check in Bob (who is registered for Org2's event)
    res_unauth = org1_client.post(
        "/api/checkin",
        json={"qr_token": "P5_TOKEN_BOB_ORG2_12345678901234"}
    )
    assert res_unauth.status_code == 403, f"Expected 403 Forbidden, got {res_unauth.status_code}"
    unauth_data = res_unauth.get_json()
    assert unauth_data["success"] is False and "Unauthorized" in unauth_data["message"]
    print("  -> Passed: Cross-organizer check-in rejected with HTTP 403 Unauthorized.")

    # ----------------------------------------------------
    # Test 10: 100-Worker Same-QR Concurrency Benchmark
    # ----------------------------------------------------
    print("\n==================================================")
    print("  MIC Phase 5 Concurrency Benchmark: 100 Concurrent Check-In Requests")
    print("==================================================")

    # Create a fresh registration for concurrency testing
    conn = get_db_connection(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO events (name, event_date, capacity, created_by) VALUES (?, ?, ?, ?)",
        ("P5 Concurrency Benchmark Event", "2026-12-05", 100, org1_id)
    )
    bench_event_id = cursor.lastrowid

    cursor.execute(
        "INSERT INTO registrations (event_id, user_id, qr_token) VALUES (?, ?, ?)",
        (bench_event_id, att2_id, "P5_CONCURRENCY_TEST_TOKEN_SAME_QR_100")
    )
    bench_reg_id = cursor.lastrowid
    conn.commit()
    conn.close()

    print(f"Created Test Registration (Reg ID: {bench_reg_id}, Token: P5_CONCURRENCY_TEST_TOKEN_SAME_QR_100).")
    print("Dispatching 100 simultaneous check-in requests for the SAME QR token using ThreadPoolExecutor(max_workers=100)...")

    def submit_checkin(worker_id):
        worker_client = app.test_client()
        with worker_client.session_transaction() as sess:
            sess["user_id"] = org1_id
            sess["name"] = "Organizer One"
            sess["role"] = "organizer"

        response = worker_client.post(
            "/api/checkin",
            json={"qr_token": "P5_CONCURRENCY_TEST_TOKEN_SAME_QR_100"}
        )
        data = response.get_json() or {}
        return {
            "worker_id": worker_id,
            "status_code": response.status_code,
            "success": (response.status_code == 200 and data.get("success") is True),
            "message": data.get("message", ""),
            "checked_in_at": data.get("checked_in_at", None)
        }

    bench_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
        futures = [executor.submit(submit_checkin, i) for i in range(100)]
        for f in concurrent.futures.as_completed(futures):
            bench_results.append(f.result())

    successful_checkins = [r for r in bench_results if r["success"]]
    rejected_checkins = [r for r in bench_results if not r["success"]]

    # Verify database final state
    conn = get_db_connection(DATABASE_NAME)
    final_row = conn.execute(
        "SELECT checked_in_at FROM registrations WHERE id = ?",
        (bench_reg_id,)
    ).fetchone()
    conn.close()

    final_db_timestamp = final_row["checked_in_at"] if final_row else None

    concurrency_evidence = {
        "benchmark_name": "MIC Phase 5 Same-QR Check-In Concurrency Benchmark",
        "total_concurrent_requests_sent": len(bench_results),
        "concurrency_workers": 100,
        "target_qr_token": "P5_CONCURRENCY_TEST_TOKEN_SAME_QR_100",
        "successful_checkin_requests": len(successful_checkins),
        "duplicate_rejected_requests": len(rejected_checkins),
        "final_sqlite_checked_in_at": final_db_timestamp,
        "multiple_checkins_occurred": (len(successful_checkins) > 1),
        "passed": (len(successful_checkins) == 1 and len(rejected_checkins) == 99 and final_db_timestamp is not None)
    }

    # Save evidence file
    evidence_path = os.path.join(
        "C:\\Users\\sara\\.gemini\\antigravity\\brain\\7018847d-e888-459f-a736-518b28435a99\\scratch",
        "checkin_concurrency_evidence.json"
    )
    with open(evidence_path, "w") as f:
        json.dump(concurrency_evidence, f, indent=2)

    print("\n--- Phase 5 Concurrency Benchmark Results ---")
    print(f"Total Concurrent Requests Sent:     {concurrency_evidence['total_concurrent_requests_sent']}")
    print(f"Worker Pool Size:                  {concurrency_evidence['concurrency_workers']}")
    print(f"Successful Check-Ins:              {concurrency_evidence['successful_checkin_requests']}")
    print(f"Rejected Duplicate Check-Ins:      {concurrency_evidence['duplicate_rejected_requests']}")
    print(f"Final SQLite Timestamp:            {concurrency_evidence['final_sqlite_checked_in_at']}")
    print(f"Evidence File Saved To:            {evidence_path}")
    print("---------------------------------------------")

    assert concurrency_evidence["successful_checkin_requests"] == 1, f"Expected exactly 1 success, got {concurrency_evidence['successful_checkin_requests']}"
    assert concurrency_evidence["duplicate_rejected_requests"] == 99, f"Expected exactly 99 rejections, got {concurrency_evidence['duplicate_rejected_requests']}"
    assert concurrency_evidence["final_sqlite_checked_in_at"] is not None, "Timestamp not set in SQLite"
    assert not concurrency_evidence["multiple_checkins_occurred"], "Race condition detected! Multiple check-ins succeeded."

    print("  -> Passed: Exactly 1 check-in succeeded and 99 were rejected as duplicates under 100 concurrent workers.")

    # ----------------------------------------------------
    # Clean up test data
    # ----------------------------------------------------
    conn = get_db_connection(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registrations WHERE event_id IN (SELECT id FROM events WHERE name LIKE 'P5 %');")
    cursor.execute("DELETE FROM events WHERE name LIKE 'P5 %';")
    cursor.execute("DELETE FROM users WHERE email IN ('p5_org1@test.com', 'p5_org2@test.com', 'p5_att1@test.com', 'p5_att2@test.com');")
    conn.commit()
    conn.close()

    print("\n==================================================")
    print("  ALL PHASE 5 TESTS + CONCURRENCY PASSED!         ")
    print("==================================================")

if __name__ == "__main__":
    run_phase5_tests()
