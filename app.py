from flask import Flask, request, jsonify, send_from_directory, session
import sqlite3
import os
import secrets
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "gomerry.db")

GROUP_SIZE = 10
REGISTRATION_FEE = 1.00

# Available contribution ranges.
# Users see these in batches through the /api/ranges endpoint.
RANGES = [
    (5, 9),
    (10, 19),
    (20, 29),
    (30, 39),
    (40, 49),
    (50, 59),
    (60, 69),
    (70, 79),
    (80, 89),
    (90, 99),
    (100, 149),
    (150, 199),
    (200, 299),
    (300, 399),
    (400, 499),
    (500, 599),
    (600, 699),
    (700, 799),
    (800, 899),
    (900, 999),
]


def now():
    return datetime.utcnow().isoformat(timespec="seconds")


def get_db():
    db = sqlite3.connect(DB_FILE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db():
    db = get_db()

    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            registration_paid INTEGER NOT NULL DEFAULT 0,
            registered_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS registration_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            status TEXT NOT NULL DEFAULT 'pending',
            provider_reference TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS selections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            range_min REAL NOT NULL,
            range_max REAL NOT NULL,
            selected_amount REAL NOT NULL,
            selected_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS merry_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            range_min REAL NOT NULL,
            range_max REAL NOT NULL,
            group_size INTEGER NOT NULL DEFAULT 10,
            member_count INTEGER NOT NULL DEFAULT 0,
            lifetime_amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'waiting',
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL UNIQUE,
            selected_amount REAL NOT NULL,
            position INTEGER NOT NULL,
            joined_at TEXT NOT NULL,
            FOREIGN KEY(group_id) REFERENCES merry_groups(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            round_number INTEGER NOT NULL,
            beneficiary_user_id INTEGER,
            status TEXT NOT NULL DEFAULT 'waiting',
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY(group_id) REFERENCES merry_groups(id),
            FOREIGN KEY(beneficiary_user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS contributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            payer_user_id INTEGER NOT NULL,
            beneficiary_user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            status TEXT NOT NULL DEFAULT 'pending',
            provider_reference TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(round_id) REFERENCES rounds(id),
            FOREIGN KEY(group_id) REFERENCES merry_groups(id),
            FOREIGN KEY(payer_user_id) REFERENCES users(id),
            FOREIGN KEY(beneficiary_user_id) REFERENCES users(id)
        );
    """)

    db.commit()
    db.close()


def row_to_dict(row):
    return dict(row) if row else None


def find_range(range_min, range_max):
    for minimum, maximum in RANGES:
        if float(minimum) == float(range_min) and float(maximum) == float(range_max):
            return minimum, maximum
    return None


def user_is_paid(db, user_id):
    row = db.execute(
        "SELECT registration_paid FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    return bool(row and row["registration_paid"] == 1)


def get_user(user_id):
    db = get_db()
    row = db.execute(
        """
        SELECT id, name, phone, registration_paid, registered_at
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    ).fetchone()
    db.close()
    return row


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/picker")
def picker():
    return send_from_directory(BASE_DIR, "picker.html")


@app.route("/admin")
def admin():
    return send_from_directory(BASE_DIR, "admin.html")


@app.route("/healthz")
def healthz():
    return jsonify({
        "status": "ok",
        "service": "Go Merry Pata Pesa"
    })


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    password = str(data.get("password", ""))

    if not name:
        return jsonify({"error": "Name is required"}), 400

    if not phone:
        return jsonify({"error": "Phone is required"}), 400

    if len(password) < 4:
        return jsonify({"error": "Password must contain at least 4 characters"}), 400

    db = get_db()

    existing = db.execute(
        "SELECT id FROM users WHERE phone = ?",
        (phone,)
    ).fetchone()

    if existing:
        db.close()
        return jsonify({"error": "A user with this phone already exists"}), 409

    cursor = db.execute(
        """
        INSERT INTO users
        (name, phone, password, registration_paid, registered_at)
        VALUES (?, ?, ?, 0, ?)
        """,
        (name, phone, password, now())
    )

    user_id = cursor.lastrowid

    # Create the registration payment record.
    db.execute(
        """
        INSERT INTO registration_payments
        (user_id, amount, currency, status, created_at)
        VALUES (?, ?, 'USD', 'pending', ?)
        """,
        (user_id, REGISTRATION_FEE, now())
    )

    db.commit()
    db.close()

    session["user_id"] = user_id

    return jsonify({
        "success": True,
        "user_id": user_id,
        "registration_fee": REGISTRATION_FEE,
        "currency": "USD",
        "payment_required": True,
        "message": "Registration created. Pay the $1 registration fee before selecting a range."
    }), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    phone = str(data.get("phone", "")).strip()
    password = str(data.get("password", ""))

    db = get_db()

    user = db.execute(
        """
        SELECT id, name, phone, registration_paid
        FROM users
        WHERE phone = ? AND password = ?
        """,
        (phone, password)
    ).fetchone()

    db.close()

    if not user:
        return jsonify({"error": "Invalid phone or password"}), 401

    session["user_id"] = user["id"]

    return jsonify({
        "success": True,
        "user": dict(user)
    })


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/api/me")
def me():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({
            "logged_in": False
        })

    user = get_user(user_id)

    if not user:
        session.clear()
        return jsonify({
            "logged_in": False
        })

    db = get_db()

    selection = db.execute(
        """
        SELECT range_min, range_max, selected_amount, selected_at
        FROM selections
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()

    membership = db.execute(
        """
        SELECT
            gm.group_id,
            gm.position,
            gm.selected_amount,
            mg.range_min,
            mg.range_max,
            mg.group_size,
            mg.member_count,
            mg.lifetime_amount,
            mg.status
        FROM group_members gm
        JOIN merry_groups mg ON mg.id = gm.group_id
        WHERE gm.user_id = ?
        """,
        (user_id,)
    ).fetchone()

    db.close()

    result = {
        "logged_in": True,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "phone": user["phone"],
            "registration_paid": bool(user["registration_paid"])
        },
        "selection": row_to_dict(selection),
        "membership": row_to_dict(membership)
    }

    return jsonify(result)


@app.route("/api/pay-registration", methods=["POST"])
def pay_registration():
    """
    DEVELOPMENT endpoint.

    This marks the $1 registration as paid for testing only.
    Replace this endpoint with the real payment-provider callback
    before using the application with real money.
    """

    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"error": "Login/register first"}), 401

    db = get_db()

    user = db.execute(
        "SELECT id FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    if not user:
        db.close()
        return jsonify({"error": "User not found"}), 404

    db.execute(
        """
        UPDATE users
        SET registration_paid = 1
        WHERE id = ?
        """,
        (user_id,)
    )

    db.execute(
        """
        UPDATE registration_payments
        SET status = 'paid'
        WHERE id = (
            SELECT id
            FROM registration_payments
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
        )
        """,
        (user_id,)
    )

    db.commit()
    db.close()

    return jsonify({
        "success": True,
        "message": "Registration payment recorded as paid for development testing.",
        "amount": REGISTRATION_FEE,
        "currency": "USD"
    })


@app.route("/api/ranges")
def ranges():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"error": "Login/register first"}), 401

    db = get_db()

    if not user_is_paid(db, user_id):
        db.close()
        return jsonify({
            "error": "Pay the $1 registration fee before choosing a range."
        }), 403

    # Return the number of members currently waiting in each range.
    result = []

    for minimum, maximum in RANGES:
        count = db.execute(
            """
            SELECT COUNT(*)
            FROM selections s
            LEFT JOIN group_members gm ON gm.user_id = s.user_id
            WHERE s.range_min = ?
              AND s.range_max = ?
              AND gm.user_id IS NULL
            """,
            (minimum, maximum)
        ).fetchone()[0]

        result.append({
            "min": minimum,
            "max": maximum,
            "members_waiting": count,
            "group_size": GROUP_SIZE
        })

    db.close()

    return jsonify({
        "ranges": result
    })


@app.route("/api/range/<int:range_min>/<int:range_max>")
def range_information(range_min, range_max):
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"error": "Login/register first"}), 401

    valid = find_range(range_min, range_max)

    if not valid:
        return jsonify({"error": "Invalid range"}), 400

    db = get_db()

    members = db.execute(
        """
        SELECT
            u.id,
            u.name,
            s.selected_amount,
            s.selected_at
        FROM selections s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN group_members gm ON gm.user_id = s.user_id
        WHERE s.range_min = ?
          AND s.range_max = ?
          AND gm.user_id IS NULL
        ORDER BY s.selected_at ASC
        """,
        (range_min, range_max)
    ).fetchall()

    count = len(members)

    db.close()

    return jsonify({
        "range": {
            "min": range_min,
            "max": range_max
        },
        "members_waiting": count,
        "group_size": GROUP_SIZE,
        "places_remaining": max(GROUP_SIZE - count, 0),
        "members": [dict(member) for member in members]
    })


@app.route("/api/select-range", methods=["POST"])
def select_range():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"error": "Login/register first"}), 401

    data = request.get_json(silent=True) or {}

    try:
        range_min = float(data["range_min"])
        range_max = float(data["range_max"])
        selected_amount = float(data["selected_amount"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Valid range and amount are required"}), 400

    valid = find_range(range_min, range_max)

    if not valid:
        return jsonify({"error": "That range is not available"}), 400

    if selected_amount < range_min or selected_amount > range_max:
        return jsonify({
            "error": "Selected amount must be inside the selected range"
        }), 400

    db = get_db()

    if not user_is_paid(db, user_id):
        db.close()
        return jsonify({
            "error": "Pay the $1 registration fee before selecting a range."
        }), 403

    # Do not allow a member already inside a group to change selection.
    existing_member = db.execute(
        """
        SELECT group_id
        FROM group_members
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()

    if existing_member:
        db.close()
        return jsonify({
            "error": "You are already a member of a merry-go-round group."
        }), 409

    existing_selection = db.execute(
        """
        SELECT id
        FROM selections
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()

    if existing_selection:
        db.execute(
            """
            UPDATE selections
            SET range_min = ?,
                range_max = ?,
                selected_amount = ?,
                selected_at = ?
            WHERE user_id = ?
            """,
            (
                range_min,
                range_max,
                selected_amount,
                now(),
                user_id
            )
        )
    else:
        db.execute(
            """
            INSERT INTO selections
            (user_id, range_min, range_max, selected_amount, selected_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                range_min,
                range_max,
                selected_amount,
                now()
            )
        )

    db.commit()

    # Count all people who selected this range and have not yet joined
    # a completed/active group.
    waiting_count = db.execute(
        """
        SELECT COUNT(*)
        FROM selections s
        LEFT JOIN group_members gm ON gm.user_id = s.user_id
        WHERE s.range_min = ?
          AND s.range_max = ?
          AND gm.user_id IS NULL
        """,
        (range_min, range_max)
    ).fetchone()[0]

    db.close()

    return jsonify({
        "success": True,
        "range_min": range_min,
        "range_max": range_max,
        "selected_amount": selected_amount,
        "members_waiting": waiting_count,
        "group_size": GROUP_SIZE,
        "message": "Range and contribution amount saved."
    })


@app.route("/api/join-group", methods=["POST"])
def join_group():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"error": "Login/register first"}), 401

    db = get_db()

    if not user_is_paid(db, user_id):
        db.close()
        return jsonify({"error": "Registration payment is required"}), 403

    selection = db.execute(
        """
        SELECT range_min, range_max, selected_amount
        FROM selections
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()

    if not selection:
        db.close()
        return jsonify({
            "error": "Select a range and amount first."
        }), 400

    already = db.execute(
        """
        SELECT group_id
        FROM group_members
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()

    if already:
        db.close()
        return jsonify({
            "error": "You are already in a merry-go-round group.",
            "group_id": already["group_id"]
        }), 409

    range_min = selection["range_min"]
    range_max = selection["range_max"]

    # Find a waiting group for exactly this range.
    group = db.execute(
        """
        SELECT *
        FROM merry_groups
        WHERE range_min = ?
          AND range_max = ?
          AND status = 'waiting'
          AND member_count < group_size
        ORDER BY id ASC
        LIMIT 1
        """,
        (range_min, range_max)
    ).fetchone()

    if not group:
        # Highest amount in the range x 10 is stored ONCE as the
        # lifetime group amount.
        lifetime_amount = range_max * GROUP_SIZE

        cursor = db.execute(
            """
            INSERT INTO merry_groups
            (
                range_min,
                range_max,
                group_size,
                member_count,
                lifetime_amount,
                status,
                created_at
            )
            VALUES (?, ?, ?, 0, ?, 'waiting', ?)
            """,
            (
                range_min,
                range_max,
                GROUP_SIZE,
                lifetime_amount,
                now()
            )
        )

        group_id = cursor.lastrowid

        group = db.execute(
            "SELECT * FROM merry_groups WHERE id = ?",
            (group_id,)
        ).fetchone()

    group_id = group["id"]

    position = group["member_count"] + 1

    db.execute(
        """
        INSERT INTO group_members
        (
            group_id,
            user_id,
            selected_amount,
            position,
            joined_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            group_id,
            user_id,
            selection["selected_amount"],
            position,
            now()
        )
    )

    new_count = position

    if new_count >= GROUP_SIZE:
        db.execute(
            """
            UPDATE merry_groups
            SET member_count = ?,
                status = 'active',
                started_at = ?
            WHERE id = ?
            """,
            (new_count, now(), group_id)
        )

        # Create the first round.
        first_member = db.execute(
            """
            SELECT user_id
            FROM group_members
            WHERE group_id = ?
            ORDER BY position ASC
            LIMIT 1
            """,
            (group_id,)
        ).fetchone()

        db.execute(
            """
            INSERT INTO rounds
            (
                group_id,
                round_number,
                beneficiary_user_id,
                status,
                created_at
            )
            VALUES (?, 1, ?, 'active', ?)
            """,
            (
                group_id,
                first_member["user_id"],
                now()
            )
        )

        group_status = "active"
        message = "The group has reached 10 members and the merry-go-round is ready to begin."
    else:
        db.execute(
            """
            UPDATE merry_groups
            SET member_count = ?
            WHERE id = ?
            """,
            (new_count, group_id)
        )

        group_status = "waiting"
        message = "You have joined the waiting group. The group will start when it reaches 10 members."

    db.commit()

    members = db.execute(
        """
        SELECT
            gm.position,
            u.id AS user_id,
            u.name,
            gm.selected_amount
        FROM group_members gm
        JOIN users u ON u.id = gm.user_id
        WHERE gm.group_id = ?
        ORDER BY gm.position ASC
        """,
        (group_id,)
    ).fetchall()

    updated_group = db.execute(
        """
        SELECT *
        FROM merry_groups
        WHERE id = ?
        """,
        (group_id,)
    ).fetchone()

    db.close()

    return jsonify({
        "success": True,
        "message": message,
        "group": dict(updated_group),
        "members": [dict(member) for member in members],
        "members_needed": max(GROUP_SIZE - new_count, 0)
    })


@app.route("/api/group/<int:group_id>")
def group_details(group_id):
    db = get_db()

    group = db.execute(
        """
        SELECT *
        FROM merry_groups
        WHERE id = ?
        """,
        (group_id,)
    ).fetchone()

    if not group:
        db.close()
        return jsonify({"error": "Group not found"}), 404

    members = db.execute(
        """
        SELECT
            gm.position,
            u.id AS user_id,
            u.name,
            gm.selected_amount,
            gm.joined_at
        FROM group_members gm
        JOIN users u ON u.id = gm.user_id
        WHERE gm.group_id = ?
        ORDER BY gm.position
        """,
        (group_id,)
    ).fetchall()

    rounds = db.execute(
        """
        SELECT
            r.id,
            r.round_number,
            r.beneficiary_user_id,
            u.name AS beneficiary_name,
            r.status,
            r.created_at,
            r.completed_at
        FROM rounds r
        LEFT JOIN users u
            ON u.id = r.beneficiary_user_id
        WHERE r.group_id = ?
        ORDER BY r.round_number
        """,
        (group_id,)
    ).fetchall()

    db.close()

    return jsonify({
        "group": dict(group),
        "members": [dict(member) for member in members],
        "rounds": [dict(round_row) for round_row in rounds]
    })


@app.route("/api/my-group")
def my_group():
    user_id = session.get("user_id")

    if not user_id:
        return jsonify({"error": "Login/register first"}), 401

    db = get_db()

    membership = db.execute(
        """
        SELECT group_id
        FROM group_members
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()

    db.close()

    if not membership:
        return jsonify({
            "group": None,
            "message": "You are not in a group yet."
        })

    return group_details(membership["group_id"])


@app.route("/api/admin/overview")
def admin_overview():
    """
    Basic monitoring endpoint.
    Protect this with real authentication before production use.
    """

    db = get_db()

    users = db.execute(
        "SELECT COUNT(*) AS count FROM users"
    ).fetchone()["count"]

    paid_users = db.execute(
        """
        SELECT COUNT(*) AS count
        FROM users
        WHERE registration_paid = 1
        """
    ).fetchone()["count"]

    selected_users = db.execute(
        "SELECT COUNT(*) AS count FROM selections"
    ).fetchone()["count"]

    groups = db.execute(
        "SELECT COUNT(*) AS count FROM merry_groups"
    ).fetchone()["count"]

    waiting_groups = db.execute(
        """
        SELECT COUNT(*) AS count
        FROM merry_groups
        WHERE status = 'waiting'
        """
    ).fetchone()["count"]

    active_groups = db.execute(
        """
        SELECT COUNT(*) AS count
        FROM merry_groups
        WHERE status = 'active'
        """
    ).fetchone()["count"]

    ranges = db.execute(
        """
        SELECT
            range_min,
            range_max,
            COUNT(*) AS members
        FROM selections
        GROUP BY range_min, range_max
        ORDER BY range_min
        """
    ).fetchall()

    db.close()

    return jsonify({
        "users": users,
        "paid_users": paid_users,
        "selected_users": selected_users,
        "groups": groups,
        "waiting_groups": waiting_groups,
        "active_groups": active_groups,
        "range_counts": [dict(row) for row in ranges]
    })


@app.route("/api/admin/groups")
def admin_groups():
    db = get_db()

    groups = db.execute(
        """
        SELECT
            id,
            range_min,
            range_max,
            group_size,
            member_count,
            lifetime_amount,
            status,
            created_at,
            started_at,
            completed_at
        FROM merry_groups
        ORDER BY id DESC
        """
    ).fetchall()

    db.close()

    return jsonify({
        "groups": [dict(group) for group in groups]
    })


@app.route("/api/admin/range/<int:range_min>/<int:range_max>")
def admin_range(range_min, range_max):
    valid = find_range(range_min, range_max)

    if not valid:
        return jsonify({"error": "Invalid range"}), 400

    db = get_db()

    people = db.execute(
        """
        SELECT
            u.id,
            u.name,
            u.phone,
            s.selected_amount,
            s.selected_at,
            gm.group_id,
            gm.position
        FROM selections s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN group_members gm ON gm.user_id = s.user_id
        WHERE s.range_min = ?
          AND s.range_max = ?
        ORDER BY s.selected_at ASC
        """,
        (range_min, range_max)
    ).fetchall()

    db.close()

    return jsonify({
        "range_min": range_min,
        "range_max": range_max,
        "people": [dict(person) for person in people]
    })


@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Not found"
    }), 404


@app.errorhandler(500)
def server_error(error):
    return jsonify({
        "error": "Internal server error"
    }), 500


init_db()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
