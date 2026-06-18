import json
import pymongo
from pymongo.errors import ConnectionFailure

MONGO_URI = "mongodb://saniruddha93_db_user:1AkL2lxwR7o2n0bs@ac-pyrtk0j-shard-00-00.fqtcxib.mongodb.net:27017,ac-pyrtk0j-shard-00-01.fqtcxib.mongodb.net:27017,ac-pyrtk0j-shard-00-02.fqtcxib.mongodb.net:27017/?ssl=true&replicaSet=atlas-r2glat-shard-0&authSource=admin&appName=Cluster0"
def get_target_buses():
    buses = set()
    try:
        with open(r'c:\Users\PC\Desktop\DL\buses.txt', 'r') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    buses.add(parts[1].strip())
    except Exception as e:
        print(f"Error reading buses.txt: {e}")
    return list(buses)

TARGET_BUSES = get_target_buses()

def main():
    print("Connecting to MongoDB Atlas Cluster...")
    try:
        client = pymongo.MongoClient(MONGO_URI)
        client.admin.command('ping')
        print("Connected to MongoDB successfully!")
    except ConnectionFailure as e:
        print(f"Failed to connect to MongoDB: {e}")
        return

    db = client.fleet_db
    journeys_col = db.journeys
    trips_col = db.trip_points

    print(f"Clearing existing data for buses {TARGET_BUSES}...")
    journeys_col.delete_many({"bus_no": {"$in": list(TARGET_BUSES)}})
    
    print("Loading journeys from JSON...")
    with open(r'c:\Users\PC\Desktop\DL\fleet_db.journeys.json', 'r') as f:
        all_journeys = json.load(f)
    
    target_journeys = []
    for j in all_journeys:
        if j.get('bus_no') in TARGET_BUSES:
            if '_id' in j:
                del j['_id']
            target_journeys.append(j)
            
    journey_ids = {j['journey_id'] for j in target_journeys}
    print(f"Found {len(target_journeys)} journeys for target buses.")
    
    if target_journeys:
        journeys_col.insert_many(target_journeys)
    
    if journey_ids:
        trips_col.delete_many({"journey_id": {"$in": list(journey_ids)}})

    print("Loading trip points (this might take a moment due to 250MB+ file size)...")
    with open(r'c:\Users\PC\Desktop\DL\fleet_db.trip_points.json', 'r') as f:
        all_trips = json.load(f)
        
    target_trips = []
    for t in all_trips:
        if t.get('journey_id') in journey_ids:
            if '_id' in t:
                del t['_id']
            # Transform to GeoJSON for 2dsphere indexing
            lat = t.get('lat')
            lon = t.get('lon')
            if lat is not None and lon is not None:
                t['location'] = {
                    "type": "Point",
                    "coordinates": [lon, lat] # GeoJSON standard is [longitude, latitude]
                }
            target_trips.append(t)
            
    print(f"Found {len(target_trips)} trip points for the targeted journeys.")
    
    if target_trips:
        print("Uploading trip points to Atlas...")
        trips_col.insert_many(target_trips)
        
    print("Creating indexes (2dsphere on location, ascending on journey_id)...")
    trips_col.create_index([("location", pymongo.GEOSPHERE)])
    trips_col.create_index([("journey_id", pymongo.ASCENDING), ("timestamp", pymongo.ASCENDING)])
    journeys_col.create_index([("bus_no", pymongo.ASCENDING)])
    
    print("Data upload and spatial indexing successfully completed!")

if __name__ == "__main__":
    main()
