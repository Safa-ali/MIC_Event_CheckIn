import sqlite3

DATABASE_NAME = "event_checkin.db"


def get_db_connection(db_name=DATABASE_NAME):
    """
    Creates and returns a connection to the SQLite database.
    Enables foreign key constraint enforcement, row access by column name,
    and a 30-second timeout for concurrent write operations.
    """
    conn = sqlite3.connect(db_name, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_name=DATABASE_NAME):
    """
    Initializes the SQLite database with the required tables for Phase 1.
    Creates 'users', 'events', and 'registrations' tables if they do not exist.
    """
    conn = get_db_connection(db_name)
    cursor = conn.cursor()

    # 1. Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'attendee'
        );
    """)

    # 2. Events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            event_date TEXT NOT NULL,
            capacity INTEGER NOT NULL,
            created_by INTEGER NOT NULL,
            FOREIGN KEY (created_by) REFERENCES users (id)
        );
    """)

    # 3. Registrations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            qr_token TEXT UNIQUE,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            checked_in_at TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES events (id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE (event_id, user_id)
        );
    """)

    conn.commit()
    conn.close()
    print(f"Database '{db_name}' initialized successfully.")


if __name__ == "__main__":
    init_db()
