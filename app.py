from flask import Flask, request, render_template, redirect, url_for
import requests as req
from datetime import datetime, timedelta, date
import random
import os
import markdown
from dotenv import load_dotenv
from google import genai

load_dotenv()

app = Flask(__name__)

CF_HANDLE = "akcodesalot"
_cf_cache = {"stats": None, "time": None, "advice": None}


def get_cf_stats():
    """Fetch CF user stats with 5-minute caching."""
    now = datetime.now()
    if _cf_cache["stats"] and _cf_cache["time"] and (now - _cf_cache["time"]).seconds < 300:
        return _cf_cache["stats"]

    stats = {"rating": "N/A", "maxRating": "N/A", "rank": "N/A", "total_solved": 0, "rating_dist": {}}
    try:
        r = req.get(f"https://codeforces.com/api/user.info?handles={CF_HANDLE}", timeout=5)
        d = r.json()
        if d["status"] == "OK":
            u = d["result"][0]
            stats["rating"] = u.get("rating", "N/A")
            stats["maxRating"] = u.get("maxRating", "N/A")
            stats["rank"] = u.get("rank", "N/A").title()
    except Exception as e:
        print(f"CF user.info error: {e}")

    try:
        r = req.get(f"https://codeforces.com/api/user.status?handle={CF_HANDLE}&count=5000", timeout=10)
        d = r.json()
        if d["status"] == "OK":
            solved = {}   # problem_id -> rating
            for s in d["result"]:
                if s["verdict"] == "OK":
                    prob = s["problem"]
                    pid = f"{prob.get('contestId', '')}{prob['index']}"
                    if pid not in solved:
                        solved[pid] = prob.get("rating")  # None if unrated

            stats["total_solved"] = len(solved)

            # Count per rating bucket
            dist = {}
            for rating in solved.values():
                if rating is not None:
                    dist[rating] = dist.get(rating, 0) + 1

            # Return sorted by rating
            stats["rating_dist"] = dict(sorted(dist.items()))
    except Exception as e:
        print(f"CF user.status error: {e}")

    _cf_cache["stats"] = stats
    _cf_cache["time"] = now
    return stats


def get_heatmap():
    """Fetch last 52 weeks of AC submission counts per day, starting on a Sunday."""
    today = date.today()
    start = today - timedelta(weeks=52)
    # Shift start back to the nearest Sunday (weekday() is 0 for Mon, 6 for Sun)
    days_to_sunday = (start.weekday() + 1) % 7
    start = start - timedelta(days=days_to_sunday)

    # Initialize all days to 0
    day_counts = {}
    cur = start
    while cur <= today:
        day_counts[cur.strftime("%Y-%m-%d")] = 0
        cur += timedelta(days=1)

    try:
        r = req.get(
            f"https://codeforces.com/api/user.status?handle={CF_HANDLE}&count=10000",
            timeout=15
        )
        d = r.json()
        if d["status"] == "OK":
            for sub in d["result"]:
                if sub["verdict"] == "OK":
                    sub_date = datetime.fromtimestamp(sub["creationTimeSeconds"]).date()
                    date_str = sub_date.strftime("%Y-%m-%d")
                    if date_str in day_counts:
                        day_counts[date_str] += 1
    except Exception as e:
        print(f"CF heatmap error: {e}")

    return sorted(day_counts.items())  # list of (date_str, count)


@app.context_processor
def inject_cf_stats():
    """Make cf_stats available in every template (for aside)."""
    return {"cf_stats": get_cf_stats()}


def get_cf_solved_problems():
    """Fetch all unique accepted problems from CF API, sorted by rating."""
    problems = []
    seen = set()
    try:
        r = req.get(
            f"https://codeforces.com/api/user.status?handle={CF_HANDLE}&count=10000",
            timeout=15
        )
        d = r.json()
        if d["status"] == "OK":
            for sub in d["result"]:
                if sub["verdict"] == "OK":
                    prob = sub["problem"]
                    contest_id = prob.get("contestId", "")
                    index = prob.get("index", "")
                    pid = f"{contest_id}{index}"
                    if pid not in seen:
                        seen.add(pid)
                        problems.append({
                            "pid":    pid,
                            "title":  prob.get("name", "N/A"),
                            "rating": prob.get("rating"),   # None if unrated
                            "link":   f"https://codeforces.com/problemset/problem/{contest_id}/{index}",
                            "tags":   ", ".join(prob.get("tags", []))
                        })
    except Exception as e:
        print(f"CF solved problems error: {e}")

    # Sort: rated problems by rating, unrated at the end
    problems.sort(key=lambda p: (p["rating"] is None, p["rating"] or 0))
    return problems


