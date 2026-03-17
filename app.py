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

# In-memory stores
NOMINEES = []
SUCCESSION_RECORDS = []


def _load_csv_from_data():
    """Load CSV from Data folder (works for both local and Heroku when CSV is in repo)."""
    global NOMINEES
    names = ("Transition Team Member Nomination Form(Sheet1) (4).csv", "Transition Team Member Nomination Form(Sheet1) (3).csv", "Transition Team Member Nomination Form(Sheet1) (2).csv", "Transition Team Member Nomination Form(Sheet1) (1).csv", "Transition Team Member Nomination Form(Sheet1).csv")
    # Try paths: next to app.py, then cwd/Data
    for data_dir in (os.path.join(os.path.dirname(os.path.abspath(__file__)), "Data"), os.path.join(os.getcwd(), "Data")):
        if not os.path.isdir(data_dir):
            continue
        for name in names:
            path = os.path.join(data_dir, name)
            if os.path.isfile(path):
                try:
                    with open(path, encoding="utf-8-sig") as f:
                        NOMINEES = parse_csv(f.read())
                    if NOMINEES:
                        return
                except Exception as e:
                    print(f"Error loading {path}: {e}")


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


def _name_to_email_prefix(name: str) -> str:
    """Convert name to expected email prefix (e.g. James Hancock -> jhancock)."""
    name = (name or "").strip()
    if not name:
        return ""
    parts = name.split()
    if not parts:
        return ""
    first = parts[0].lower()
    last = parts[-1].lower().split("-")[0] if parts else ""  # take first part of hyphenated last
    return (first[0] if first else "") + last


def _is_self_nominated(nominee: str, email: str) -> bool:
    """Self-nominated = metadata email matches the nominee's name (email prefix identifies the person)."""
    if not nominee or not email or "@" not in email:
        return False
    nominee_clean = nominee.strip()
    if " - " in nominee_clean:
        nominee_clean = nominee_clean.split(" - ", 1)[-1].strip()
    if "myself" in nominee_clean.lower():
        nominee_clean = nominee_clean.replace("Myself", "").replace("myself", "").strip().lstrip("- ")
    expected = _name_to_email_prefix(nominee_clean)
    actual = email.split("@")[0].lower()
    return expected == actual or actual.startswith(expected)


def parse_csv(content: str) -> list[dict]:
    """Parse Microsoft Forms CSV export into normalized nominee records."""
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    for row in reader:
        nominee = row.get("Who are you Nominating", "").strip()
        if not nominee:
            continue
        nominator = (row.get("Name", "") or "").strip()
        email = (row.get("Email", "") or "").strip()
        rows.append({
            "id": row.get("Id", ""),
            "nominee": nominee,
            "vertical": (row.get("Vertical", "") or "").strip() or "Unspecified",
            "current_account": (row.get("Current Account / Site Assignment", "") or "").strip(),
            "title": (row.get("Current Title", "") or "").strip(),
            "years_in_role": (row.get("Years in Current Role", "") or "").strip(),
            "experience": normalize_experience(row.get("Experience Level", "")),
            "summary": (row.get("Summary of Prior Transition Experience", "") or "").strip(),
            "nominator_name": nominator,
            "nominator_email": email,
            "is_self_nominated": _is_self_nominated(nominee, email),
        })
    return rows


