import os
import io
import csv
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import matplotlib
matplotlib.use("Agg")  # headless backend for servers
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = "replace-this-with-a-random-secret"  # needed for flash messages

DATA_FILE = "records.csv"


# ----- Helpers -----

def ensure_data_file():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["year", "semester", "m1", "m2", "m3", "m4", "m5", "sgpa", "timestamp"])


def load_records():
    """Return dict keyed by (year, sem) -> record dict"""
    ensure_data_file()
    records = {}
    with open(DATA_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            y = int(row["year"])
            s = int(row["semester"])
            record = {
                "year": y,
                "semester": s,
                "marks": [float(row["m1"]), float(row["m2"]), float(row["m3"]), float(row["m4"]), float(row["m5"])],
                "sgpa": float(row["sgpa"]),
                "timestamp": row["timestamp"],
            }
            records[(y, s)] = record
    return records


def save_record(year, semester, marks, sgpa):
    ensure_data_file()
    with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            year, semester,
            marks[0], marks[1], marks[2], marks[3], marks[4],
            f"{sgpa:.2f}",
            datetime.now().isoformat(timespec="seconds")
        ])


def marks_to_grade_point(m):
    """
    Convert marks (0-100) to grade points on a 10-point scale.
    Adjust thresholds to your university scheme if needed.
    """
    m = float(m)
    if m >= 90: return 10
    if m >= 80: return 9
    if m >= 70: return 8
    if m >= 60: return 7
    if m >= 50: return 6
    if m >= 40: return 5
    return 0


def compute_sgpa(marks):
    """Equal weight for 5 subjects -> mean of grade points."""
    gps = [marks_to_grade_point(m) for m in marks]
    return sum(gps) / len(gps)


def compute_year_cgpa(records, year):
    """Average of SGPA of Sem-1 and Sem-2 for that year, if both exist."""
    s1 = records.get((year, 1))
    s2 = records.get((year, 2))
    if s1 and s2:
        return (s1["sgpa"] + s2["sgpa"]) / 2
    return None


def compute_overall_cgpa(records):
    """Overall CGPA across all available semesters (equal credits)."""
    if not records:
        return None
    s_list = [r["sgpa"] for r in records.values()]
    if not s_list:
        return None
    return sum(s_list) / len(s_list)


# ----- Routes -----

@app.route("/", methods=["GET"])
def index():
    records = load_records()

    # build per-year CGPA and overall
    year_cgpas = {y: compute_year_cgpa(records, y) for y in range(1, 5)}
    overall_cgpa = compute_overall_cgpa(records)

    # Optional: user can query a particular year's CGPA via ?year_query=1..4
    year_query = request.args.get("year_query", type=int)
    selected_year_cgpa = None
    if year_query in [1, 2, 3, 4]:
        selected_year_cgpa = compute_year_cgpa(records, year_query)

    # order records for display
    table_rows = []
    for y in range(1, 5):
        for s in [1, 2]:
            rec = records.get((y, s))
            table_rows.append({
                "year": y,
                "semester": s,
                "marks": rec["marks"] if rec else None,
                "sgpa": f'{rec["sgpa"]:.2f}' if rec else None,
                "timestamp": rec["timestamp"] if rec else None,
            })

    return render_template(
        "index.html",
        table_rows=table_rows,
        year_cgpas=year_cgpas,
        overall_cgpa=overall_cgpa,
        selected_year=year_query,
        selected_year_cgpa=selected_year_cgpa
    )


@app.route("/submit", methods=["POST"])
def submit():
    try:
        year = int(request.form.get("year", ""))
        semester = int(request.form.get("semester", ""))
        marks = [
            float(request.form.get("m1", "")),
            float(request.form.get("m2", "")),
            float(request.form.get("m3", "")),
            float(request.form.get("m4", "")),
            float(request.form.get("m5", ""))
        ]
    except Exception:
        flash("Please enter valid numbers for Year, Semester, and all 5 marks.", "danger")
        return redirect(url_for("index"))

    # validation
    if year not in [1, 2, 3, 4] or semester not in [1, 2]:
        flash("Year must be 1–4 and Semester must be 1 or 2.", "danger")
        return redirect(url_for("index"))

    for i, m in enumerate(marks, start=1):
        if m < 0 or m > 100:
            flash(f"Subject {i} marks must be between 0 and 100.", "danger")
            return redirect(url_for("index"))

    sgpa = compute_sgpa(marks)
    save_record(year, semester, marks, sgpa)
    flash(f"Saved: Year {year} Sem {semester} — SGPA {sgpa:.2f}", "success")
    return redirect(url_for("index"))


@app.route("/graph.png")
def graph_png():
    """Line chart of SGPA trend across semesters (1-1 -> 4-2)."""
    records = load_records()

    # Prepare x labels and y values in order
    labels = []
    values = []
    for y in range(1, 5):
        for s in [1, 2]:
            labels.append(f"{y}-{s}")
            rec = records.get((y, s))
            values.append(rec["sgpa"] if rec else None)

    # If nothing recorded yet, return a placeholder blank plot
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=120)

    # Plot available points (skip None)
    xs = []
    ys = []
    for idx, v in enumerate(values):
        if v is not None:
            xs.append(idx)
            ys.append(v)

    if ys:
        ax.plot(xs, ys, marker="o", linewidth=2)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=0)
        ax.set_ylim(0, 10)
        ax.set_ylabel("SGPA")
        ax.set_xlabel("Semester (Year-Sem)")
        ax.set_title("SGPA Growth / Downfall Trend")
        for x, y in zip(xs, ys):
            ax.text(x, y + 0.1, f"{y:.1f}", ha="center", va="bottom", fontsize=9)
        ax.grid(True, linestyle="--", alpha=0.4)
    else:
        ax.set_title("No data yet — submit marks to see the trend")
        ax.axis("off")

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# ---- NEW: Reset Graph route (only addition) ----
@app.route("/reset-graph", methods=["POST"])
def reset_graph():
    """Clear all saved semesters so the graph resets to blank."""
    with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["year", "semester", "m1", "m2", "m3", "m4", "m5", "sgpa", "timestamp"])
    flash("Graph data reset — all saved semesters cleared.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    # For local debug
    app.run(debug=True)



