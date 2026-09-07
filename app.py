# =============================================
# FLASK BACKEND - AI RECRUITMENT SYSTEM
# =============================================

from flask import Flask, send_file, request, jsonify
import database as db
import copy
import os

app = Flask(__name__)

# =============================================
# AI SCORING ENGINE
# =============================================
def calculate_ai_score(candidate, job):
    score = 0

    # 1. Skill Match → 40 points
    matched = [s for s in candidate["skills"] if s in job["required_skills"]]
    if job["required_skills"]:
        score += (len(matched) / len(job["required_skills"])) * 40

    # 2. Experience → 25 points
    if candidate["experience"] >= job["experience_required"]:
        score += 25
    else:
        ratio  = candidate["experience"] / max(job["experience_required"], 1)
        score += ratio * 25

    # 3. CGPA → 20 points
    cgpa = candidate.get("cgpa", 0)
    if   cgpa >= 9.0: score += 20
    elif cgpa >= 8.0: score += 16
    elif cgpa >= 7.0: score += 12
    else:             score += 8

    # 4. Certifications → 15 points
    score += min(len(candidate.get("certifications", [])) * 5, 15)

    return round(score)


def get_skill_name(skill_id):
    s = next((x for x in db.skills if x["skill_id"] == skill_id), None)
    return s["skill_name"] if s else ""


def enrich_candidate(candidate, job):
    c = copy.deepcopy(candidate)
    c["ai_score"]       = calculate_ai_score(c, job)
    c["matched_skills"] = [s for s in c["skills"] if s in job["required_skills"]]
    c["missing_skills"] = [s for s in job["required_skills"] if s not in c["skills"]]
    c["matched_names"]  = [get_skill_name(s) for s in c["matched_skills"]]
    c["missing_names"]  = [get_skill_name(s) for s in c["missing_skills"]]
    return c


# =============================================
# ROUTES
# =============================================

@app.route("/")
def index():
    # Send index.html directly from same folder as app.py
    base = os.path.dirname(os.path.abspath(__file__))
    return send_file(os.path.join(base, "index.html"))


# ── Dashboard ──────────────────────────────────────
@app.route("/api/dashboard")
def dashboard():
    open_jobs   = len([j for j in db.jobs if j["status"] == "Open"])
    total_cands = len(db.candidates)
    total_ints  = len(db.interviews)
    hired       = len([h for h in db.hiring if h["decision"] == "Selected"])

    scored_apps = []
    for app_rec in db.applications:
        cand = next((c for c in db.candidates if c["candidate_id"] == app_rec["candidate_id"]), None)
        job  = next((j for j in db.jobs       if j["job_id"]       == app_rec["job_id"]),       None)
        if cand and job:
            score = calculate_ai_score(cand, job)
            scored_apps.append({
                **app_rec,
                "ai_score":       score,
                "candidate_name": cand["name"],
                "job_title":      job["title"],
                "photo":          cand["photo"],
                "location":       cand["location"],
                "candidate_id":   cand["candidate_id"],
            })

    avg_score = round(sum(a["ai_score"] for a in scored_apps) / len(scored_apps)) if scored_apps else 0
    top       = sorted(scored_apps, key=lambda x: x["ai_score"], reverse=True)[:5]

    return jsonify({
        "stats": {
            "open_jobs":    open_jobs,
            "candidates":   total_cands,
            "interviews":   total_ints,
            "hired":        hired,
            "avg_score":    avg_score,
            "applications": len(db.applications),
        },
        "recent_apps":    scored_apps[:6],
        "top_candidates": top,
        "funnel": [
            {"label": "Applications", "value": len(db.applications)},
            {"label": "Screened",     "value": len([a for a in db.applications if a["status"] == "Screened"])},
            {"label": "Interviews",   "value": len(db.interviews)},
            {"label": "Selected",     "value": hired},
        ],
    })


