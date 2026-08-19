import os
import io
import base64
import secrets
import sqlite3
from datetime import datetime
from functools import wraps
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    abort,
    jsonify,
)
import qrcode
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db_connection

app = Flask(__name__)

# Secret key configuration for secure session management
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key_mic_event_checkin_2026")


# ==============================================================================
# Helper Functions
# ==============================================================================

def generate_qr_base64(token: str) -> str:
    """
    Generates a PNG QR code for a given token and returns it as a base64 data string.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(token)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# ==============================================================================
# Helper Decorators for Authentication & Role-Based Access Control
# ==============================================================================

def login_required(f):
    """
    Ensures that a user is logged in before accessing the route.
    Redirects to the login page if not authenticated.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def role_required(required_role):
    """
    Ensures that the logged-in user possesses the required role ('organizer' or 'attendee').
    Returns HTTP 403 Forbidden if the user's role does not match.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to access this page.", "warning")
                return redirect(url_for("login"))
            if session.get("role") != required_role:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ==============================================================================
# Core Routes
# ==============================================================================

@app.route("/")
def index():
    """
    Landing page showing system status and navigation options.
    """
    return render_template("index.html")


@app.route("/health")
def health():
    """
    Health-check endpoint.
    """
    return jsonify({"status": "ok"})


# ==============================================================================
# Authentication Routes
# ==============================================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    """
    Handles new user registration for Organizers and Attendees.
    Hashes passwords using Werkzeug and validates unique emails.
    """
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "").strip().lower()

        # Validate required fields
        if not name or not email or not password or not role:
            flash("All fields are required.", "error")
            return render_template("register.html", name=name, email=email, role=role), 400

        # Validate role selection
        if role not in ["organizer", "attendee"]:
            flash("Invalid role selected. Must be Organizer or Attendee.", "error")
            return render_template("register.html", name=name, email=email, role=role), 400

        conn = get_db_connection()
        try:
            # Check if email is already registered
            existing_user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing_user:
                flash("An account with this email already exists. Please log in.", "error")
                return render_template("register.html", name=name, email=email, role=role), 400

            # Hash the password and save the user
            password_hash = generate_password_hash(password)
            conn.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
                (name, email, password_hash, role),
            )
            conn.commit()
        finally:
            conn.close()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Handles user login, password verification, and session creation.
    Redirects organizers to /organizer and attendees to /attendee.
    """
    # If already logged in, redirect directly to user's area
    if "user_id" in session:
        if session.get("role") == "organizer":
            return redirect(url_for("organizer_dashboard"))
        return redirect(url_for("attendee_area"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter both email and password.", "error")
            return render_template("login.html", email=email), 400

        conn = get_db_connection()
        try:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        finally:
            conn.close()

        # Verify user credentials
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("login.html", email=email), 401

        # Clear any prior session data and store new session values
        session.clear()
        session["user_id"] = user["id"]
        session["name"] = user["name"]
        session["role"] = user["role"]

        flash(f"Welcome back, {user['name']}!", "success")

        # Redirect according to role
        if user["role"] == "organizer":
            return redirect(url_for("organizer_dashboard"))
        else:
            return redirect(url_for("attendee_area"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    """
    Clears the Flask session and redirects to the login page.
    """
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("login"))


# ==============================================================================
# Role-Protected Dashboards
# ==============================================================================

@app.route("/organizer")
@login_required
@role_required("organizer")
def organizer_dashboard():
    """
    Organizer-only dashboard.
    """
    return render_template("organizer.html", name=session.get("name"))


@app.route("/attendee")
@login_required
@role_required("attendee")
def attendee_area():
    """
    Attendee-only area.
    """
    return render_template("attendee.html", name=session.get("name"))


# ==============================================================================
# Event Management Routes (Phase 3 & Phase 4)
# ==============================================================================

@app.route("/events/create", methods=["GET", "POST"])
@login_required
@role_required("organizer")
def create_event():
    """
    Handles event creation by authenticated organizers.
    Validates name, capacity (positive integer), and event date.
    """
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        event_date = request.form.get("event_date", "").strip()
        capacity_raw = request.form.get("capacity", "").strip()

        # 1. Validate required fields
        if not name or not event_date or not capacity_raw:
            flash("All fields are required.", "error")
            return render_template(
                "create_event.html",
                name=name,
                event_date=event_date,
                capacity=capacity_raw,
            ), 400

        # 2. Validate capacity is a positive integer
        try:
            capacity = int(capacity_raw)
            if capacity <= 0:
                flash("Capacity must be a positive number greater than 0.", "error")
                return render_template(
                    "create_event.html",
                    name=name,
                    event_date=event_date,
                    capacity=capacity_raw,
                ), 400
        except ValueError:
            flash("Capacity must be a valid whole number.", "error")
            return render_template(
                "create_event.html",
                name=name,
                event_date=event_date,
                capacity=capacity_raw,
            ), 400

        # 3. Validate event date format
        try:
            datetime.strptime(event_date, "%Y-%m-%d")
        except ValueError:
            flash("Invalid date format. Please use YYYY-MM-DD.", "error")
            return render_template(
                "create_event.html",
                name=name,
                event_date=event_date,
                capacity=capacity_raw,
            ), 400

        # 4. Insert event into database with created_by set to current organizer
        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO events (name, event_date, capacity, created_by) VALUES (?, ?, ?, ?)",
                (name, event_date, capacity, session["user_id"]),
            )
            conn.commit()
        finally:
            conn.close()

        flash(f"Event '{name}' created successfully!", "success")
        return redirect(url_for("organizer_events"))

    return render_template("create_event.html")


@app.route("/organizer/events")
@login_required
@role_required("organizer")
def organizer_events():
    """
    Displays the list of events created by the currently logged-in organizer.
    """
    conn = get_db_connection()
    try:
        events = conn.execute(
            """
            SELECT e.id, e.name, e.event_date, e.capacity,
                   (SELECT COUNT(*) FROM registrations WHERE event_id = e.id) AS registered_count
            FROM events e
            WHERE e.created_by = ?
            ORDER BY e.event_date ASC, e.id DESC
            """,
            (session["user_id"],),
        ).fetchall()
    finally:
        conn.close()

    return render_template("organizer_events.html", events=events, name=session.get("name"))


@app.route("/events")
@login_required
@role_required("attendee")
def attendee_events():
    """
    Displays available events for attendees with remaining seats and registration status.
    """
    conn = get_db_connection()
    try:
        events = conn.execute(
            """
            SELECT e.id, e.name, e.event_date, e.capacity,
                   (SELECT COUNT(*) FROM registrations WHERE event_id = e.id) AS registered_count,
                   (SELECT COUNT(*) FROM registrations WHERE event_id = e.id AND user_id = ?) AS is_registered
            FROM events e
            ORDER BY e.event_date ASC, e.id DESC
            """,
            (session["user_id"],),
        ).fetchall()
    finally:
        conn.close()

    return render_template("attendee_events.html", events=events, name=session.get("name"))


# ==============================================================================
# Phase 4: Attendee Registration & QR Badge Routes
# ==============================================================================

@app.route("/events/<int:event_id>/register", methods=["POST"])
@login_required
@role_required("attendee")
def register_for_event(event_id):
    """
    Registers the authenticated attendee for the specified event.
    Enforces atomic capacity limits and prevents duplicate registrations.
    """
    conn = get_db_connection()
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE;")

        # 1. Verify event exists
        event = conn.execute(
            "SELECT id, name, capacity FROM events WHERE id = ?", (event_id,)
        ).fetchone()

        if not event:
            conn.execute("ROLLBACK;")
            flash("Event not found.", "error")
            return redirect(url_for("attendee_events"))

        # 2. Check if attendee is already registered
        existing_reg = conn.execute(
            "SELECT id FROM registrations WHERE event_id = ? AND user_id = ?",
            (event_id, session["user_id"]),
        ).fetchone()

        if existing_reg:
            conn.execute("ROLLBACK;")
            flash("You are already registered for this event.", "warning")
            return redirect(url_for("attendee_registrations"))

        # 3. Check current registration count against event capacity
        count_row = conn.execute(
            "SELECT COUNT(*) AS count FROM registrations WHERE event_id = ?", (event_id,)
        ).fetchone()
        current_count = count_row["count"]

        if current_count >= event["capacity"]:
            conn.execute("ROLLBACK;")
            flash(f"Registration closed: '{event['name']}' has reached maximum capacity.", "error")
            return redirect(url_for("attendee_events"))

        # 4. Generate cryptographically random, unpredictable QR token
        qr_token = secrets.token_urlsafe(32)

        # 5. Insert registration record
        conn.execute(
            "INSERT INTO registrations (event_id, user_id, qr_token) VALUES (?, ?, ?)",
            (event_id, session["user_id"], qr_token),
        )
        conn.execute("COMMIT;")
    except sqlite3.IntegrityError:
        try:
            conn.execute("ROLLBACK;")
        except Exception:
            pass
        flash("Registration could not be completed (duplicate registration detected).", "error")
        return redirect(url_for("attendee_events"))
    except Exception:
        try:
            conn.execute("ROLLBACK;")
        except Exception:
            pass
        flash("A server error occurred during registration. Please try again.", "error")
        return redirect(url_for("attendee_events"))
    finally:
        conn.close()

    flash(f"Successfully registered for '{event['name']}'! Your QR badge is ready.", "success")
    return redirect(url_for("attendee_registrations"))


@app.route("/attendee/registrations")
@login_required
@role_required("attendee")
def attendee_registrations():
    """
    Displays the authenticated attendee's registered events with unique QR badges.
    """
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT r.id AS reg_id, r.qr_token, r.registered_at, r.checked_in_at,
                   e.id AS event_id, e.name AS event_name, e.event_date, e.capacity
            FROM registrations r
            JOIN events e ON r.event_id = e.id
            WHERE r.user_id = ?
            ORDER BY r.registered_at DESC
            """,
            (session["user_id"],),
        ).fetchall()
    finally:
        conn.close()

    # Generate QR codes for each registration
    registrations = []
    for r in rows:
        qr_b64 = generate_qr_base64(r["qr_token"])
        status = "Checked In" if r["checked_in_at"] else "Not checked in"
        registrations.append({
            "reg_id": r["reg_id"],
            "event_id": r["event_id"],
            "event_name": r["event_name"],
            "event_date": r["event_date"],
            "capacity": r["capacity"],
            "qr_token": r["qr_token"],
            "qr_base64": qr_b64,
            "registered_at": r["registered_at"],
            "status": status,
            "is_checked_in": bool(r["checked_in_at"]),
        })

    return render_template(
        "attendee_registrations.html",
        registrations=registrations,
        name=session.get("name"),
    )


# ==============================================================================
# Error Handlers
# ==============================================================================

@app.errorhandler(403)
def forbidden(error):
    """
    Custom 403 Forbidden handler.
    """
    return render_template("403.html"), 403


@app.errorhandler(404)
def not_found(error):
    """
    Custom 404 Not Found handler.
    """
    return render_template("403.html"), 404


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
