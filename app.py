import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "Frontend")
DB_PATH = os.path.join(BASE_DIR, "civicconnect.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            mobile TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_code TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            complaint_type TEXT NOT NULL,
            area TEXT NOT NULL,
            severity TEXT NOT NULL,
            people_affected INTEGER NOT NULL,
            description TEXT NOT NULL,
            image_path TEXT,
            status TEXT NOT NULL DEFAULT 'Submitted',
            ai_priority TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL,
            mobile TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            department TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )

    existing_admin = conn.execute(
        "SELECT id FROM admins WHERE admin_id = ?", ("ADMIN001",)
    ).fetchone()
    if not existing_admin:
        conn.execute(
            """
            INSERT INTO admins (
                admin_id, full_name, email, mobile, password_hash, role, department, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ADMIN001",
                "Central Administrator",
                "admin@civicconnect.gov",
                "9876543210",
                generate_password_hash("admin123"),
                "System Administrator",
                "Municipal Corporation",
                datetime.now().isoformat(),
            ),
        )

    conn.commit()
    conn.close()


def predict_priority(severity, people_affected):
    score = 0
    if severity == "High":
        score += 3
    elif severity == "Medium":
        score += 2
    else:
        score += 1

    if people_affected >= 100:
        score += 3
    elif people_affected >= 50:
        score += 2
    elif people_affected >= 10:
        score += 1

    if score >= 5:
        return "High"
    if score >= 3:
        return "Medium"
    return "Low"


def generate_complaint_code(conn):
    year = datetime.now().year
    count = conn.execute(
        "SELECT COUNT(*) AS total FROM complaints WHERE complaint_code LIKE ?",
        (f"CIV{year}%",),
    ).fetchone()["total"]
    return f"CIV{year}{count + 1:03d}"


def format_date(value):
    try:
        return datetime.fromisoformat(value).strftime("%d %B %Y")
    except ValueError:
        return value


DEPARTMENT_MAP = {
    "Pothole": "Engineering",
    "Road Damage": "Engineering",
    "Garbage Overflow": "Sanitation",
    "Water Leakage": "Water",
    "Drainage Issue": "Water",
    "Streetlight Damage": "Electrical",
}


def build_insights(summary, categories, areas, priority_rows):
    insights = []

    if summary["total"] == 0:
        return [
            "No complaints have been submitted yet.",
            "Register complaints to start generating analytics insights.",
        ]

    if categories:
        insights.append(f"{categories[0]['label']} is the highest reported complaint.")

    if areas:
        insights.append(f"{areas[0]['label']} has the highest complaint density.")

    insights.append(
        f"Overall complaint resolution rate is {summary['resolution_rate']}%.",
    )

    high_priority_pct = round((summary["high_priority"] / summary["total"]) * 100, 1)
    insights.append(
        f"{summary['high_priority']} complaints ({high_priority_pct}%) are marked as high priority.",
    )

    if summary["pending"] > 0:
        insights.append(f"{summary['pending']} complaints are still pending resolution.")
    else:
        insights.append("All submitted complaints have been resolved.")

    if priority_rows:
        top_priority = max(priority_rows, key=lambda item: item["count"])
        insights.append(
            f"Most complaints are classified as {top_priority['label']} priority by AI.",
        )

    return insights[:6]


@app.route("/api/analytics", methods=["GET"])
def analytics():
    conn = get_db()

    total = conn.execute("SELECT COUNT(*) AS count FROM complaints").fetchone()["count"]
    resolved = conn.execute(
        "SELECT COUNT(*) AS count FROM complaints WHERE status = 'Completed'"
    ).fetchone()["count"]
    pending = total - resolved
    high_priority = conn.execute(
        "SELECT COUNT(*) AS count FROM complaints WHERE ai_priority = 'High'"
    ).fetchone()["count"]

    resolution_rate = round((resolved / total) * 100, 1) if total else 0

    trend_labels = []
    trend_values = []
    for offset in range(6, -1, -1):
        day = datetime.now().date() - timedelta(days=offset)
        trend_labels.append(day.strftime("%a"))
        count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM complaints
            WHERE date(created_at) = date(?)
            """,
            (day.isoformat(),),
        ).fetchone()["count"]
        trend_values.append(count)

    category_rows = conn.execute(
        """
        SELECT complaint_type, COUNT(*) AS count
        FROM complaints
        GROUP BY complaint_type
        ORDER BY count DESC
        """
    ).fetchall()
    categories = [
        {"label": row["complaint_type"], "count": row["count"]} for row in category_rows
    ]

    area_rows = conn.execute(
        """
        SELECT area, COUNT(*) AS count
        FROM complaints
        GROUP BY area
        ORDER BY count DESC
        LIMIT 8
        """
    ).fetchall()
    areas = [{"label": row["area"], "count": row["count"]} for row in area_rows]

    monthly_rows = conn.execute(
        """
        SELECT strftime('%Y-%m', created_at) AS month_key,
               COUNT(*) AS total,
               SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS resolved
        FROM complaints
        GROUP BY month_key
        ORDER BY month_key DESC
        LIMIT 6
        """
    ).fetchall()
    monthly_rows = list(reversed(monthly_rows))
    monthly_resolution = {
        "labels": [
            datetime.strptime(row["month_key"], "%Y-%m").strftime("%b")
            for row in monthly_rows
        ],
        "values": [
            round((row["resolved"] / row["total"]) * 100, 1) if row["total"] else 0
            for row in monthly_rows
        ],
    }

    complaint_types = conn.execute(
        "SELECT complaint_type FROM complaints"
    ).fetchall()
    department_counts = defaultdict(int)
    for row in complaint_types:
        department = DEPARTMENT_MAP.get(row["complaint_type"], "General")
        department_counts[department] += 1

    departments = [
        {"label": label, "count": department_counts[label]}
        for label in sorted(department_counts, key=department_counts.get, reverse=True)
    ]

    priority_rows = conn.execute(
        """
        SELECT ai_priority, COUNT(*) AS count
        FROM complaints
        GROUP BY ai_priority
        ORDER BY count DESC
        """
    ).fetchall()
    priorities = [
        {"label": row["ai_priority"], "count": row["count"]} for row in priority_rows
    ]

    this_month = datetime.now().strftime("%Y-%m")
    last_month = (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    this_month_count = conn.execute(
        "SELECT COUNT(*) AS count FROM complaints WHERE strftime('%Y-%m', created_at) = ?",
        (this_month,),
    ).fetchone()["count"]
    last_month_count = conn.execute(
        "SELECT COUNT(*) AS count FROM complaints WHERE strftime('%Y-%m', created_at) = ?",
        (last_month,),
    ).fetchone()["count"]

    if last_month_count == 0:
        month_change = 100 if this_month_count > 0 else 0
    else:
        month_change = round(
            ((this_month_count - last_month_count) / last_month_count) * 100, 1
        )

    summary = {
        "total": total,
        "resolved": resolved,
        "pending": pending,
        "high_priority": high_priority,
        "resolution_rate": resolution_rate,
        "month_change": month_change,
    }

    insights = build_insights(summary, categories, areas, priorities)
    conn.close()

    return jsonify(
        {
            "summary": summary,
            "trend": {"labels": trend_labels, "values": trend_values},
            "categories": categories,
            "areas": areas,
            "monthly_resolution": monthly_resolution,
            "departments": departments,
            "priorities": priorities,
            "insights": insights,
            "metrics": {
                "resolution_rate": f"{resolution_rate}%",
                "pending_rate": f"{round((pending / total) * 100, 1) if total else 0}%",
                "high_priority_rate": f"{round((high_priority / total) * 100, 1) if total else 0}%",
            },
        }
    )


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    mobile = (data.get("mobile") or "").strip()
    password = (data.get("password") or "").strip()

    if not all([full_name, email, mobile, password]):
        return jsonify({"message": "All fields are required."}), 400

    if len(password) < 6:
        return jsonify({"message": "Password must be at least 6 characters."}), 400

    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"message": "Email is already registered."}), 409

    conn.execute(
        """
        INSERT INTO users (full_name, email, mobile, password_hash, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            full_name,
            email,
            mobile,
            generate_password_hash(password),
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Registration successful."}), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()

    if not email or not password:
        return jsonify({"message": "Email and password are required."}), 400

    conn = get_db()
    user = conn.execute(
        "SELECT id, full_name, email, password_hash FROM users WHERE email = ?",
        (email,),
    ).fetchone()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"message": "Invalid email or password."}), 401

    return jsonify(
        {
            "message": "Login successful.",
            "user": {
                "id": user["id"],
                "full_name": user["full_name"],
                "email": user["email"],
            },
        }
    )


@app.route("/api/complaints", methods=["POST"])
def create_complaint():
    user_id = request.form.get("user_id")
    complaint_type = (request.form.get("complaint_type") or "").strip()
    area = (request.form.get("area") or "").strip()
    severity = (request.form.get("severity") or "").strip()
    people_affected = request.form.get("people_affected")
    description = (request.form.get("description") or "").strip()

    if not all([user_id, complaint_type, area, severity, people_affected, description]):
        return jsonify({"message": "All complaint fields are required."}), 400

    try:
        user_id = int(user_id)
        people_affected = int(people_affected)
    except ValueError:
        return jsonify({"message": "Invalid user or people affected value."}), 400

    if people_affected < 1:
        return jsonify({"message": "People affected must be at least 1."}), 400

    conn = get_db()
    user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({"message": "User not found. Please login again."}), 404

    image_path = None
    image_file = request.files.get("image")
    if image_file and image_file.filename:
        filename = secure_filename(image_file.filename)
        if filename:
            unique_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            image_path = os.path.join(UPLOAD_DIR, unique_name)
            image_file.save(image_path)

    complaint_code = generate_complaint_code(conn)
    ai_priority = predict_priority(severity, people_affected)
    created_at = datetime.now().isoformat()

    conn.execute(
        """
        INSERT INTO complaints (
            complaint_code, user_id, complaint_type, area, severity,
            people_affected, description, image_path, status, ai_priority, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            complaint_code,
            user_id,
            complaint_type,
            area,
            severity,
            people_affected,
            description,
            image_path,
            "Submitted",
            ai_priority,
            created_at,
        ),
    )
    conn.commit()
    conn.close()

    return jsonify(
        {
            "message": "Complaint submitted successfully.",
            "complaint": {
                "complaint_code": complaint_code,
                "complaint_type": complaint_type,
                "area": area,
                "severity": severity,
                "people_affected": people_affected,
                "description": description,
                "status": "Submitted",
                "ai_priority": ai_priority,
                "created_at": format_date(created_at),
            },
        }
    ), 201