# ── Jobs ───────────────────────────────────────────
@app.route("/api/jobs", methods=["GET"])
def get_jobs():
    search = request.args.get("search", "").lower()
    dept   = request.args.get("dept",   "")

    result = db.jobs
    if search:
        result = [j for j in result if
                  search in j["title"].lower() or
                  search in j["department"].lower()]
    if dept:
        result = [j for j in result if j["department"] == dept]

    enriched = []
    for job in result:
        app_count   = len([a for a in db.applications if a["job_id"] == job["job_id"]])
        skill_names = [get_skill_name(s) for s in job["required_skills"]]
        enriched.append({**job, "app_count": app_count, "skill_names": skill_names})

    return jsonify(enriched)


@app.route("/api/jobs", methods=["POST"])
def add_job():
    data    = request.json
    new_job = {
        "job_id":              len(db.jobs) + 1,
        "title":               data.get("title", ""),
        "dept_id":             int(data.get("dept_id", 1)),
        "department":          data.get("department", ""),
        "experience_required": int(data.get("experience_required", 0)),
        "education":           data.get("education", ""),
        "job_type":            data.get("job_type", "Full-Time"),
        "location":            data.get("location", ""),
        "salary_min":          int(data.get("salary_min", 500000)),
        "salary_max":          int(data.get("salary_max", 1000000)),
        "openings":            int(data.get("openings", 1)),
        "posted_date":         data.get("posted_date", "2024-01-01"),
        "deadline":            data.get("deadline",    "2024-12-31"),
        "status":              "Open",
        "description":         data.get("description", ""),
        "required_skills":     [],
    }
    db.jobs.append(new_job)
    return jsonify({"success": True,
                    "message": f'Job "{new_job["title"]}" posted!',
                    "job": new_job})


# ── Candidates ─────────────────────────────────────
@app.route("/api/candidates", methods=["GET"])
def get_candidates():
    search = request.args.get("search", "").lower()
    exp    = request.args.get("exp",    "")

    result = db.candidates
    if search:
        result = [c for c in result if
                  search in c["name"].lower() or
                  search in c["location"].lower() or
                  search in c["education"].lower()]
    if exp == "0-2":
        result = [c for c in result if c["experience"] <= 2]
    elif exp == "3-5":
        result = [c for c in result if 3 <= c["experience"] <= 5]
    elif exp == "6+":
        result = [c for c in result if c["experience"] >= 6]

    enriched = []
    for cand in result:
        skill_names = [get_skill_name(s) for s in cand["skills"]]
        enriched.append({**cand, "skill_names": skill_names})

    return jsonify(enriched)


@app.route("/api/candidates", methods=["POST"])
def add_candidate():
    data  = request.json
    name  = data.get("name", "")
    parts = name.split()
    photo = "".join(p[0] for p in parts[:2]).upper() if parts else "??"

    new_cand = {
        "candidate_id":  len(db.candidates) + 1,
        "name":          name,
        "email":         data.get("email",    ""),
        "phone":         data.get("phone",    ""),
        "location":      data.get("location", ""),
        "experience":    int(data.get("experience", 0)),
        "education":     data.get("education", ""),
        "college":       data.get("college",   ""),
        "cgpa":          float(data.get("cgpa", 7.0)),
        "skills":        [],
        "certifications": [c.strip() for c in data.get("certifications","").split(",") if c.strip()],
        "applied_date":  "2024-01-25",
        "photo":         photo,
    }
    db.candidates.append(new_cand)
    return jsonify({"success": True,
                    "message": f'Candidate "{name}" added!',
                    "candidate": new_cand})


@app.route("/api/candidates/<int:cid>", methods=["GET"])
def get_candidate_detail(cid):
    cand = next((c for c in db.candidates if c["candidate_id"] == cid), None)
    if not cand:
        return jsonify({"error": "Not found"}), 404

    skill_names = [get_skill_name(s) for s in cand["skills"]]
    cand_apps   = [a for a in db.applications if a["candidate_id"] == cid]
    cand_ints   = [i for i in db.interviews   if i["candidate_id"] == cid]

    enriched_apps = []
    for app_rec in cand_apps:
        job   = next((j for j in db.jobs if j["job_id"] == app_rec["job_id"]), None)
        score = calculate_ai_score(cand, job) if job else 0
        enriched_apps.append({
            **app_rec,
            "job_title": job["title"] if job else "-",
            "ai_score":  score,
        })

    return jsonify({
        **cand,
        "skill_names":  skill_names,
        "applications": enriched_apps,
        "interviews":   cand_ints,
    })


