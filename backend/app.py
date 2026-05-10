from pathlib import Path
import json

from flask import Flask, Response, jsonify, send_from_directory
from flask_cors import CORS
from config import (
    APP_HOST,
    APP_PORT,
    DEFAULT_MAP_CENTER,
    DEFAULT_TERRAIN_PATH,
    DEFAULT_VERTICAL_CAP_M,
    ENABLE_ONLINE_ELEVATION,
    MAPBOX_TOKEN,
)

# Import the model routes we wrote earlier
from api.routes_model import model_api
# Import the new systems library routes
from api.routes_systems import systems_api
from engine.terrain import get_terrain_status, scan_terrain_path

def create_app():
    app = Flask(__name__)
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    
    # Enable CORS so your Deck.gl frontend can talk to this API
    CORS(app)

    # Register Blueprints
    # This mounts your routes at specific URL prefixes
    app.register_blueprint(model_api, url_prefix='/api/v1')
    app.register_blueprint(systems_api, url_prefix='/api/v1')

    @app.route('/health', methods=['GET'])
    def health_check():
        return jsonify({
            "status": "online",
            "project": "Specter-EP",
            "modules": ["propagation_engine", "systems_library"]
        }), 200

    @app.route('/api/v1/config', methods=['GET'])
    def runtime_config():
        terrain_status = get_terrain_status()
        return jsonify({
            "status": "success",
            "terrain_path": terrain_status["path"],
            "terrain": terrain_status,
            "online_elevation_enabled": ENABLE_ONLINE_ELEVATION,
            "default_map_center": DEFAULT_MAP_CENTER,
            "vertical_cap_m": DEFAULT_VERTICAL_CAP_M,
            "port": APP_PORT,
        }), 200

    @app.route('/app-config.js', methods=['GET'])
    def frontend_config():
        payload = {
            "mapboxToken": MAPBOX_TOKEN,
        }
        return Response(
            f"window.SPECTER_CONFIG = {json.dumps(payload)};\n",
            mimetype='application/javascript',
        )

    @app.route('/api/v1/terrain/status', methods=['GET'])
    def terrain_status():
        return jsonify({
            "status": "success",
            "terrain": get_terrain_status(),
            "online_elevation_enabled": ENABLE_ONLINE_ELEVATION,
        }), 200

    @app.route('/api/v1/terrain/source', methods=['POST'])
    def set_terrain_source():
        from flask import request

        data = request.get_json() or {}
        path = str(data.get("path", "")).strip()
        if not path:
            return jsonify({"status": "error", "message": "Path is required."}), 400
        terrain_status = scan_terrain_path(path)
        status_code = 200 if terrain_status["exists"] else 400
        return jsonify({
            "status": "success" if terrain_status["exists"] else "error",
            "terrain": terrain_status,
            "online_elevation_enabled": ENABLE_ONLINE_ELEVATION,
        }), status_code

    @app.route('/', methods=['GET'])
    def index():
        return send_from_directory(frontend_dir, 'index.html')

    @app.route('/<path:path>', methods=['GET'])
    def frontend_assets(path):
        return send_from_directory(frontend_dir, path)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host=APP_HOST, port=APP_PORT, debug=True)
