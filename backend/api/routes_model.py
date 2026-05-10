from flask import Blueprint, request, jsonify
from config import DEFAULT_TERRAIN_PATH, DEFAULT_VERTICAL_CAP_M
from engine.terrain import (
    check_line_of_sight,
    extract_elevation_grid,
    get_elevation_profiles_batch,
    get_terrain_status,
)
from engine.propagation import (
    calculate_eirp_dbm,
    calculate_fspl_grid,
    calculate_path_loss_details,
    calculate_path_loss,
    calculate_sensing_distance,
    destination_point,
    directional_gain_db,
)

# Create a Blueprint for routing
model_api = Blueprint('model_api', __name__)


def _walk_profile_to_range(profile, freq_mhz, terrain, eirp_dbm, rx_gain_dbi,
                           rx_sensitivity_dbm, tx_height_m, rx_height_m):
    max_loss = eirp_dbm + rx_gain_dbi - rx_sensitivity_dbm
    prev_d = 0.0
    prev_pl = 0.0
    last_details = None

    for i in range(1, len(profile)):
        d_i = profile[i]["distance_km"]
        if d_i <= 0:
            continue

        sub = profile[:i + 1]
        h_tx = sub[0]["elevation_m"] + tx_height_m
        h_rx = sub[-1]["elevation_m"] + rx_height_m
        terrain_blocked = any(
            pt["elevation_m"] > h_tx + (h_rx - h_tx) * (pt["distance_km"] / d_i) + 1.0
            for pt in sub[1:-1]
            if 0 < pt["distance_km"] < d_i
        )

        if terrain_blocked:
            los = check_line_of_sight(sub, freq_mhz, tx_height_m, rx_height_m)
            diff_db = los["diffraction_loss_db"]
            is_los = los["is_los"]
        else:
            diff_db = 0.0
            is_los = True

        details = calculate_path_loss_details(
            d_i,
            freq_mhz,
            terrain,
            diff_db,
            tx_height_m,
            rx_height_m,
            is_los,
        )
        path_loss = details["path_loss_db"]
        details.update({
            "max_obstruction_m": los["max_obstruction_m"] if terrain_blocked else 0.0,
            "obstruction_distance_km": los["obstruction_distance_km"] if terrain_blocked else 0.0,
        })
        if path_loss > max_loss:
            if prev_d <= 0:
                details["range_km"] = max(0.05, d_i / 2.0)
                return details
            frac = (max_loss - prev_pl) / max(path_loss - prev_pl, 1e-9)
            details["range_km"] = prev_d + max(0.0, min(1.0, frac)) * (d_i - prev_d)
            return details

        prev_pl = path_loss
        prev_d = d_i
        last_details = details

    if last_details is None:
        last_details = calculate_path_loss_details(
            profile[-1]["distance_km"],
            freq_mhz,
            terrain,
            0.0,
            tx_height_m,
            rx_height_m,
            True,
        )
    last_details["range_km"] = profile[-1]["distance_km"]
    return last_details


def _profile_source_counts(profiles):
    counts = {}
    for profile in profiles:
        for point in profile:
            source = point.get("elevation_source", "unknown")
            counts[source] = counts.get(source, 0) + 1
    return counts

