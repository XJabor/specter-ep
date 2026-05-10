from flask import Blueprint, jsonify
import json
from config import LIBRARY_DIR

systems_api = Blueprint('systems_api', __name__)

LIBRARY_PATH = LIBRARY_DIR / 'core_systems.json'

@systems_api.route('/systems', methods=['GET'])
def get_systems():
    """Returns the list of all pre-configured RF systems."""
    if not LIBRARY_PATH.exists():
        return jsonify({"error": "Library file not found"}), 404
        
    with open(LIBRARY_PATH, 'r') as f:
        data = json.load(f)
    return jsonify(data)
