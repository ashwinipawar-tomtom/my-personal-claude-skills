"""Drive the tablet's fake GPS along a route (free driving / drive simulation).

The TomTom fake GPS tool (com.tomtom.tool.fakegpsservice) only holds one static
position, so this script moves it: it walks the route at a constant speed and sends
one POSITION broadcast (lat, lon, speed m/s, bearing) per second.

Usage: python3 -I drive.py <route.json> [--speed KMH] [--serial SERIAL] [--once]
  route.json  JSON list of [lon, lat] points (from extract_route.py)
  --speed     km/h, default 50
  --serial    adb serial, default R52Y206FKSE
  --once      drive the route once and stop at the end (default: loop forever)
Stop it by killing the process; the tablet then keeps the last position sent.
"""
import argparse, json, math, subprocess, time

ap = argparse.ArgumentParser()
ap.add_argument("route")
ap.add_argument("--speed", type=float, default=50.0)
ap.add_argument("--serial", default="R52Y206FKSE")
ap.add_argument("--once", action="store_true")
args = ap.parse_args()

R = 6371000.0
v = args.speed / 3.6  # m/s


def dist(a, b):
    lat1, lat2 = math.radians(a[1]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, math.radians(b[0] - a[0])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def bearing(a, b):
    lat1, lat2 = math.radians(a[1]), math.radians(b[1])
    dlon = math.radians(b[0] - a[0])
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def send(lon, lat, brg, speed):
    subprocess.run(
        ["adb", "-s", args.serial, "shell", "am", "broadcast",
         "-a", "com.tomtom.tool.fakegpsservice.POSITION",
         "--ef", "lat", f"{lat:.6f}", "--ef", "lon", f"{lon:.6f}",
         "--ef", "speed", f"{speed:.2f}", "--ef", "bearing", f"{brg:.1f}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


route = json.load(open(args.route))
pts = [route[0]]
for p in route[1:]:  # drop zero-length segments
    if dist(pts[-1], p) > 0.5:
        pts.append(p)
total_km = sum(dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) / 1000
print(f"{len(pts)} points, {total_km:.1f} km, {args.speed:.0f} km/h, "
      f"~{total_km / args.speed * 60:.0f} min per lap, {'once' if args.once else 'looping'}", flush=True)

lap = 0
while True:
    lap += 1
    print(f"lap {lap} start", flush=True)
    seg, offset = 0, 0.0
    while seg < len(pts) - 1:
        t0 = time.time()
        a, b = pts[seg], pts[seg + 1]
        f = offset / dist(a, b)
        send(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, bearing(a, b), v)
        offset += v
        while seg < len(pts) - 1 and offset >= dist(pts[seg], pts[seg + 1]):
            offset -= dist(pts[seg], pts[seg + 1])
            seg += 1
        time.sleep(max(0.0, 1.0 - (time.time() - t0)))
    if args.once:
        end = pts[-1]
        send(end[0], end[1], bearing(pts[-2], end), 0.0)  # park at the destination
        print("arrived, stopped at route end", flush=True)
        break
