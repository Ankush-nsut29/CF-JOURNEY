from flask import Flask, request, render_template, redirect, url_for
import requests as req
from datetime import datetime, timedelta, date
import random
import os
import json
import markdown
from dotenv import load_dotenv
from google import genai
from neetcode150 import NEETCODE_150, ROADMAP_LEVELS
from a2oj_ladders import A2OJ_LADDERS, ROADMAP_LEVELS_A2OJ
from dotenv import load_dotenv
from google import genai

load_dotenv()

app = Flask(__name__)

CF_HANDLE = "akcodesalot"
_cf_cache = {"stats": None, "stats_time": None, "advice": None, "heatmap": None, "heatmap_time": None, "submissions": None, "submissions_time": None}

LC_HANDLE = os.environ.get("LC_USERNAME", "isaidduh")
_lc_cache = {"stats": None, "time": None, "advice": None, "recent": None, "recent_time": None, "heatmap": None, "heatmap_time": None}


def _get_cf_submissions():
    now = datetime.now()
    if _cf_cache.get("submissions") and _cf_cache.get("submissions_time") and (now - _cf_cache.get("submissions_time")).total_seconds() < 3600:
        return _cf_cache["submissions"]

    try:
        r = req.get(f"https://codeforces.com/api/user.status?handle={CF_HANDLE}&count=10000", timeout=15)
        if r.status_code == 200:
            d = r.json()
            if d.get("status") == "OK":
                _cf_cache["submissions"] = d["result"]
                _cf_cache["submissions_time"] = now
                return d["result"]
    except Exception as e:
        print(f"CF submissions error: {e}")
        
    return _cf_cache.get("submissions") or []


def get_cf_stats():
    """Fetch CF user stats with 5-minute caching."""
    now = datetime.now()
    if _cf_cache.get("stats") and _cf_cache.get("stats_time") and (now - _cf_cache.get("stats_time")).total_seconds() < 3600:
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
        submissions = _get_cf_submissions()
        solved = {}   # problem_id -> rating
        for s in submissions:
            if s.get("verdict") == "OK":
                prob = s.get("problem", {})
                pid = f"{prob.get('contestId', '')}{prob.get('index', '')}"
                if pid and pid not in solved:
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

    if stats["rating"] != "N/A" and stats["total_solved"] > 0:
        _cf_cache["stats"] = stats
        _cf_cache["stats_time"] = now
    elif _cf_cache.get("stats"):
        return _cf_cache["stats"]
    return stats


def get_heatmap():
    """Fetch last 52 weeks of AC submission counts per day, starting on a Sunday."""
    now = datetime.now()
    if _cf_cache.get("heatmap") and _cf_cache.get("heatmap_time") and (now - _cf_cache.get("heatmap_time")).total_seconds() < 3600:
        return _cf_cache["heatmap"]

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
        submissions = _get_cf_submissions()
        for sub in submissions:
            if sub.get("verdict") == "OK":
                sub_date = datetime.fromtimestamp(sub.get("creationTimeSeconds", 0)).date()
                date_str = sub_date.strftime("%Y-%m-%d")
                if date_str in day_counts:
                    day_counts[date_str] += 1
    except Exception as e:
        print(f"CF heatmap error: {e}")

    result = sorted(day_counts.items())
    # Only cache if data seems valid (has submissions)
    if sum(day_counts.values()) > 0:
        _cf_cache["heatmap"] = result
        _cf_cache["heatmap_time"] = now
    elif _cf_cache.get("heatmap"):
        return _cf_cache["heatmap"]
    return result


@app.context_processor
def inject_cf_stats():
    """Make cf_stats available in every template (for aside)."""
    return {"cf_stats": get_cf_stats()}

def get_lc_stats():
    now = datetime.now()
    if _lc_cache.get("stats") and _lc_cache.get("stats_time") and (now - _lc_cache.get("stats_time")).total_seconds() < 3600:
        return _lc_cache["stats"]
    
    url = 'https://leetcode.com/graphql'
    query = '''
    query userSessionProgress($username: String!) {
      matchedUser(username: $username) {
        submitStats {
          acSubmissionNum {
            difficulty
            count
          }
        }
      }
    }
    '''
    stats = {"All": 0, "Easy": 0, "Medium": 0, "Hard": 0}
    try:
        r = req.post(url, json={'query': query, 'variables': {'username': LC_HANDLE}}, timeout=5)
        d = r.json()
        ac_num = d.get("data", {}).get("matchedUser", {}).get("submitStats", {}).get("acSubmissionNum", [])
        for item in ac_num:
            diff = item.get("difficulty")
            if diff in stats:
                stats[diff] = item.get("count")
    except Exception as e:
        print(f"LC stats error: {e}")

    if stats["All"] > 0 or not _lc_cache.get("stats"):
        _lc_cache["stats"] = stats
        _lc_cache["stats_time"] = now
    elif _lc_cache.get("stats"):
        return _lc_cache["stats"]
    return stats

