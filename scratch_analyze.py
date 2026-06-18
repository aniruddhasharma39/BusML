import json
import os
import time

start_time = time.time()
print("Loading buses.txt...")
valid_buses = set()
with open(r'c:\Users\PC\Desktop\DL\buses.txt', 'r') as f:
    lines = f.readlines()[1:] # skip header
    for line in lines:
        parts = line.strip().split('\t')
        if len(parts) >= 2:
            valid_buses.add(parts[1])

print(f"Valid buses count: {len(valid_buses)}")

print("Loading journeys...")
with open(r'c:\Users\PC\Desktop\DL\fleet_db.journeys.json', 'r') as f:
    journeys = json.load(f)

valid_journey_ids = set()
for j in journeys:
    if j.get('bus_no') in valid_buses:
        valid_journey_ids.add(j['journey_id'])

print(f"Valid journeys count: {len(valid_journey_ids)}")

print("Loading trip points...")
# We will use streaming or just json.load since 252MB is not too large for modern PCs (usually takes ~1GB RAM).
try:
    with open(r'c:\Users\PC\Desktop\DL\fleet_db.trip_points.json', 'r') as f:
        trip_points = json.load(f)
    print(f"Loaded {len(trip_points)} trip points.")
    
    # Filter trip points
    valid_points = [p for p in trip_points if p.get('journey_id') in valid_journey_ids]
    print(f"Valid trip points count: {len(valid_points)}")
except Exception as e:
    print(f"Error loading trip points: {e}")

print(f"Finished in {time.time() - start_time:.2f} seconds.")
