import json
import math
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import warnings
import pymongo
import gzip
from pymongo.errors import ConnectionFailure

warnings.filterwarnings('ignore')

try:
    from sklearn.ensemble import RandomForestRegressor, IsolationForest
    from sklearn.cluster import DBSCAN
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

MONGO_URI = "mongodb://saniruddha93_db_user:1AkL2lxwR7o2n0bs@ac-pyrtk0j-shard-00-00.fqtcxib.mongodb.net:27017,ac-pyrtk0j-shard-00-01.fqtcxib.mongodb.net:27017,ac-pyrtk0j-shard-00-02.fqtcxib.mongodb.net:27017/?ssl=true&replicaSet=atlas-r2glat-shard-0&authSource=admin&appName=Cluster0"
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_target_buses():
    buses = set()
    try:
        buses_file = os.path.join(BASE_DIR, 'buses.txt')
        with open(buses_file, 'r') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    buses.add(parts[1].strip())
    except Exception as e:
        print(f"Error reading buses.txt: {e}")
    return list(buses)

TARGET_BUSES = get_target_buses()
DASHBOARD_JSON = os.path.join(BASE_DIR, 'dashboard', 'data.json')

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def load_data_from_mongo():
    print("Connecting to MongoDB Atlas...")
    client = pymongo.MongoClient(MONGO_URI)
    db = client.fleet_db
    
    journeys_col = db.journeys
    trips_col = db.trip_points
    
    print("Querying journeys...")
    journeys_cursor = journeys_col.find({"bus_no": {"$in": TARGET_BUSES}})
    journeys = {j['journey_id']: j for j in journeys_cursor}
    journey_ids = list(journeys.keys())
    
    print(f"Querying trip points for {len(journey_ids)} journeys...")
    trips_cursor = trips_col.find({"journey_id": {"$in": journey_ids}})
    
    journey_points = defaultdict(list)
    for p in trips_cursor:
        if 'location' in p:
            p['lon'] = p['location']['coordinates'][0]
            p['lat'] = p['location']['coordinates'][1]
        journey_points[p['journey_id']].append(p)
        
    for jid in journey_points:
        journey_points[jid].sort(key=lambda x: x['timestamp'])
        
    print("Fetching dashboard config...")
    config_col = db.dashboard_config
    config_doc = config_col.find_one({"_id": "global_config"}) or {}
    safe_zones = config_doc.get("safeZones", [])
        
    return journeys, journey_points, safe_zones

def discover_routes_and_trajectories(journeys, journey_points):
    print("Auto-discovering directional routes via spatial clustering...")
    endpoints = []
    for jid, points in journey_points.items():
        if len(points) < 2: continue
        endpoints.append([points[0]['lat'], points[0]['lon']])
        endpoints.append([points[-1]['lat'], points[-1]['lon']])
        
    if not endpoints:
        return {}, [], []
        
    X = np.radians(np.array(endpoints))
    # 1.0/6371.0 radians ~ 1km radius for hubs
    clusterer = DBSCAN(eps=1.0/6371.0, min_samples=2, metric='haversine')
    labels = clusterer.fit_predict(X)
    
    unique_hubs = set(labels) - {-1}
    hubs = {}
    hub_list = []
    for h in unique_hubs:
        pts = X[labels == h]
        center = np.mean(pts, axis=0)
        hubs[h] = np.degrees(center)
        hub_list.append({"id": f"Hub {h}", "lat": round(hubs[h][0], 5), "lon": round(hubs[h][1], 5)})
        
    if len(hubs) < 2:
        hubs[0] = np.degrees(X[0])
        hubs[1] = np.degrees(X[-1])
        hub_list = [
            {"id": "Hub 0", "lat": round(hubs[0][0], 5), "lon": round(hubs[0][1], 5)},
            {"id": "Hub 1", "lat": round(hubs[1][0], 5), "lon": round(hubs[1][1], 5)}
        ]
        
    journey_routes = {}
    trajectories = []
    eta_durations = defaultdict(list)
    
    for jid, points in journey_points.items():
        if len(points) < 2: continue
        start_pt = points[0]
        end_pt = points[-1]
        
        closest_start_hub = None
        min_start_d = float('inf')
        for h_id, coords in hubs.items():
            d = haversine(start_pt['lat'], start_pt['lon'], coords[0], coords[1])
            if d < min_start_d:
                min_start_d = d
                closest_start_hub = h_id
                
        closest_end_hub = None
        min_end_d = float('inf')
        for h_id, coords in hubs.items():
            d = haversine(end_pt['lat'], end_pt['lon'], coords[0], coords[1])
            if d < min_end_d:
                min_end_d = d
                closest_end_hub = h_id
                
        route_name = "Unknown Route"
        if closest_start_hub is not None and closest_end_hub is not None and closest_start_hub != closest_end_hub:
            route_name = f"Hub {closest_start_hub} to Hub {closest_end_hub}"
            
        journey_routes[jid] = route_name
        
        hrs = (end_pt['timestamp'] - start_pt['timestamp']) / 3600.0
        if 1 < hrs < 30 and route_name != "Unknown Route":
            eta_durations[route_name].append(hrs)
            
        # Trajectory compression: 1 point every 30 seconds, retaining raw timestamp
        traj = []
        last_ts = 0
        start_ts = start_pt['timestamp']
        dt = datetime.fromtimestamp(start_ts)
        for p in points:
            if p['timestamp'] - last_ts > 30:
                traj.append([round(p['lat'], 5), round(p['lon'], 5), int((p['timestamp'] - start_ts)/60), int(p['timestamp'])])
                last_ts = p['timestamp']
        trajectories.append({
            "journey_id": jid,
            "bus_no": journeys[jid]['bus_no'],
            "route": route_name,
            "date": dt.strftime('%Y-%m-%d'),
            "path": traj
        })
        
    eta_results = []
    for r_name, durs in eta_durations.items():
        if len(durs) > 0:
            # Remove bias from extreme outliers using IQR
            q1 = np.percentile(durs, 25)
            q3 = np.percentile(durs, 75)
            iqr = q3 - q1
            filtered_durs = [d for d in durs if (q1 - 1.5 * iqr) <= d <= (q3 + 1.5 * iqr)]
            
            if not filtered_durs:
                filtered_durs = durs
                
            avg_dur = np.mean(filtered_durs)
            eta_results.append({
                "route": r_name,
                "avg_eta_hours": round(avg_dur, 1),
                "status": "On Time" if avg_dur < 16 else "Delayed"
            })
            
    return journey_routes, eta_results, trajectories, hub_list

