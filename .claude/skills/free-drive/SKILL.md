---
name: free-drive
description: Simulates driving on the connected test tablet by moving the TomTom fake GPS along a real road route at a set speed. Use when the user asks to start free driving, drive/move/simulate the car on the tablet, drive to a destination for a navigation test, or stop the drive.
---

# Skill: free-drive

Move the tablet's fake GPS along a real road route, one position per second, so ANA behaves as if the car is driving. Use it for free driving (no route in the app) or to drive the route of a navigation test.

## Trigger

User says something like:
- "start free driving mode on tablet"
- "drive to Utrecht at 80 km/h"
- "simulate driving for this test case"
- "stop the drive" / "is the free driving script running?"

## Why a script is needed

The TomTom fake GPS tool (`com.tomtom.tool.fakegpsservice`) only accepts one broadcast, `com.tomtom.tool.fakegpsservice.POSITION`, with float extras `lat`, `lon`, `speed` (m/s) and `bearing`. It re-publishes that position but never moves it (checked in its APK on 2026-11-24). `drive.py` does the moving from the Mac. There is no drive or route mode in the tool itself; don't look for one.

## Constants

| Value | Data |
|---|---|
| Device serial | `R52Y206FKSE` (Galaxy Tab S9 FE), unless the user gives another |
| Skill folder | `/Users/ashwini.pawar/myproject/.claude/skills/free-drive` |
| Work folder | the session scratchpad, subfolder `free-drive/` (never `/tmp`) |
| Default speed | 50 km/h |

## Inputs

All optional. Never ask for them; use the defaults.

| Input | Default |
|---|---|
| Start | the tablet's current GPS position (Step 1) |
| Destination / via points | none: build a loop of about 30–40 km from the start (Step 2) |
| Speed | 50 km/h |
| Mode | loop forever for free driving; `--once` (stop at the end) when the user names a destination or a test route |

---

## Step 1 — Check the device and the current position

```bash
adb devices -l
adb -s R52Y206FKSE shell dumpsys activity services | grep -c com.tomtom.tool.fakegpsservice
adb -s R52Y206FKSE shell dumpsys location | grep -m1 "last location=Location\[gps"
```

- If the device is missing, stop and tell the user to connect the tablet.
- If the fake GPS service isn't running, tell the user to open the FakeGPS app on the tablet once, then retry. Don't try to start it some other way.
- The `gps` line gives the start position, e.g. `52.377201,4.909800` (lat, lon). Its `mock` tag shows the fake GPS is active.
- Also check that no earlier drive is still running: `pgrep -fl free-drive/drive.py`. If one is, stop it first (Step 5). Two drivers fight over the position.

## Step 2 — Get a road route

Load `mcp__claude_ai_TomTom_Maps__tomtom-routing` with ToolSearch if needed. Call it with `response_detail: "geometry"`. `locations` are `[lon, lat]` pairs (longitude first):

- **Free driving (no destination):** make a loop through 2–3 points about 5–10 km away on main roads, ending back at the start, e.g. `[start, p1, p2, start]`. The default Amsterdam-office loop used on 2026-11-24 was `[[4.9098,52.377201],[4.889,52.3405],[4.838,52.389],[4.9098,52.377201]]`: 35 km over the A10 east/south, RAI, A10 west and Sloterdijk.
- **Destination given:** `[start, destination]`. Geocode the place name first (`tomtom-geocode` or `tomtom-fuzzy-search`) if it isn't coordinates.
- **Test case route:** use the test's set location and destination, e.g. NAV-169376's `51.582385, 5.189882` → `51.586974, 5.196116`. Teleport the tablet to the test's start first: `adb -s R52Y206FKSE shell am broadcast -a com.tomtom.tool.fakegpsservice.POSITION --ef lat <lat> --ef lon <lon>`.

Don't copy the coordinates out of the result by hand. Step 3 extracts them.

## Step 3 — Save the route

```bash
mkdir -p <scratchpad>/free-drive
python3 -I /Users/ashwini.pawar/myproject/.claude/skills/free-drive/extract_route.py <scratchpad>/free-drive/route.json
```

It finds the newest tomtom-routing geometry in this project's session transcripts and prints the point count and start/end. Check that the start is near the tablet's position (or the test's start). If it says nothing was found, redo Step 2 with `response_detail: "geometry"`.

## Step 4 — Start driving

Run it with the Bash tool's `run_in_background: true` (not `&`):

```bash
cd <scratchpad>/free-drive && python3 -I /Users/ashwini.pawar/myproject/.claude/skills/free-drive/drive.py route.json --speed 50 > drive.log 2>&1
```

Add `--once` for a destination or test route; it parks at the end with speed 0. Add `--serial <serial>` for another device.

Then check that the position moves:

```bash
sleep 6; adb -s R52Y206FKSE shell dumpsys location | grep -m1 "last location=Location\[gps"
adb -s R52Y206FKSE shell dumpsys activity activities | grep -m1 topResumedActivity
```

The `gps` line should show a new position, `vel=` equal to the speed in m/s (50 km/h = 13.89) and a `bear=` value. The ANA app (`com.tomtom.automotive.navigation.reference`) should be in front.

Tell the user:
- the route, its length and speed, and whether it loops or stops at the end;
- the first position seen;
- that the speed is constant (no speed limits or stops), so it's the same speed on motorways and in town;
- that it stops if the Mac sleeps or the cable comes off, and the tablet then keeps the last position;
- that in **free driving** (no route in the app) ANA shows no POI events (petrol stations, rest areas, EV chargers). `FreeDrivingHorizonOptionsProvider.poiCategories()` is empty, so POI test cases need navigation started.

## Step 5 — Status and stop

- **Status:** `pgrep -fl free-drive/drive.py`, the `gps` line from `dumpsys location`, and the last lines of `drive.log`. Report where the tablet is and roughly how far into the lap.
- **Stop:** `pkill -f free-drive/drive.py`, then confirm with `pgrep` and give the final position. A background task notice with exit code 143 afterwards just means it was killed on request, not a crash.

---

## Constraints

- Only one driver at a time. Always check with `pgrep` before starting.
- Never type out route coordinates by hand. Use `extract_route.py`.
- Don't use `adb screencap` to check the drive; `dumpsys location` is enough.
- Keep files in the session scratchpad, not `/tmp`.
- Don't change app settings (vehicle type, configuration mode) unless the user asks. If a test needs them, say what to set, using the Developer Settings UI (broadcasts don't work for settings).