def get_stats(nominees: list) -> dict:
    """Compute executive snapshot stats."""
    experts = sum(1 for n in nominees if n["experience"] == "Expert")
    intermediate = sum(1 for n in nominees if n["experience"] == "Intermediate")
    novice = sum(1 for n in nominees if n["experience"] == "Novice")
    unknown = sum(1 for n in nominees if n["experience"] == "Unknown")
    verticals_set = set(n["vertical"] for n in nominees if n.get("vertical"))
    verticals = len(verticals_set)
    self_nominated = [n["nominee"] for n in nominees if n.get("is_self_nominated")]
    titles = list(set(n["title"] for n in nominees if n.get("title")))
    return {
        "total": len(nominees),
        "expert": experts,
        "intermediate": intermediate,
        "novice": novice,
        "unknown": unknown,
        "verticals": verticals,
        "self_nominated": self_nominated,
        "self_nominated_count": len(self_nominated),
        "titles": sorted(titles),
        "verticals_list": sorted(verticals_set),
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


_EMPTY_VALS = {"", "none", "n/a", "na", "tbd", "currently recruiting"}


def _is_empty_successor(val: str) -> bool:
    return (val or "").strip().lower() in _EMPTY_VALS


def parse_succession_csv(content: str) -> list[dict]:
    """Parse Succession Planning Forms CSV export."""
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    for row in reader:
        leader = (row.get("Created By", "") or "").strip()
        if not leader:
            continue
        title = (row.get("Title", "") or "").strip()
        vertical = (row.get("Vertical", "") or "").strip() or "Unspecified"
        successor = (row.get("Who is your current %232?", "") or row.get("Who is your current #2?", "") or "").strip()
        successor_role = (row.get("What is their current role/title?", "") or "").strip()
        successor_tenure = (row.get("How long have they been with SBM?", "") or "").strip()
        successor_readiness = (row.get("Any notes about your %232's readiness for leadership?", "") or row.get("Any notes about your #2's readiness for leadership?", "") or "").strip()
        mentoring_raw = (row.get("Are you currently mentoring or training an MIT/ New Leader?", "") or "").strip()
        mentoring_mit = mentoring_raw.lower().startswith("yes")
        mit_name = (row.get("If yes, who is the MIT you are currently training?", "") or "").strip()
        mit_reason_not = (row.get("If you are not currently mentoring an MIT, are there any factors preventing this? Please briefly explain!", "") or "").strip()
        mit_dev_focus = (row.get("What areas are you currently helping them develop?", "") or "").strip()
        has_succ_raw = (row.get("Does your %232 currently have soemone they are developing as their successor?", "") or row.get("Does your #2 currently have someone they are developing as their successor?", "") or "").strip()
        has_successor_pipeline = has_succ_raw.lower().startswith("yes")
        succ_succ_name = (row.get("If yes, who is your %232's %232!", "") or row.get("If yes, who is your #2's #2!", "") or "").strip()
        succ_succ_notes = (row.get("Any notes on this individuals readiness or development?", "") or "").strip()
        succ_succ_reason_not = (row.get("If your %232 is not currently developing a successor or you are unsure, what is the main reason?", "") or row.get("If your #2 is not currently developing a successor or you are unsure, what is the main reason?", "") or "").strip()

        # Risk flags
        risks = []
        if _is_empty_successor(successor):
            risks.append("No #2")
        if not mentoring_mit:
            risks.append("No MIT")
        if not has_successor_pipeline:
            risks.append("No pipeline")

        # Skip rows that are test/blank entries (no title AND no successor AND no MIT)
        if not title and _is_empty_successor(successor) and not mentoring_mit:
            continue

        rows.append({
            "leader_name": leader,
            "leader_title": title,
            "vertical": vertical,
            "successor_name": successor,
            "successor_role": successor_role,
            "successor_tenure": successor_tenure,
            "successor_readiness_notes": successor_readiness,
            "mentoring_mit": mentoring_mit,
            "mit_name": mit_name,
            "mit_reason_not": mit_reason_not,
            "mit_development_focus": mit_dev_focus,
            "successor_has_successor": has_successor_pipeline,
            "successor_successor_name": succ_succ_name,
            "successor_successor_notes": succ_succ_notes,
            "successor_successor_reason_not": succ_succ_reason_not,
            "risk_flags": risks,
            "risk_flag": risks[0] if risks else "",
        })
    return rows


def _load_succession_csv():
    """Load Succession Planning CSV from Succession (or Succsession) folder."""
    global SUCCESSION_RECORDS
    base = os.path.dirname(os.path.abspath(__file__))
    folder_names = ("Succession", "Succsession")
    for root in (base, os.getcwd()):
        for folder in folder_names:
            d = os.path.join(root, folder)
            if not os.path.isdir(d):
                continue
            csvs = [f for f in os.listdir(d) if f.lower().endswith(".csv")]
            for name in ("Succession Planning.csv",):
                if name in csvs:
                    csvs = [name]
                    break
            for name in csvs:
                path = os.path.join(d, name)
                try:
                    with open(path, encoding="utf-8-sig") as f:
                        SUCCESSION_RECORDS = parse_succession_csv(f.read())
                    if SUCCESSION_RECORDS:
                        return
                except Exception as e:
                    print(f"Error loading succession CSV {path}: {e}")


def get_succession_stats(records: list) -> dict:
    total = len(records)
    with_number2 = sum(1 for r in records if not _is_empty_successor(r["successor_name"]))
    with_mit = sum(1 for r in records if r["mentoring_mit"])
    with_pipeline = sum(1 for r in records if r["successor_has_successor"])
    no_number2 = total - with_number2
    no_mit = total - with_mit
    no_pipeline = total - with_pipeline
    verticals_set = set(r["vertical"] for r in records if r.get("vertical"))
    return {
        "total_leaders": total,
        "with_number2": with_number2,
        "with_mit": with_mit,
        "with_pipeline": with_pipeline,
        "no_number2": no_number2,
        "no_mit": no_mit,
        "no_pipeline": no_pipeline,
        "verticals": len(verticals_set),
        "verticals_list": sorted(verticals_set),
    }


def filter_nominees(nominees: list, vertical: str, experience: str, title: str, search: str, self_only: bool = False) -> list:
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
    if self_only:
        out = [n for n in out if n.get("is_self_nominated")]
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


@app.route("/api/debug")
def debug():
    """Return debug info about CSV loading (for troubleshooting 0 counts)."""
    base = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base, "Data")
    exists = os.path.isdir(data_dir)
    files = []
    if exists:
        try:
            files = [f for f in os.listdir(data_dir) if f.lower().endswith(".csv")]
        except OSError:
            pass
    return jsonify({
        "nominee_count": len(NOMINEES),
        "data_dir": data_dir,
        "data_dir_exists": exists,
        "csv_files": files,
        "cwd": os.getcwd(),
    })