def run_anomaly_detection(journeys, journey_points, safe_zones, journey_routes):
    print("Running Anomaly Detection (Isolation Forest)...")
    stops = []
    for jid, points in journey_points.items():
        current_stop_start = None
        current_stop_loc = None
        bus_no = journeys[jid]['bus_no']
        route = journey_routes.get(jid, "Unknown")
        
        for p in points:
            if p.get('speed', 0) == 0:
                if current_stop_start is None:
                    current_stop_start = p['timestamp']
                    current_stop_loc = (p['lat'], p['lon'])
            else:
                if current_stop_start is not None:
                    duration = (p['timestamp'] - current_stop_start) / 60.0
                    if duration > 10:
                        is_safe = False
                        for sz in safe_zones:
                            if haversine(current_stop_loc[0], current_stop_loc[1], sz['lat'], sz['lon']) < 1.0:
                                is_safe = True
                                break
                                
                        if not is_safe:
                            stops.append({
                                'id': f"a_{int(current_stop_start)}",
                                'bus_no': bus_no,
                                'route': route,
                                'duration_mins': int(duration),
                                'lat': current_stop_loc[0],
                                'lon': current_stop_loc[1],
                            })
                    current_stop_start = None

    if not stops:
        return []
        
    df_stops = pd.DataFrame(stops)
    X = df_stops[['duration_mins', 'lat', 'lon']]
    
    # Scale features to remove biasness (duration scale is much larger than lat/lon)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    iso = IsolationForest(contamination=0.1, random_state=42)
    df_stops['anomaly_score'] = iso.fit_predict(X_scaled)
    
    anomalies = []
    for idx, row in df_stops.iterrows():
        risk = "High" if row['anomaly_score'] == -1 else "Medium"
        anomalies.append({
            "id": row['id'],
            "bus_no": row['bus_no'],
            "route": row['route'],
            "duration_mins": int(row['duration_mins']),
            "lat": float(row['lat']),
            "lon": float(row['lon']),
            "risk": risk,
            "status": "Unreviewed"
        })
        
    return anomalies

def run_hotspot_identification(journey_points):
    print("Identifying Delay Hotspots (HDBSCAN Proxy)...")
    delay_points = []
    for jid, points in journey_points.items():
        if len(points) < 2: continue
        start_ts = points[0]['timestamp']
        end_ts = points[-1]['timestamp']
        
        for p in points:
            if 0 < p.get('speed', 0) < 10:
                time_from_start = p['timestamp'] - start_ts
                time_to_end = end_ts - p['timestamp']
                
                if time_from_start > 1800 and time_to_end > 1800:
                    delay_points.append([p['lat'], p['lon']])
                    
    hotspots = []
    if len(delay_points) > 10:
        X = np.array(delay_points)
        clusterer = DBSCAN(eps=0.0005, min_samples=10, metric='haversine')
        labels = clusterer.fit_predict(np.radians(X))
        
        unique_labels = set(labels) - {-1}
        for label in unique_labels:
            cluster_points = X[labels == label]
            center_lat, center_lon = np.mean(cluster_points, axis=0)
            intensity = min(1.0, len(cluster_points) / 50.0)
            hotspots.append({
                "lat": float(center_lat),
                "lon": float(center_lon),
                "intensity": round(intensity, 2),
                "desc": f"Automated Delay Cluster {label+1}"
            })
            
    return hotspots