def get_lc_recent():
    now = datetime.now()
    if _lc_cache.get("recent") and _lc_cache.get("recent_time") and (now - _lc_cache.get("recent_time")).total_seconds() < 3600:
        return _lc_cache["recent"]

    url = 'https://leetcode.com/graphql'
    query = '''
    query recentAcSubmissions($username: String!) {
      recentAcSubmissionList(username: $username, limit: 20) {
        title
        titleSlug
        timestamp
      }
    }
    '''
    recent = []
    try:
        r = req.post(url, json={'query': query, 'variables': {'username': LC_HANDLE}}, timeout=5)
        d = r.json()
        recent = d.get("data", {}).get("recentAcSubmissionList", [])
        
        # Batch fetch difficulty
        if recent:
            diff_query = "query { " + " ".join([f'q{i}: question(titleSlug: "{item.get("titleSlug")}") {{ difficulty }}' for i, item in enumerate(recent)]) + " }"
            diff_r = req.post(url, json={'query': diff_query}, timeout=5)
            diff_d = diff_r.json().get("data", {})
            for i, item in enumerate(recent):
                item["link"] = f"https://leetcode.com/problems/{item.get('titleSlug')}/"
                item["difficulty"] = diff_d.get(f"q{i}", {}).get("difficulty", "Unknown")
                
    except Exception as e:
        print(f"LC recent error: {e}")
        
    if recent:
        _lc_cache["recent"] = recent
        _lc_cache["recent_time"] = now
    elif _lc_cache.get("recent"):
        return _lc_cache["recent"]
    return recent

def get_lc_heatmap():
    now = datetime.now()
    if _lc_cache.get("heatmap") and _lc_cache.get("heatmap_time") and (now - _lc_cache.get("heatmap_time")).total_seconds() < 3600:
        return _lc_cache["heatmap"]

    url = 'https://leetcode.com/graphql'
    query = '''
    query userProfileCalendar($username: String!, $year: Int) {
      matchedUser(username: $username) {
        userCalendar(year: $year) {
          submissionCalendar
        }
      }
    }
    '''
    today = date.today()
    start = today - timedelta(weeks=52)
    days_to_sunday = (start.weekday() + 1) % 7
    start = start - timedelta(days=days_to_sunday)

    day_counts = {}
    cur = start
    while cur <= today:
        day_counts[cur.strftime("%Y-%m-%d")] = 0
        cur += timedelta(days=1)

    try:
        r = req.post(url, json={'query': query, 'variables': {'username': LC_HANDLE}}, timeout=5)
        d = r.json()
        cal_str = d.get("data", {}).get("matchedUser", {}).get("userCalendar", {}).get("submissionCalendar", "{}")
        if cal_str:
            cal_data = json.loads(cal_str)
            for ts_str, count in cal_data.items():
                ts = int(ts_str)
                sub_date = datetime.fromtimestamp(ts).date()
                date_str = sub_date.strftime("%Y-%m-%d")
                if date_str in day_counts:
                    day_counts[date_str] += count
    except Exception as e:
        print(f"LC heatmap error: {e}")

    result = sorted(day_counts.items())
    if sum(day_counts.values()) > 0:
        _lc_cache["heatmap"] = result
        _lc_cache["heatmap_time"] = now
    elif _lc_cache.get("heatmap"):
        return _lc_cache["heatmap"]
    return result

@app.context_processor
def inject_lc_stats():
    """Make lc_stats available in every template (for aside)."""
    return {"lc_stats": get_lc_stats()}

@app.template_filter('datetimeformat')
def datetimeformat(value, format='%Y-%m-%d %H:%M'):
    return datetime.fromtimestamp(value).strftime(format)


def get_cf_solved_problems():
    """Fetch all unique accepted problems from CF API, sorted by rating."""
    now = datetime.now()
    if _cf_cache.get("solved") and _cf_cache.get("solved_time") and (now - _cf_cache.get("solved_time")).total_seconds() < 3600:
        return _cf_cache["solved"]
        
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
    if problems:
        _cf_cache["solved"] = problems
        _cf_cache["solved_time"] = now
    elif _cf_cache.get("solved"):
        return _cf_cache["solved"]
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


def get_birch_advice(force_refresh=False, code=None, action="recommend"):
    if not force_refresh and action == "recommend" and _cf_cache.get("advice"):
        return _cf_cache["advice"]

    # Force reload of .env so we don't need to restart the server when adding the key
    load_dotenv(override=True)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        return "<p>Ah! I seem to have misplaced my <b>Gemini API Key</b>! Please add it to your <code>.env</code> file (or host environment variables) so we can begin your training!</p>"
    
    client = genai.Client(api_key=api_key)
    
    if action == "recommend":
        stats = get_cf_stats()
        urating = stats.get("rating")
        rating_val = urating if isinstance(urating, int) else 800
        candidates = get_cf_candidate_problems(rating_val)
        
        if not candidates:
            return "<p>Oh my! The Codeforces Pokédex seems to be offline. Try again later!</p>"
            
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
    else:
        prompt = f"""
        You are Professor Birch from Pokémon Ruby/Sapphire/Emerald.
        You are an enthusiastic researcher, but instead of Pokémon, you research competitive programming!
        Please review the following Python solution the user submitted for a competitive programming problem.
        
        Code:
        ```python
        {code}
        ```
        
        Give a brief review on its Time & Space complexity, any edge cases missed, and how it could be written more efficiently.
        Format your response in markdown. Be encouraging! Do not use asterisks for actions.
        """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
    except Exception as e:
        print(f"Flash model failed ({e}), falling back to Pro model...")
        try:
            response = client.models.generate_content(
                model='gemini-2.5-pro',
                contents=prompt,
            )
        except Exception as fallback_e:
            print(f"Gemini API Error: {fallback_e}")
            return "<p>Oh no, a wild Error appeared! Both Gemini models failed to respond. Check your API key and try again.</p>"

    # Convert markdown to html and cache it if recommendation
    html_advice = markdown.markdown(response.text)
    if action == "recommend":
        _cf_cache["advice"] = html_advice
    return html_advice


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


