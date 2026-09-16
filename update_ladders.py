import requests
import json
import pprint
from a2oj_ladders import A2OJ_LADDERS, ROADMAP_LEVELS_A2OJ

def get_rating_box(rating):
    if rating < 1300: return "Codeforces Rating < 1300"
    if 1300 <= rating <= 1399: return "1300 <= Codeforces Rating <= 1399"
    if 1400 <= rating <= 1499: return "1400 <= Codeforces Rating <= 1499"
    if 1500 <= rating <= 1599: return "1500 <= Codeforces Rating <= 1599"
    if 1600 <= rating <= 1699: return "1600 <= Codeforces Rating <= 1699"
    if 1700 <= rating <= 1799: return "1700 <= Codeforces Rating <= 1799"
    if 1800 <= rating <= 1899: return "1800 <= Codeforces Rating <= 1899"
    if 1900 <= rating <= 1999: return "1900 <= Codeforces Rating <= 1999"
    if 2000 <= rating <= 2099: return "2000 <= Codeforces Rating <= 2099"
    if 2100 <= rating <= 2199: return "2100 <= Codeforces Rating <= 2199"
    if rating >= 2200: return "Codeforces Rating >= 2200"
    return None

def update_a2oj_ratings():
    # Fetch current problem ratings
    r = requests.get("https://codeforces.com/api/problemset.problems")
    data = r.json()
    ratings = {}
    for p in data["result"]["problems"]:
        pid = f"{p.get('contestId', '')}{p.get('index', '')}"
        if 'rating' in p:
            ratings[pid] = p['rating']
            
    rating_boxes = [b[0] for b in ROADMAP_LEVELS_A2OJ]
    
    # Collect all problems currently in ANY rating box
    all_rating_problems = []
    seen = set()
    for box in rating_boxes:
        for p in A2OJ_LADDERS.get(box, []):
            if p['pid'] not in seen:
                all_rating_problems.append(p)
                seen.add(p['pid'])
                
    # Clear the old boxes
    for box in rating_boxes:
        A2OJ_LADDERS[box] = []
        
    # Re-distribute based on new ratings
    for p in all_rating_problems:
        pid = p['pid']
        rating = ratings.get(pid)
        if rating is None:
            # If the problem has no rating now, it's hard to place. Just put it in <1300 or drop. We'll skip or place in < 1300
            rating = 800
            
        box_name = get_rating_box(rating)
        p['_rating'] = rating # Temporary for sorting
        if box_name in A2OJ_LADDERS:
            A2OJ_LADDERS[box_name].append(p)
            
    # Sort them by rating
    for box in rating_boxes:
        A2OJ_LADDERS[box].sort(key=lambda x: (x['_rating'], x['pid']))
        # Remove the temporary key
        for p in A2OJ_LADDERS[box]:
            del p['_rating']
            
    # Write back to file
    with open("a2oj_ladders.py", "w", encoding="utf-8") as f:
        f.write("A2OJ_LADDERS = {\n")
        
        # We need to print dict nicely
        # Since it's huge, we iterate manually to not block
        items = list(A2OJ_LADDERS.items())
        for i, (k, v) in enumerate(items):
            f.write(f'    "{k}": [\n')
            for j, p in enumerate(v):
                f.write('        {\n')
                f.write(f'            "title": {json.dumps(p["title"])},\n')
                f.write(f'            "link": {json.dumps(p["link"])},\n')
                f.write(f'            "pid": {json.dumps(p["pid"])}\n')
                if j == len(v) - 1:
                    f.write('        }\n')
                else:
                    f.write('        },\n')
            if i == len(items) - 1:
                f.write('    ]\n')
            else:
                f.write('    ],\n')
        f.write("}\n\n")
        
        f.write("ROADMAP_LEVELS_A2OJ = [\n")
        for i, box in enumerate(ROADMAP_LEVELS_A2OJ):
            f.write('    [\n')
            f.write(f'        "{box[0]}"\n')
            if i == len(ROADMAP_LEVELS_A2OJ) - 1:
                f.write('    ]\n')
            else:
                f.write('    ],\n')
        f.write("]\n")

if __name__ == "__main__":
    update_a2oj_ratings()
    print("Done!")