# ── AI Screening ───────────────────────────────────
@app.route("/api/screen/<int:job_id>", methods=["GET"])
def screen_job(job_id):
    threshold = int(request.args.get("threshold", 70))
    job       = next((j for j in db.jobs if j["job_id"] == job_id), None)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    job_apps = [a for a in db.applications if a["job_id"] == job_id]
    ranked   = []

    for app_rec in job_apps:
        cand = next((c for c in db.candidates
                     if c["candidate_id"] == app_rec["candidate_id"]), None)
        if cand:
            ranked.append(enrich_candidate(cand, job))

    ranked.sort(key=lambda x: x["ai_score"], reverse=True)

    qualified = [c for c in ranked if c["ai_score"] >= threshold]
    rejected  = [c for c in ranked if c["ai_score"] <  threshold]

    return jsonify({
        "job":       job,
        "qualified": qualified,
        "rejected":  rejected,
        "stats": {
            "total":     len(ranked),
            "qualified": len(qualified),
            "rejected":  len(rejected),
            "top_score": ranked[0]["ai_score"] if ranked else 0,
            "avg_score": round(sum(c["ai_score"] for c in ranked) / len(ranked)) if ranked else 0,
        },
    })


# ── Interviews ─────────────────────────────────────
@app.route("/api/interviews", methods=["GET"])
def get_interviews():
    search     = request.args.get("search", "").lower()
    status_val = request.args.get("status", "")

    result = db.interviews
    if status_val:
        result = [i for i in result if i["status"] == status_val]

    enriched = []
    for itv in result:
        cand = next((c for c in db.candidates if c["candidate_id"] == itv["candidate_id"]), {})
        job  = next((j for j in db.jobs       if j["job_id"]       == itv["job_id"]),       {})
        row  = {
            **itv,
            "candidate_name": cand.get("name",  ""),
            "job_title":      job.get("title",   ""),
            "photo":          cand.get("photo",  "?"),
        }
        if search and (search not in row["candidate_name"].lower() and
                       search not in row["job_title"].lower()):
            continue
        enriched.append(row)

    return jsonify(enriched)


@app.route("/api/interviews", methods=["POST"])
def add_interview():
    data    = request.json
    new_int = {
        "interview_id": len(db.interviews) + 1,
        "candidate_id": int(data.get("candidate_id")),
        "job_id":       int(data.get("job_id")),
        "round":        data.get("round",       "Technical Round 1"),
        "date":         data.get("date",        ""),
        "time":         data.get("time",        ""),
        "mode":         data.get("mode",        "Video Call"),
        "interviewer":  data.get("interviewer", "TBD"),
        "status":       "Scheduled",
        "rating":       None,
        "feedback":     None,
    }
    db.interviews.append(new_int)
    return jsonify({"success": True,
                    "message": "Interview scheduled!",
                    "interview": new_int})


@app.route("/api/interviews/<int:iid>/complete", methods=["POST"])
def complete_interview(iid):
    itv = next((i for i in db.interviews if i["interview_id"] == iid), None)
    if not itv:
        return jsonify({"error": "Not found"}), 404
    data            = request.json or {}
    itv["status"]   = "Completed"
    itv["rating"]   = data.get("rating",   4)
    itv["feedback"] = data.get("feedback", "Interview completed successfully.")
    return jsonify({"success": True, "message": "Interview marked completed!"})


# ── Hiring ─────────────────────────────────────────
@app.route("/api/hiring", methods=["GET"])
def get_hiring():
    enriched = []
    for h in db.hiring:
        cand = next((c for c in db.candidates if c["candidate_id"] == h["candidate_id"]), {})
        job  = next((j for j in db.jobs       if j["job_id"]       == h["job_id"]),       {})
        enriched.append({
            **h,
            "candidate_name": cand.get("name",  ""),
            "job_title":      job.get("title",   ""),
            "photo":          cand.get("photo",  "?"),
        })
    return jsonify(enriched)