@app.route("/coach", methods=["GET", "POST"])
def coach():
    advice_html = None
    if request.method == "POST":
        action = request.form.get("action_type")
        code = request.form.get("code")
        advice_html = get_birch_advice(code=code, action=action)
    return render_template("coach.html", advice=advice_html)


@app.route("/cf/roadmap")
def cf_roadmap():
    solved = get_cf_solved_problems()
    solved_pids = [p["pid"] for p in solved]
    return render_template("cf_roadmap.html", levels=ROADMAP_LEVELS_A2OJ, a2oj=A2OJ_LADDERS, solved_pids=solved_pids)


@app.route("/lc")
def lc_home():
    heatmap = get_lc_heatmap()
    stats = get_lc_stats()
    rating_dist = {
        "Easy": stats.get("Easy", 0),
        "Medium": stats.get("Medium", 0),
        "Hard": stats.get("Hard", 0)
    }
    return render_template("lc_home.html", heatmap=heatmap, rating_dist=rating_dist)

@app.route("/lc/view")
def lc_view():
    problems = get_lc_recent()
    return render_template("lc_view.html", problems=problems)

def get_elm_advice(solved_dict, code=None, action="recommend"):
    load_dotenv(override=True)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        return "<p>Ah! I seem to have misplaced my <b>Gemini API Key</b>! Please add it to your <code>.env</code> file (or host environment variables) so we can begin your training!</p>"
        
    client = genai.Client(api_key=api_key)
    stats = get_lc_stats()
    
    solved_list = list(solved_dict.keys())
    solved_str = ", ".join(solved_list) if solved_list else "None"
    
    recent_list = get_lc_recent()
    recent_titles = [r.get("title") for r in recent_list[:5]] if recent_list else []
    recent_str = ", ".join(recent_titles) if recent_titles else "None"
    
    if action == "recommend":
        prompt = f"""
        You are Professor Elm from Pokemon, but as an expert LeetCode coach.
        The user's LeetCode stats are:
        Easy: {stats.get('Easy', 0)}, Medium: {stats.get('Medium', 0)}, Hard: {stats.get('Hard', 0)}
        
        They have manually marked the following problems as completed from the NeetCode 150 list:
        {solved_str}
        
        Their most recently solved problems on LeetCode are:
        {recent_str}
        
        Based on their stats and the standard NeetCode 150 topic progression (Arrays -> Two Pointers -> Sliding Window -> Stack -> Binary Search -> Linked List -> Trees etc.),
        Recommend the NEXT 3 specific problems they should tackle. 
        Format your response nicely with markdown, using a friendly Professor Elm tone.
        """
    else:
        prompt = f"""
        You are Professor Elm from Pokemon, but as an expert LeetCode coach.
        Please review the following Python solution the user submitted for a LeetCode problem.
        
        Code:
        ```python
        {code}
        ```
        
        Give a brief review on its Time & Space complexity, any edge cases missed, and how it could be written more efficiently.
        Format your response in markdown. Be encouraging!
        """
        
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
    except Exception as e:
        print(f"Flash model failed ({e}), falling back to Pro model...")
        try:
            response = client.models.generate_content(
                model='gemini-2.5-pro',
                contents=prompt,
            )
        except Exception as fallback_e:
            print(f"Gemini error: {fallback_e}")
            return f"<p>Oops, my Pokedex (Gemini API) is malfunctioning. Both models failed: {fallback_e}</p>"
            
    return markdown.markdown(response.text)

@app.route("/lc/coach", methods=["GET", "POST"])
def lc_coach():
    advice_html = None
    if request.method == "POST":
        action = request.form.get("action_type")
        code = request.form.get("code")
        solved_str = request.form.get("solved_problems", "{}")
        try:
            solved_dict = json.loads(solved_str)
        except:
            solved_dict = {}
            
        advice_html = get_elm_advice(solved_dict, code=code, action=action)
        
    return render_template("lc_coach.html", advice=advice_html)


@app.route("/lc/roadmap")
def lc_roadmap():
    return render_template("lc_roadmap.html", levels=ROADMAP_LEVELS, neetcode=NEETCODE_150)

if __name__ == "__main__":
    app.run(debug=True)