@app.route("/api/users/<int:user_id>", methods=["GET"])
def get_user_profile(user_id):
    conn = get_db()
    user = conn.execute(
        """
        SELECT id, full_name, email, mobile, created_at
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()
    conn.close()

    if not user:
        return jsonify({"message": "User not found."}), 404

    return jsonify(
        {
            "user": {
                "id": user["id"],
                "full_name": user["full_name"],
                "email": user["email"],
                "mobile": user["mobile"],
                "created_at": format_date(user["created_at"]),
            }
        }
    )


@app.route("/api/users/<int:user_id>/complaints", methods=["GET"])
def get_user_complaints(user_id):
    conn = get_db()
    user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({"message": "User not found."}), 404

    rows = conn.execute(
        """
        SELECT complaint_code, complaint_type, area, status, ai_priority, created_at
        FROM complaints
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    ).fetchall()
    conn.close()

    complaints = [
        {
            "complaint_code": row["complaint_code"],
            "complaint_type": row["complaint_type"],
            "area": row["area"],
            "status": row["status"],
            "ai_priority": row["ai_priority"],
            "created_at": format_date(row["created_at"]),
        }
        for row in rows
    ]

    return jsonify({"complaints": complaints}    )


@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or {}
    admin_id = (data.get("admin_id") or "").strip().upper()
    password = (data.get("password") or "").strip()

    if not admin_id or not password:
        return jsonify({"message": "Admin ID and password are required."}), 400

    conn = get_db()
    admin = conn.execute(
        """
        SELECT id, admin_id, full_name, email, mobile, role, department, password_hash
        FROM admins WHERE admin_id = ?
        """,
        (admin_id,),
    ).fetchone()
    conn.close()

    if not admin or not check_password_hash(admin["password_hash"], password):
        return jsonify({"message": "Invalid admin ID or password."}), 401

    return jsonify(
        {
            "message": "Admin login successful.",
            "admin": {
                "id": admin["id"],
                "admin_id": admin["admin_id"],
                "full_name": admin["full_name"],
                "email": admin["email"],
                "mobile": admin["mobile"],
                "role": admin["role"],
                "department": admin["department"],
            },
        }
    )