def get_cf_candidate_problems(user_rating):
    """Fetch unsolved CF problems roughly +0 to +300 above user's rating."""
    solved = {p["pid"] for p in get_cf_solved_problems()}
    try:
        r = req.get("https://codeforces.com/api/problemset.problems", timeout=15)
        d = r.json()
        if d["status"] != "OK":
            return []
        
        all_problems = d["result"]["problems"]
        target_min = user_rating if isinstance(user_rating, int) else 800
        target_max = target_min + 300
        
        candidates = []
        for p in all_problems:
            pid = f"{p.get('contestId', '')}{p.get('index', '')}"
            prating = p.get("rating")
            if pid not in solved and prating is not None:
                if target_min <= prating <= target_max:
                    candidates.append({
                        "pid": pid,
                        "title": p.get("name"),
                        "rating": prating,
                        "tags": p.get("tags", [])
                    })
        
        if len(candidates) > 30:
            candidates = random.sample(candidates, 30)
        return candidates
    except Exception as e:
        print(f"Error fetching problemset: {e}")
        return []


def get_birch_advice(force_refresh=False):
    if not force_refresh and _cf_cache.get("advice"):
        return _cf_cache["advice"]

    # Force reload of .env so we don't need to restart the server when adding the key
    load_dotenv(override=True)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        return "<p>Ah! I seem to have misplaced my <b>Gemini API Key</b>! Please add it to your <code>.env</code> file so we can begin your training!</p>"
    
    stats = get_cf_stats()
    urating = stats.get("rating")
    rating_val = urating if isinstance(urating, int) else 800
    candidates = get_cf_candidate_problems(rating_val)
    
    if not candidates:
        return "<p>Oh my! The Codeforces Pokédex seems to be offline. Try again later!</p>"
        
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    You are Professor Birch from Pokémon Ruby/Sapphire/Emerald.
    You are an enthusiastic researcher, but instead of Pokémon, you research competitive programming!
    Analyze this user's Codeforces stats: Rating {stats['rating']}, Total Solved: {stats['total_solved']}.
    Here is a list of candidate unsolved problems for them:
    {candidates}
    
    Select exactly 3 problems from the list that they should solve next to improve.
    Speak directly to the user in Professor Birch's enthusiastic, slightly absent-minded but encouraging tone.
    Explain why each problem is a good fit for their training.
    Format your response in Markdown (bolding problem titles and ratings). Keep it relatively brief, around 3 paragraphs. Do not use asterisks for actions.
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        # Convert markdown to html and cache it
        html_advice = markdown.markdown(response.text)
        _cf_cache["advice"] = html_advice
        return html_advice
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return "<p>Oh no, a wild Error appeared! The Gemini API failed to respond. Check your API key and try again.</p>"


@app.route("/")
def home():
    heatmap = get_heatmap()
    stats = get_cf_stats()
    rating_dist = stats.get("rating_dist", {})
    return render_template("home.html", heatmap=heatmap, rating_dist=rating_dist)


@app.route("/view")
def view():
    problems = get_cf_solved_problems()
    return render_template("view.html", problems=problems)


@app.route("/sort", methods=["GET", "POST"])
def sort():
    problems = []
    rating = None
    if request.method == "POST":
        rating = request.form.get("rating")
        try:
            r_int = int(rating)
        except (ValueError, TypeError):
            r_int = None
            
        all_solved = get_cf_solved_problems()
        if r_int is not None:
            problems = [p for p in all_solved if p.get("rating") == r_int]
            
    return render_template("sort.html", problems=problems, rating=rating)


@app.route("/coach")
def coach():
    force = request.args.get("refresh", False)
    advice_html = get_birch_advice(force_refresh=force)
    return render_template("coach.html", advice=advice_html)


if __name__ == "__main__":
    app.run(debug=True)
