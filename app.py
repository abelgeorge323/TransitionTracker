"""
Transition Takeover Deployment Tracker
Purpose: View bench capacity, filter by vertical + experience, deploy the right person fast.
"""
import os
import csv
import io
import re
from flask import Flask, render_template, request, jsonify, Response, send_from_directory
from collections import defaultdict

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# In-memory store (use Heroku Postgres or Redis for production persistence)
NOMINEES = []


def _load_csv_from_data():
    """Load CSV from Data folder (works for both local and Heroku when CSV is in repo)."""
    data_dir = os.path.join(os.path.dirname(__file__), "Data")
    # Prefer newest sheet (2), then (1), then original
    for name in ("Transition Team Member Nomination Form(Sheet1) (2).csv", "Transition Team Member Nomination Form(Sheet1) (1).csv", "Transition Team Member Nomination Form(Sheet1).csv"):
        path = os.path.join(data_dir, name)
        if os.path.isfile(path):
            with open(path, encoding="utf-8-sig") as f:
                global NOMINEES
                NOMINEES = parse_csv(f.read())
            return


def normalize_experience(raw: str) -> str:
    """Extract Novice, Intermediate, or Expert from form response."""
    if not raw:
        return "Unknown"
    raw_lower = raw.lower()
    if "expert" in raw_lower:
        return "Expert"
    if "intermediate" in raw_lower:
        return "Intermediate"
    if "novice" in raw_lower:
        return "Novice"
    return "Unknown"


def parse_csv(content: str) -> list[dict]:
    """Parse Microsoft Forms CSV export into normalized nominee records."""
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    for row in reader:
        nominee = row.get("Who are you Nominating", "").strip()
        if not nominee:
            continue
        rows.append({
            "id": row.get("Id", ""),
            "nominee": nominee,
            "vertical": (row.get("Vertical", "") or "").strip() or "Unspecified",
            "current_account": (row.get("Current Account / Site Assignment", "") or "").strip(),
            "title": (row.get("Current Title", "") or "").strip(),
            "years_in_role": (row.get("Years in Current Role", "") or "").strip(),
            "experience": normalize_experience(row.get("Experience Level", "")),
            "summary": (row.get("Summary of Prior Transition Experience", "") or "").strip(),
            "nominator_name": (row.get("Name", "") or "").strip(),
            "nominator_email": (row.get("Email", "") or "").strip(),
        })
    return rows


def get_stats(nominees: list) -> dict:
    """Compute executive snapshot stats."""
    experts = sum(1 for n in nominees if n["experience"] == "Expert")
    intermediate = sum(1 for n in nominees if n["experience"] == "Intermediate")
    novice = sum(1 for n in nominees if n["experience"] == "Novice")
    unknown = sum(1 for n in nominees if n["experience"] == "Unknown")
    verticals = len(set(n["vertical"] for n in nominees if n["vertical"]))
    return {
        "total": len(nominees),
        "expert": experts,
        "intermediate": intermediate,
        "novice": novice,
        "unknown": unknown,
        "verticals": verticals,
    }


def get_grid(nominees: list) -> dict:
    """Build Vertical × Experience matrix."""
    matrix = defaultdict(lambda: {"Novice": 0, "Intermediate": 0, "Expert": 0, "Unknown": 0})
    for n in nominees:
        v = n["vertical"] or "Unspecified"
        e = n["experience"]
        matrix[v][e] = matrix[v][e] + 1
    # Sort verticals, add totals
    result = []
    for v in sorted(matrix.keys()):
        row = matrix[v]
        total = sum(row.values())
        result.append({
            "vertical": v,
            "novice": row["Novice"],
            "intermediate": row["Intermediate"],
            "expert": row["Expert"],
            "unknown": row["Unknown"],
            "total": total,
        })
    return result


def filter_nominees(nominees: list, vertical: str, experience: str, title: str, search: str) -> list:
    """Apply filters to nominee list."""
    out = nominees
    if vertical:
        out = [n for n in out if n["vertical"] == vertical]
    if experience:
        out = [n for n in out if n["experience"] == experience]
    if title:
        out = [n for n in out if n["title"] == title]
    if search:
        q = search.lower()
        out = [n for n in out if q in (n["nominee"] or "").lower() or q in (n["nominator_name"] or "").lower()]
    return out


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    return send_from_directory(assets_dir, filename)


def _get_logo_url():
    """Return logo URL if it exists. Returns None (no logo displayed)."""
    return None


@app.route("/")
def index():
    logo_url = _get_logo_url()
    return render_template(
        "index.html",
        has_data=len(NOMINEES) > 0,
        logo_url=logo_url,
    )


@app.route("/api/load-sample", methods=["POST"])
def load_sample():
    """Load sample CSV from Data folder (for dev/demo)."""
    global NOMINEES
    try:
        _load_csv_from_data()
        return jsonify({"count": len(NOMINEES), "message": f"Loaded {len(NOMINEES)} nominees from sample."})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/upload", methods=["POST"])
def upload():
    global NOMINEES
    file = request.files.get("file")
    if not file or not file.filename.lower().endswith(".csv"):
        return jsonify({"error": "Please upload a CSV file."}), 400
    try:
        content = file.read().decode("utf-8-sig")
        NOMINEES = parse_csv(content)
        return jsonify({"count": len(NOMINEES), "message": f"Loaded {len(NOMINEES)} nominees."})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/stats")
def stats():
    s = get_stats(NOMINEES)
    return jsonify(s)


@app.route("/api/grid")
def grid():
    g = get_grid(NOMINEES)
    return jsonify(g)


@app.route("/api/nominees")
def nominees():
    vertical = request.args.get("vertical", "")
    experience = request.args.get("experience", "")
    title = request.args.get("title", "")
    search = request.args.get("search", "")
    filtered = filter_nominees(NOMINEES, vertical, experience, title, search)
    return jsonify(filtered)


@app.route("/api/export")
def export():
    vertical = request.args.get("vertical", "")
    experience = request.args.get("experience", "")
    title = request.args.get("title", "")
    search = request.args.get("search", "")
    filtered = filter_nominees(NOMINEES, vertical, experience, title, search)
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["Nominee", "Vertical", "Experience", "Title", "Current Account", "Years in Role", "Summary"])
    for n in filtered:
        w.writerow([
            n["nominee"],
            n["vertical"],
            n["experience"],
            n["title"],
            n["current_account"],
            n["years_in_role"],
            n["summary"],
        ])
    csv_bytes = output.getvalue().encode("utf-8-sig")  # BOM for Excel
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=\"transition_nominees.csv\"",
            "Content-Length": str(len(csv_bytes)),
        },
    )


# Load sample data for local dev (file in Data/ folder)
_load_csv_from_data()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
