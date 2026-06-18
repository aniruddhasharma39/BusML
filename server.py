import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pymongo

app = Flask(__name__, static_folder='dashboard')
CORS(app)

PORT = int(os.environ.get("PORT", 8080))
MONGO_URI = "mongodb://saniruddha93_db_user:1AkL2lxwR7o2n0bs@ac-pyrtk0j-shard-00-00.fqtcxib.mongodb.net:27017,ac-pyrtk0j-shard-00-01.fqtcxib.mongodb.net:27017,ac-pyrtk0j-shard-00-02.fqtcxib.mongodb.net:27017/?ssl=true&replicaSet=atlas-r2glat-shard-0&authSource=admin&appName=Cluster0"

try:
    client = pymongo.MongoClient(MONGO_URI)
    db = client.fleet_db
    config_col = db.dashboard_config
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    config_col = None

# Ensure a default config document exists
def get_config_doc():
    if config_col is None:
        return {"hubNames": {}, "ignoredRoutes": {}, "ignoredHubs": [], "safeZones": []}
    doc = config_col.find_one({"_id": "global_config"})
    if not doc:
        doc = {
            "_id": "global_config",
            "hubNames": {},
            "ignoredRoutes": {},
            "ignoredHubs": [],
            "safeZones": []
        }
        config_col.insert_one(doc)
    return doc

@app.route('/api/config', methods=['GET'])
def get_config():
    doc = get_config_doc()
    return jsonify(doc)

@app.route('/api/config', methods=['POST'])
def update_config():
    if config_col is None:
        return jsonify({"success": False, "error": "No DB connection"}), 500
    
    data = request.json
    update_fields = {}
    if "hubNames" in data: update_fields["hubNames"] = data["hubNames"]
    if "ignoredRoutes" in data: update_fields["ignoredRoutes"] = data["ignoredRoutes"]
    if "ignoredHubs" in data: update_fields["ignoredHubs"] = data["ignoredHubs"]
    if "safeZones" in data: update_fields["safeZones"] = data["safeZones"]
    
    if update_fields:
        config_col.update_one({"_id": "global_config"}, {"$set": update_fields}, upsert=True)
    
    return jsonify({"success": True})

@app.route('/', defaults={'path': 'index.html'})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
