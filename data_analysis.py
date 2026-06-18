import json
import math
from collections import defaultdict
from datetime import datetime

# Haversine formula to calculate distance between two lat/lon points
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0 # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Locations
INDORE_LAT, INDORE_LON = 22.7196, 75.8577
PUNE_LAT, PUNE_LON = 18.5204, 73.8567
DHULE_LAT, DHULE_LON = 20.9042, 74.7749

print("Loading buses...")
valid_buses = set()
with open(r'c:\Users\PC\Desktop\DL\buses.txt', 'r') as f:
    lines = f.readlines()[1:]
    for line in lines:
        parts = line.strip().split('\t')
        if len(parts) >= 2:
            valid_buses.add(parts[1])

print("Loading journeys...")
with open(r'c:\Users\PC\Desktop\DL\fleet_db.journeys.json', 'r') as f:
    journeys_data = json.load(f)

journeys = {j['journey_id']: j for j in journeys_data if j.get('bus_no') in valid_buses}
print(f"Valid journeys: {len(journeys)}")

print("Loading trip points...")
with open(r'c:\Users\PC\Desktop\DL\fleet_db.trip_points.json', 'r') as f:
    trip_points = json.load(f)

journey_points = defaultdict(list)
for p in trip_points:
    jid = p.get('journey_id')
    if jid in journeys:
        journey_points[jid].append(p)

for jid in journey_points:
    journey_points[jid].sort(key=lambda x: x['timestamp'])

print("Data loaded. Analyzing...")

# 1. Detect routes and time to Dhule for Pune to Indore for bus MP09DL9990
# We use MP09DL9990 since it's "Bus 1" and matches "9990".
TARGET_BUS = "MP09DL9990"
dhule_times = []

for jid, points in journey_points.items():
    if not points: continue
    
    first_pt = points[0]
    last_pt = points[-1]
    
    dist_start_indore = haversine(first_pt['lat'], first_pt['lon'], INDORE_LAT, INDORE_LON)
    dist_start_pune = haversine(first_pt['lat'], first_pt['lon'], PUNE_LAT, PUNE_LON)
    
    route = "Unknown"
    if dist_start_indore < dist_start_pune:
        route = "Indore to Pune"
    else:
        route = "Pune to Indore"
    
    journeys[jid]['route'] = route
    
    if route == "Pune to Indore" and journeys[jid]['bus_no'] == TARGET_BUS:
        # Find time to reach Dhule
        start_ts = first_pt['timestamp']
        min_dist_dhule = float('inf')
        time_to_dhule = None
        
        for p in points:
            d = haversine(p['lat'], p['lon'], DHULE_LAT, DHULE_LON)
            if d < min_dist_dhule:
                min_dist_dhule = d
                time_to_dhule = p['timestamp'] - start_ts
                
        # If it passed reasonably close to Dhule (e.g. within 50km)
        if min_dist_dhule < 50 and time_to_dhule is not None:
            dhule_times.append(time_to_dhule)

if dhule_times:
    avg_dhule_time_hrs = (sum(dhule_times) / len(dhule_times)) / 3600
    print(f"1. Average time to reach Dhule for {TARGET_BUS} (Pune to Indore): {avg_dhule_time_hrs:.2f} hours (based on {len(dhule_times)} journeys)")
else:
    print(f"1. No valid Pune to Indore journeys found for {TARGET_BUS} passing near Dhule.")

# 2. Bus with maximum stoppage
bus_stoppage = defaultdict(int)
for jid, points in journey_points.items():
    bus_no = journeys[jid]['bus_no']
    # Stoppage = sum of time intervals where speed is 0
    stoppage_time = 0
    for i in range(1, len(points)):
        if points[i]['speed'] == 0:
            stoppage_time += (points[i]['timestamp'] - points[i-1]['timestamp'])
    bus_stoppage[bus_no] += stoppage_time

if bus_stoppage:
    max_bus = max(bus_stoppage, key=bus_stoppage.get)
    print(f"2. Bus with maximum stoppage: {max_bus} with {bus_stoppage[max_bus]/3600:.2f} hours")

# 3. Points on route with maximum delays
# We will bin coordinates (round to 2 decimal places ~ 1.1km precision)
delay_hotspots = defaultdict(int)
for jid, points in journey_points.items():
    for i in range(1, len(points)):
        # Consider speed < 10 km/h as delay, excluding very start and end (assume first/last 30 mins are terminal)
        p = points[i]
        if p['speed'] < 10:
            # Check if it's middle of journey
            time_from_start = p['timestamp'] - points[0]['timestamp']
            time_to_end = points[-1]['timestamp'] - p['timestamp']
            if time_from_start > 1800 and time_to_end > 1800:
                loc_key = (round(p['lat'], 2), round(p['lon'], 2))
                # Skip if near Indore or Pune
                if haversine(p['lat'], p['lon'], INDORE_LAT, INDORE_LON) > 30 and \
                   haversine(p['lat'], p['lon'], PUNE_LAT, PUNE_LON) > 30:
                    delay_hotspots[loc_key] += (p['timestamp'] - points[i-1]['timestamp'])

if delay_hotspots:
    top_hotspot = max(delay_hotspots, key=delay_hotspots.get)
    print(f"3. Maximum delay hotspot (lat, lon): {top_hotspot} with {delay_hotspots[top_hotspot]/3600:.2f} hours of accumulated delay across all buses")

# 4. Days in week which delayed most buses
# Analyze total journey duration vs day of week
day_durations = defaultdict(list)
for jid, points in journey_points.items():
    if len(points) < 2: continue
    start_ts = points[0]['timestamp']
    end_ts = points[-1]['timestamp']
    duration_hrs = (end_ts - start_ts) / 3600
    
    # Filter anomalous durations
    if 5 < duration_hrs < 30: 
        day_of_week = datetime.fromtimestamp(start_ts).strftime('%A')
        day_durations[day_of_week].append(duration_hrs)

print("4. Average journey duration by day of week:")
for day, durations in sorted(day_durations.items(), key=lambda x: sum(x[1])/len(x[1]) if x[1] else 0, reverse=True):
    avg_dur = sum(durations) / len(durations)
    print(f"   {day}: {avg_dur:.2f} hours ({len(durations)} trips)")

print("Done.")