@app.route("/api/admin/dashboard", methods=["GET"])
def admin_dashboard():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) AS count FROM complaints").fetchone()["count"]
    resolved = conn.execute(
        "SELECT COUNT(*) AS count FROM complaints WHERE status = 'Completed'"
    ).fetchone()["count"]
    pending = total - resolved
    high_priority = conn.execute(
        "SELECT COUNT(*) AS count FROM complaints WHERE ai_priority = 'High'"
    ).fetchone()["count"]
    total_users = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]

    today = datetime.now().date().isoformat()
    today_count = conn.execute(
        "SELECT COUNT(*) AS count FROM complaints WHERE date(created_at) = date(?)",
        (today,),
    ).fetchone()["count"]

    recent = conn.execute(
        """
        SELECT c.complaint_code, c.complaint_type, c.area, c.status, c.ai_priority,
               u.full_name
        FROM complaints c
        JOIN users u ON u.id = c.user_id
        ORDER BY c.created_at DESC
        LIMIT 5
        """
    ).fetchall()

    alerts = conn.execute(
        """
        SELECT c.complaint_code, c.complaint_type, c.area, c.ai_priority
        FROM complaints c
        WHERE c.ai_priority = 'High' AND c.status != 'Completed'
        ORDER BY c.created_at DESC
        LIMIT 5
        """
    ).fetchall()
    conn.close()

    return jsonify(
        {
            "summary": {
                "total": total,
                "resolved": resolved,
                "pending": pending,
                "high_priority": high_priority,
                "total_users": total_users,
                "today_count": today_count,
            },
            "recent_complaints": [
                {
                    "complaint_code": row["complaint_code"],
                    "complaint_type": row["complaint_type"],
                    "area": row["area"],
                    "status": row["status"],
                    "ai_priority": row["ai_priority"],
                    "citizen_name": row["full_name"],
                }
                for row in recent
            ],
            "high_priority_alerts": [
                {
                    "complaint_code": row["complaint_code"],
                    "complaint_type": row["complaint_type"],
                    "area": row["area"],
                    "ai_priority": row["ai_priority"],
                }
                for row in alerts
            ],
        }
    )


