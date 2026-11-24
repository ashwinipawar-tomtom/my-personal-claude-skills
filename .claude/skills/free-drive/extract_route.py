"""Pull the newest tomtom-routing geometry out of this project's Claude Code transcripts.

The tomtom-routing MCP result (response_detail="geometry") lands in the session
transcript (.jsonl) or, when large, in a tool-results file. This finds the most
recent one and writes its LineString coordinates ([lon, lat] pairs) to a JSON file,
so the route never has to be retyped.

Usage: python3 -I extract_route.py <out.json>
"""
import glob, json, os, sys

PROJECT_DIR = os.path.expanduser("~/.claude/projects/-Users-ashwini-pawar-myproject")
MARKER = '"geometry":{"type":"FeatureCollection"'


def coords_from(text):
    """Return the last route LineString coordinates found in text, or None."""
    text = text.replace('\\"', '"')
    i = text.rfind(MARKER)
    if i < 0:
        return None
    j = text.find('"coordinates":[', i)
    if j < 0:
        return None
    j += len('"coordinates":')
    depth = 0
    for k in range(j, len(text)):
        if text[k] == "[":
            depth += 1
        elif text[k] == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[j:k + 1])
                except ValueError:
                    return None
    return None


files = glob.glob(os.path.join(PROJECT_DIR, "*.jsonl")) + glob.glob(
    os.path.join(PROJECT_DIR, "*", "tool-results", "*"))
files.sort(key=os.path.getmtime, reverse=True)

for path in files[:20]:
    try:
        lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
    except OSError:
        continue
    for line in reversed(lines):
        if MARKER.replace('"', '\\"') in line or MARKER in line:
            coords = coords_from(line)
            if coords and len(coords) >= 2:
                json.dump(coords, open(sys.argv[1], "w"))
                print(f"{len(coords)} points from {os.path.basename(path)}; "
                      f"start {coords[0]}, end {coords[-1]}")
                sys.exit(0)

print("No tomtom-routing geometry found. Call tomtom-routing with response_detail='geometry' first.")
sys.exit(1)