@app.route("/api/hiring", methods=["POST"])
def add_hiring():
    data  = request.json
    new_h = {
        "hiring_id":     len(db.hiring) + 1,
        "candidate_id":  int(data.get("candidate_id")),
        "job_id":        int(data.get("job_id")),
        "decision":      data.get("decision",      "Selected"),
        "offer_salary":  data.get("offer_salary"),
        "decision_date": data.get("decision_date", "2024-02-01"),
        "joining_date":  data.get("joining_date"),
        "decision_by":   data.get("decision_by",   "HR Manager"),
    }
    db.hiring.append(new_h)
    return jsonify({"success": True,
                    "message": "Hiring decision recorded!",
                    "hiring": new_h})


# ── Analytics ──────────────────────────────────────
@app.route("/api/analytics", methods=["GET"])
def analytics():
    dept_data = []
    for dept in db.departments:
        job_ids   = [j["job_id"] for j in db.jobs if j["dept_id"] == dept["dept_id"]]
        app_count = len([a for a in db.applications if a["job_id"] in job_ids])
        dept_data.append({"label": dept["dept_name"], "value": app_count})
    dept_data = sorted([d for d in dept_data if d["value"] > 0],
                       key=lambda x: x["value"], reverse=True)

    skill_count = {}
    for job in db.jobs:
        for s in job["required_skills"]:
            skill_count[s] = skill_count.get(s, 0) + 1
    top_skills = sorted(skill_count.items(), key=lambda x: x[1], reverse=True)[:8]
    skill_data = [{"label": get_skill_name(int(k)), "value": v} for k, v in top_skills]

    all_scores = []
    for app_rec in db.applications:
        cand = next((c for c in db.candidates if c["candidate_id"] == app_rec["candidate_id"]), None)
        job  = next((j for j in db.jobs       if j["job_id"]       == app_rec["job_id"]),       None)
        if cand and job:
            all_scores.append(calculate_ai_score(cand, job))

    exp_data = [
        {"label": "0-2 yrs", "value": len([c for c in db.candidates if c["experience"] <= 2])},
        {"label": "3-5 yrs", "value": len([c for c in db.candidates if 3 <= c["experience"] <= 5])},
        {"label": "6-8 yrs", "value": len([c for c in db.candidates if 6 <= c["experience"] <= 8])},
        {"label": "9+ yrs",  "value": len([c for c in db.candidates if c["experience"] >= 9])},
    ]

    return jsonify({
        "dept_data":  dept_data,
        "skill_data": skill_data,
        "exp_data":   exp_data,
        "score_dist": {
            "high":   len([s for s in all_scores if s >= 80]),
            "medium": len([s for s in all_scores if 60 <= s < 80]),
            "low":    len([s for s in all_scores if s < 60]),
            "avg":    round(sum(all_scores) / len(all_scores)) if all_scores else 0,
        },
        "metrics": {
            "avg_cgpa":    round(sum(c["cgpa"] for c in db.candidates) / len(db.candidates), 1),
            "avg_exp":     round(sum(c["experience"] for c in db.candidates) / len(db.candidates), 1),
            "hire_rate":   round(len([h for h in db.hiring if h["decision"] == "Selected"]) / max(len(db.applications), 1) * 100),
            "total_apps":  len(db.applications),
            "interviews":  len(db.interviews),
            "departments": len(db.departments),
        },
    })


# ── Departments ────────────────────────────────────
@app.route("/api/departments", methods=["GET"])
def get_departments():
    enriched = []
    for dept in db.departments:
        job_ids   = [j["job_id"] for j in db.jobs if j["dept_id"] == dept["dept_id"]]
        app_count = len([a for a in db.applications if a["job_id"] in job_ids])
        enriched.append({**dept, "job_count": len(job_ids), "app_count": app_count})
    return jsonify(enriched)


@app.route("/api/skills", methods=["GET"])
def get_skills():
    return jsonify(db.skills)


# =============================================
if __name__ == "__main__":
    base = os.path.dirname(os.path.abspath(__file__))
    print("=" * 50)
    print("  🤖 AI Recruitment System")
    print(f"  📂 Folder : {base}")
    print(f"  📄 HTML   : {os.path.join(base, 'index.html')}")
    print(f"  ✅ Exists : {os.path.exists(os.path.join(base, 'index.html'))}")
    print("  🌐 Open   : http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, port=5000)