@app.route("/api/admin/complaints", methods=["GET"])
def admin_complaints():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT c.complaint_code, c.complaint_type, c.area, c.status, c.ai_priority,
               c.created_at, u.full_name AS citizen_name
        FROM complaints c
        JOIN users u ON u.id = c.user_id
        ORDER BY c.created_at DESC
        """
    ).fetchall()
    conn.close()

    complaints = [
        {
            "complaint_code": row["complaint_code"],
            "complaint_type": row["complaint_type"],
            "area": row["area"],
            "status": row["status"],
            "ai_priority": row["ai_priority"],
            "created_at": format_date(row["created_at"]),
            "citizen_name": row["citizen_name"],
        }
        for row in rows
    ]

    return jsonify({"complaints": complaints})


VALID_STATUSES = [
    "Submitted",
    "Under Review",
    "Assigned",
    "In Progress",
    "Completed",
]


@app.route("/api/admin/complaints/<complaint_code>", methods=["PUT"])
def update_admin_complaint(complaint_code):
    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip()

    if status not in VALID_STATUSES:
        return jsonify({"message": "Invalid complaint status."}), 400

    code = complaint_code.strip().upper()
    conn = get_db()
    complaint = conn.execute(
        "SELECT complaint_code FROM complaints WHERE complaint_code = ?",
        (code,),
    ).fetchone()

    if not complaint:
        conn.close()
        return jsonify({"message": "Complaint not found."}), 404

    conn.execute(
        "UPDATE complaints SET status = ? WHERE complaint_code = ?",
        (status, code),
    )
    conn.commit()
    conn.close()

    return jsonify({"message": "Complaint updated successfully.", "status": status})


@app.route("/api/admin/users", methods=["GET"])
def admin_users():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT u.id, u.full_name, u.email, u.mobile, u.created_at,
               COUNT(c.id) AS complaint_count
        FROM users u
        LEFT JOIN complaints c ON c.user_id = u.id
        GROUP BY u.id
        ORDER BY u.created_at DESC
        """
    ).fetchall()
    conn.close()

    users = [
        {
            "id": row["id"],
            "full_name": row["full_name"],
            "email": row["email"],
            "mobile": row["mobile"],
            "complaint_count": row["complaint_count"],
            "created_at": format_date(row["created_at"]),
            "status": "Active" if row["complaint_count"] > 0 else "Registered",
        }
        for row in rows
    ]

    return jsonify(
        {
            "summary": {
                "total_users": len(users),
                "active_users": sum(1 for user in users if user["complaint_count"] > 0),
                "total_complaints": sum(user["complaint_count"] for user in users),
            },
            "users": users,
        }
    )


@app.route("/api/complaints/<complaint_code>", methods=["GET"])
def get_complaint(complaint_code):
    code = complaint_code.strip().upper()
    conn = get_db()
    complaint = conn.execute(
        """
        SELECT complaint_code, complaint_type, area, severity, people_affected,
               description, status, ai_priority, created_at
        FROM complaints
        WHERE complaint_code = ?
        """,
        (code,),
    ).fetchone()
    conn.close()

    if not complaint:
        return jsonify({"message": "Complaint not found."}), 404

    return jsonify(
        {
            "complaint": {
                "complaint_code": complaint["complaint_code"],
                "complaint_type": complaint["complaint_type"],
                "area": complaint["area"],
                "severity": complaint["severity"],
                "people_affected": complaint["people_affected"],
                "description": complaint["description"],
                "status": complaint["status"],
                "ai_priority": complaint["ai_priority"],
                "created_at": format_date(complaint["created_at"]),
            }
        }
    )


@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:filename>")
def serve_frontend(filename):
    if filename.startswith("api/"):
        return jsonify({"message": "Not found."}), 404
    return send_from_directory(FRONTEND_DIR, filename)


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