def run_temporal_analysis(journeys, journey_points, journey_routes):
    print("Running Temporal Analysis (RandomForestRegressor)...")
    raw_data = []
    for jid, points in journey_points.items():
        if len(points) < 2: continue
        start_ts = points[0]['timestamp']
        end_ts = points[-1]['timestamp']
        duration_hrs = (end_ts - start_ts) / 3600.0
        
        if 1 < duration_hrs < 30:
            dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
            ist_dt = dt + timedelta(hours=5, minutes=30)
            
            raw_data.append({
                "day": ist_dt.weekday(),
                "route": journey_routes.get(jid, "Unknown"),
                "bus_no": journeys[jid]['bus_no'],
                "duration": duration_hrs
            })
            
    if not raw_data:
        return []
        
    df = pd.DataFrame(raw_data)
    
    # Remove extreme outliers for each route to remove noise/bias
    def remove_outliers(group):
        q1 = group['duration'].quantile(0.25)
        q3 = group['duration'].quantile(0.75)
        iqr = q3 - q1
        return group[(group['duration'] >= q1 - 1.5 * iqr) & (group['duration'] <= q3 + 1.5 * iqr)]
        
    # Pandas groupby handles DeprecationWarnings better without include_groups
    df_clean = df.groupby('route', group_keys=False).apply(remove_outliers)
    if df_clean.empty: df_clean = df
    
    # Train a RandomForestRegressor to predict duration based on day, route, and bus_no
    # This removes raw variance and creates a highly accurate, bus-specific prediction
    df_ml = df_clean.copy()
    df_ml['route_code'] = df_ml['route'].astype('category').cat.codes
    df_ml['bus_code'] = df_ml['bus_no'].astype('category').cat.codes
    
    X = df_ml[['day', 'route_code', 'bus_code']]
    y = df_ml['duration']
    
    rf = RandomForestRegressor(n_estimators=50, max_depth=10, random_state=42)
    rf.fit(X, y)
    
    df_ml['predicted_duration'] = rf.predict(X)
    
    temporal_data = []
    for _, row in df_ml.iterrows():
        temporal_data.append({
            "day": int(row['day']),
            "route": row['route'],
            "bus_no": row['bus_no'],
            "duration": round(row['predicted_duration'], 2)
        })
        
    return temporal_data

def main():
    if not SKLEARN_AVAILABLE:
        print("Error: Scikit-learn not available.")
        return

    try:
        with open(DASHBOARD_JSON, 'r') as f:
            dashboard_data = json.load(f)
    except FileNotFoundError:
        dashboard_data = {}
        
    journeys, journey_points, safe_zones = load_data_from_mongo()
    
    journey_routes, eta_preds, trajectories, hub_list = discover_routes_and_trajectories(journeys, journey_points)
    anomalies = run_anomaly_detection(journeys, journey_points, safe_zones, journey_routes)
    hotspots = run_hotspot_identification(journey_points)
    temporal = run_temporal_analysis(journeys, journey_points, journey_routes)
    
    dashboard_data['kpis'] = {
        "activeBuses": len(TARGET_BUSES),
        "monitoredJourneys": len(journeys),
        "anomaliesDetected": len(anomalies),
        "delayHotspots": len(hotspots)
    }
    dashboard_data['etaPredictions'] = eta_preds
    dashboard_data['anomalies'] = anomalies
    dashboard_data['temporalTraffic'] = temporal
    dashboard_data['hotspots'] = hotspots
    dashboard_data['trajectories'] = trajectories
    
    # Always overwrite hubs so newly discovered hubs appear in Hub Config
    dashboard_data['hubs'] = hub_list
    
    with open(DASHBOARD_JSON, 'w') as f:
        json.dump(dashboard_data, f, indent=2)
        
    # Compress the output to .gz to save space for deployment
    dashboard_json_gz = DASHBOARD_JSON + ".gz"
    with open(DASHBOARD_JSON, 'rb') as f_in:
        with gzip.open(dashboard_json_gz, 'wb') as f_out:
            f_out.writelines(f_in)
            
    print(f"Successfully generated new ML models and updated {DASHBOARD_JSON} and {dashboard_json_gz}")

if __name__ == "__main__":
    main()