@app.route("/api/reload")
def reload_data():
    """Force reload CSV from Data folder (useful when initial load fails)."""
    global NOMINEES
    _load_csv_from_data()
    return jsonify({"count": len(NOMINEES), "message": f"Loaded {len(NOMINEES)} nominees."})


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
    self_only = request.args.get("self_nominated") == "1"
    filtered = filter_nominees(NOMINEES, vertical, experience, title, search, self_only)
    return jsonify(filtered)


@app.route("/api/succession/stats")
def succession_stats():
    vertical = request.args.get("vertical", "")
    records = SUCCESSION_RECORDS
    if vertical:
        records = [r for r in records if r["vertical"] == vertical]
    return jsonify(get_succession_stats(records))


@app.route("/api/succession/records")
def succession_records():
    vertical = request.args.get("vertical", "")
    search = request.args.get("search", "")
    risk = request.args.get("risk", "")
    records = SUCCESSION_RECORDS
    if vertical:
        records = [r for r in records if r["vertical"] == vertical]
    if search:
        q = search.lower()
        records = [r for r in records if q in r["leader_name"].lower() or q in r.get("successor_name", "").lower()]
    if risk:
        records = [r for r in records if risk in r.get("risk_flags", [])]
    return jsonify(records)


@app.route("/api/succession/export")
def succession_export():
    vertical = request.args.get("vertical", "")
    records = SUCCESSION_RECORDS
    if vertical:
        records = [r for r in records if r["vertical"] == vertical]
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["Leader", "Title", "Vertical", "#2", "#2 Role", "#2 Tenure", "#2 Readiness Notes", "MIT (Y/N)", "MIT Name", "MIT Reason Not", "#2's #2 (Y/N)", "#2's #2 Name", "#2's #2 Notes", "Risk Flag"])
    for r in records:
        w.writerow([
            r["leader_name"], r["leader_title"], r["vertical"],
            r["successor_name"], r["successor_role"], r["successor_tenure"], r["successor_readiness_notes"],
            "Yes" if r["mentoring_mit"] else "No", r["mit_name"], r["mit_reason_not"],
            "Yes" if r["successor_has_successor"] else "No", r["successor_successor_name"], r["successor_successor_notes"],
            r["risk_flag"],
        ])
    csv_bytes = output.getvalue().encode("utf-8-sig")
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=\"succession_planning.csv\"",
            "Content-Length": str(len(csv_bytes)),
        },
    )


@app.route("/api/export")
def export():
    vertical = request.args.get("vertical", "")
    experience = request.args.get("experience", "")
    title = request.args.get("title", "")
    search = request.args.get("search", "")
    self_only = request.args.get("self_nominated") == "1"
    filtered = filter_nominees(NOMINEES, vertical, experience, title, search, self_only)
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["Nominee", "Vertical", "Experience", "Title", "Current Account", "Years in Role", "Self-Nominated", "Summary"])
    for n in filtered:
        w.writerow([
            n["nominee"],
            n["vertical"],
            n["experience"],
            n["title"],
            n["current_account"],
            n["years_in_role"],
            "Yes" if n.get("is_self_nominated") else "No",
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


# Load data at startup
_load_csv_from_data()
_load_succession_csv()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