@model_api.route('/calculate', methods=['POST'])
def calculate_propagation():
    """
    Expects a JSON payload:
    {
        "tx_lat": 34.05,
        "tx_lon": -118.24,
        "radius_km": 10,
        "freq_mhz": 300,
        "tx_power_dbm": 45
    }
    """
    try:
        data = request.get_json()

        # 1. Extract user inputs
        tx_lat = float(data.get('tx_lat'))
        tx_lon = float(data.get('tx_lon'))
        radius_km = float(data.get('radius_km', 10)) # Default to 10km if not provided
        freq_mhz = float(data.get('freq_mhz'))
        tx_power_dbm = float(data.get('tx_power_dbm'))

        # 2. Trigger the Engine (Terrain Extraction)
        lats, lons, elev_matrix = extract_elevation_grid(DEFAULT_TERRAIN_PATH, tx_lat, tx_lon, radius_km)

        # 3. Trigger the Engine (Math)
        heatmap_data = calculate_fspl_grid(
            tx_lat, tx_lon, freq_mhz, tx_power_dbm, lats, lons, elev_matrix
        )

        # 4. Return the massive JSON array to Deck.gl
        return jsonify({
            "status": "success",
            "point_count": len(heatmap_data),
            "data": heatmap_data
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@model_api.route('/footprint', methods=['POST'])
def calculate_footprint():
    """
    Terrain-shaped EMS footprint for a single radio/SATCOM emitter.
    Returns polygon_points as [lat, lon] vertices and optional vertical beam metadata.
    """
    try:
        data = request.get_json() or {}

        tx_lat = float(data["tx_lat"])
        tx_lon = float(data["tx_lon"])
        freq_mhz = float(data.get("freq_mhz", 300))
        tx_power_dbm = float(data.get("tx_power_dbm", 37))
        antenna_gain_dbi = float(data.get("antenna_gain_dbi", 0))
        cable_loss_db = float(data.get("cable_loss_db", 0))
        rx_gain_dbi = float(data.get("rx_gain_dbi", 0))
        rx_sensitivity_dbm = float(data.get("rx_sensitivity_dbm", -100))
        terrain = data.get("terrain", "rural")
        tx_height_m = float(data.get("tx_height_m", 2.0))
        rx_height_m = float(data.get("rx_height_m", 2.0))
        antenna_type = data.get("antenna_type", "omni")
        azimuth_deg = float(data.get("azimuth_deg", 0))
        elevation_deg = float(data.get("elevation_deg", 45))
        beamwidth_deg = float(data.get("beamwidth_deg", 90))
        num_bearings = int(data.get("num_bearings", 72))
        num_samples = int(data.get("num_samples", 25))
        vertical_cap_m = float(data.get("vertical_cap_m", DEFAULT_VERTICAL_CAP_M))

        if freq_mhz <= 0:
            return jsonify({"status": "error", "message": "freq_mhz must be greater than zero."}), 400
        if not (-90 <= tx_lat <= 90) or not (-180 <= tx_lon <= 180):
            return jsonify({"status": "error", "message": "Invalid transmitter coordinates."}), 400
        if not (8 <= num_bearings <= 360):
            return jsonify({"status": "error", "message": "num_bearings must be between 8 and 360."}), 400

        def eirp_at_bearing(bearing):
            gain = antenna_gain_dbi
            if antenna_type in ("directional", "satcom"):
                gain = directional_gain_db(antenna_gain_dbi, azimuth_deg, bearing, beamwidth_deg)
            return calculate_eirp_dbm(tx_power_dbm, gain, cable_loss_db)

        peak_bearing = azimuth_deg if antenna_type in ("directional", "satcom") else 0
        peak_eirp = eirp_at_bearing(peak_bearing)
        base_range_km = calculate_sensing_distance(
            peak_eirp,
            freq_mhz,
            terrain,
            rx_gain_dbi,
            rx_sensitivity_dbm,
            tx_height_m=tx_height_m,
            rx_height_m=rx_height_m,
            is_los=True,
        )
        unconstrained_proj_range_km = max(
            base_range_km,
            calculate_sensing_distance(
                peak_eirp,
                freq_mhz,
                terrain,
                rx_gain_dbi,
                rx_sensitivity_dbm,
                tx_height_m=tx_height_m,
                rx_height_m=rx_height_m,
                is_los=False,
            ),
        )
        max_radius_km = data.get("max_radius_km")
        proj_range_km = unconstrained_proj_range_km
        clipped_by_request = False
        if max_radius_km is not None:
            max_radius_km = float(max_radius_km)
            clipped_by_request = max_radius_km < proj_range_km
            proj_range_km = min(max_radius_km, proj_range_km)

        bearings = [360.0 * i / num_bearings for i in range(num_bearings)]
        paths = []
        for bearing in bearings:
            end_lat, end_lon = destination_point(tx_lat, tx_lon, bearing, proj_range_km)
            paths.append((tx_lat, tx_lon, end_lat, end_lon))

        profiles = get_elevation_profiles_batch(paths, num_samples=num_samples)
        polygon_points = []
        sectors = []
        for bearing, profile in zip(bearings, profiles):
            eirp = eirp_at_bearing(bearing)
            sector_details = _walk_profile_to_range(
                profile,
                freq_mhz,
                terrain,
                eirp,
                rx_gain_dbi,
                rx_sensitivity_dbm,
                tx_height_m,
                rx_height_m,
            )
            range_km = sector_details["range_km"]
            range_km = max(range_km, 0.05)
            pt_lat, pt_lon = destination_point(tx_lat, tx_lon, bearing, range_km)
            polygon_points.append([pt_lat, pt_lon])
            sectors.append({
                "bearing_deg": round(bearing, 1),
                "range_km": round(range_km, 3),
                "eirp_dbm": eirp,
                "model": sector_details["model"],
                "is_los": sector_details["is_los"],
                "diffraction_loss_db": sector_details["diffraction_loss_db"],
                "path_loss_db": sector_details["path_loss_db"],
                "max_obstruction_m": sector_details.get("max_obstruction_m", 0.0),
                "obstruction_distance_km": sector_details.get("obstruction_distance_km", 0.0),
            })

        vertical_beam = None
        if antenna_type in ("directional", "satcom"):
            vertical_beam = {
                "origin": [tx_lat, tx_lon, tx_height_m],
                "azimuth_deg": azimuth_deg,
                "elevation_deg": elevation_deg,
                "beamwidth_deg": beamwidth_deg,
                "cap_m_agl": vertical_cap_m,
            }

        ranges = [sector["range_km"] for sector in sectors]
        source_counts = _profile_source_counts(profiles)
        terrain_status = get_terrain_status()
        warnings = []
        warnings.extend(terrain_status.get("warnings", []))
        if source_counts.get("fallback_zero"):
            warnings.append("Some terrain samples were unavailable and treated as 0 m elevation.")
        if source_counts.get("online"):
            warnings.append("Some terrain samples came from the online elevation fallback.")
        if clipped_by_request:
            warnings.append(f"Projection range clipped to requested max_radius_km={max_radius_km}.")

        return jsonify({
            "status": "success",
            "base_range_km": base_range_km,
            "unconstrained_projection_range_km": round(unconstrained_proj_range_km, 3),
            "projection_range_km": round(proj_range_km, 3),
            "polygon_points": polygon_points,
            "sectors": sectors,
            "summary": {
                "min_range_km": min(ranges) if ranges else 0,
                "max_range_km": max(ranges) if ranges else 0,
                "avg_range_km": round(sum(ranges) / len(ranges), 3) if ranges else 0,
                "los_sector_count": sum(1 for sector in sectors if sector["is_los"]),
                "nlos_sector_count": sum(1 for sector in sectors if not sector["is_los"]),
                "model_counts": {
                    model: sum(1 for sector in sectors if sector["model"] == model)
                    for model in sorted({sector["model"] for sector in sectors})
                },
            },
            "terrain": {
                "source_counts": source_counts,
                "path": terrain_status["path"],
                "elevation_source_count": terrain_status["elevation_source_count"],
            },
            "warnings": warnings,
            "vertical_beam": vertical_beam,
        }), 200

    except KeyError as e:
        return jsonify({"status": "error", "message": f"Missing required field: {e.args[0]}"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
