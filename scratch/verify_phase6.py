import os
import sys

# Make sure the project root is importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app import app


passed = 0
failed = 0


def check(name, condition):
    global passed, failed

    if condition:
        print(f"[PASS] {name}")
        passed += 1
    else:
        print(f"[FAIL] {name}")
        failed += 1


print("=" * 60)
print("PHASE 6 VERIFICATION")
print("=" * 60)


# ---------------------------------------------------------
# 1. Required files
# ---------------------------------------------------------

required_files = [
    "templates/organizer_dashboard.html",
    "templates/insights.html",
    "templates/scanner.html",
    "templates/organizer.html",
    "templates/organizer_events.html",
]

for file_path in required_files:
    check(
        f"File exists: {file_path}",
        os.path.exists(os.path.join(PROJECT_ROOT, file_path))
    )


# ---------------------------------------------------------
# 2. Required routes
# ---------------------------------------------------------

routes = {rule.rule for rule in app.url_map.iter_rules()}

check(
    "Organizer dashboard route exists",
    "/organizer/dashboard/<int:event_id>" in routes
)

check(
    "CSV export route exists",
    "/organizer/dashboard/<int:event_id>/export" in routes
)

check(
    "AI insights route exists",
    "/organizer/dashboard/<int:event_id>/insights" in routes
)

check(
    "Phase 5 check-in route still exists",
    "/api/checkin" in routes
)


# ---------------------------------------------------------
# 3. Dashboard HTML requirements
# ---------------------------------------------------------

dashboard_path = os.path.join(
    PROJECT_ROOT,
    "templates",
    "organizer_dashboard.html"
)

with open(dashboard_path, "r", encoding="utf-8") as f:
    dashboard = f.read()

check(
    "Dashboard has 10-second auto refresh",
    'http-equiv="refresh"' in dashboard and 'content="10"' in dashboard
)

check(
    "Dashboard contains registered/check-in statistics",
    "Registered" in dashboard and "Checked" in dashboard
)

check(
    "Dashboard contains attendee table",
    "<table" in dashboard.lower()
)

check(
    "Dashboard contains CSV export link",
    "export" in dashboard.lower()
)

check(
    "Dashboard contains AI Insights link",
    "insights" in dashboard.lower()
)


# ---------------------------------------------------------
# 4. Scanner offline requirements
# ---------------------------------------------------------

scanner_path = os.path.join(
    PROJECT_ROOT,
    "templates",
    "scanner.html"
)

with open(scanner_path, "r", encoding="utf-8") as f:
    scanner = f.read()

check(
    "Scanner contains online/offline detection",
    "navigator.onLine" in scanner
)

check(
    "Scanner uses localStorage queue",
    "localStorage" in scanner
)

check(
    "Scanner has queue synchronization",
    "syncQueue" in scanner
)

check(
    "Scanner has offline handling",
    '"offline"' in scanner or "'offline'" in scanner
)

check(
    "Scanner has token submission logic",
    "submitToken" in scanner
)


# ---------------------------------------------------------
# 5. Insights requirements
# ---------------------------------------------------------

insights_path = os.path.join(
    PROJECT_ROOT,
    "templates",
    "insights.html"
)

with open(insights_path, "r", encoding="utf-8") as f:
    insights = f.read()

check(
    "Insights template exists and has content",
    len(insights.strip()) > 100
)

check(
    "Insights contains AI/fallback wording",
    "AI" in insights or "fallback" in insights.lower()
)


# ---------------------------------------------------------
# 6. Security / unauthenticated access
# ---------------------------------------------------------

client = app.test_client()

response = client.get("/organizer/dashboard/1")

check(
    "Unauthenticated dashboard request is blocked",
    response.status_code in (302, 401, 403)
)

response = client.get("/organizer/dashboard/1/export")

check(
    "Unauthenticated CSV request is blocked",
    response.status_code in (302, 401, 403)
)

response = client.get("/organizer/dashboard/1/insights")

check(
    "Unauthenticated insights request is blocked",
    response.status_code in (302, 401, 403)
)


# ---------------------------------------------------------
# Final result
# ---------------------------------------------------------

print()
print("=" * 60)
print(f"PASSED: {passed}")
print(f"FAILED: {failed}")
print("=" * 60)

if failed == 0:
    print("ALL PHASE 6 VERIFICATION CHECKS PASSED")
    sys.exit(0)
else:
    print("PHASE 6 VERIFICATION HAS FAILURES")
    sys.exit(1)