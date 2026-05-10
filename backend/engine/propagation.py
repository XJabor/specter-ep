import math

import numpy as np

_EGLI_K = 47.39
_RE_EFF_KM = 8500.0


def haversine_km(lat1, lon1, lat2, lon2):
    radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def haversine_vectorized(lat1, lon1, lat2_matrix, lon2_matrix):
    """Calculate great-circle distance from a point to a matrix, in km."""
    radius_km = 6371.0
    lat1_rad = np.radians(lat1)
    lon1_rad = np.radians(lon1)
    lat2_rad = np.radians(lat2_matrix)
    lon2_rad = np.radians(lon2_matrix)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2) ** 2
    )
    return radius_km * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def destination_point(lat, lon, bearing_deg, distance_km):
    radius_km = 6371.0
    d = distance_km / radius_km
    brng = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(d)
        + math.cos(lat1) * math.sin(d) * math.cos(brng)
    )
    lon2 = lon1 + math.atan2(
        math.sin(brng) * math.sin(d) * math.cos(lat1),
        math.cos(d) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lon2)


def bearing_deg(lat1, lon1, lat2, lon2):
    lat1r = math.radians(lat1)
    lat2r = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(lat2r)
    y = (
        math.cos(lat1r) * math.sin(lat2r)
        - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon)
    )
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def directional_gain_db(peak_gain_dbi, boresight_deg, target_bearing_deg, beamwidth_deg):
    if beamwidth_deg <= 0:
        return peak_gain_dbi
    delta = (target_bearing_deg - boresight_deg + 180) % 360 - 180
    rolloff = min(12.0 * (delta / beamwidth_deg) ** 2, 20.0)
    return peak_gain_dbi - rolloff


def _cost231_valid(frequency_mhz, tx_height_m):
    return frequency_mhz >= 150.0 and tx_height_m >= 30.0


def _radio_horizon_km(ht_m, hr_m):
    return (
        math.sqrt(2.0 * _RE_EFF_KM * max(1.0, ht_m) / 1000.0)
        + math.sqrt(2.0 * _RE_EFF_KM * max(1.0, hr_m) / 1000.0)
    )


def _terrain_correction_db(terrain_type):
    terrain = terrain_type.strip().lower()
    if "dense" in terrain or "urban" in terrain:
        return 20.0
    if "suburb" in terrain or "light" in terrain:
        return 8.0
    return 0.0


def _fspl(distance_km, frequency_mhz):
    return 20.0 * math.log10(max(0.001, distance_km)) + 20.0 * math.log10(frequency_mhz) + 32.44


def _egli_path_loss(distance_km, frequency_mhz, tx_height_m, rx_height_m, terrain_type):
    ht = max(1.0, tx_height_m)
    hr = max(1.0, rx_height_m)
    loss = (
        20.0 * math.log10(frequency_mhz)
        + 40.0 * math.log10(max(0.001, distance_km))
        - 20.0 * math.log10(ht)
        - 20.0 * math.log10(hr)
        + _EGLI_K
        + _terrain_correction_db(terrain_type)
    )
    return max(_fspl(distance_km, frequency_mhz), loss)


def _cost231_hata_path_loss(distance_km, frequency_mhz, terrain_type, tx_height_m, rx_height_m):
    f = max(150.0, min(2000.0, frequency_mhz))
    h_b = max(2.0, tx_height_m)
    h_m = max(1.0, rx_height_m)
    a_hm = (1.1 * math.log10(f) - 0.7) * h_m - (1.56 * math.log10(f) - 0.8)
    c_m = 3.0 if "dense" in terrain_type.lower() else 0.0
    a = 46.3 + 33.9 * math.log10(f) - 13.82 * math.log10(h_b) - a_hm + c_m
    b = 44.9 - 6.55 * math.log10(h_b)
    urban_loss = a + b * math.log10(max(0.1, distance_km))
    terrain = terrain_type.strip().lower()
    if "rural" in terrain or "open" in terrain or "free" in terrain:
        loss = urban_loss - 4.78 * math.log10(f) ** 2 + 18.33 * math.log10(f) - 40.94
    elif "suburb" in terrain or "light" in terrain:
        loss = urban_loss - 2.0 * (math.log10(f / 28.0)) ** 2 - 5.4
    else:
        loss = urban_loss
    return max(_fspl(distance_km, f), loss)


def _two_ray_path_loss(distance_km, frequency_mhz, tx_height_m, rx_height_m):
    ht = max(1.0, tx_height_m)
    hr = max(1.0, rx_height_m)
    d_m = max(1.0, distance_km * 1000.0)
    loss = 40.0 * math.log10(d_m) - 20.0 * math.log10(ht) - 20.0 * math.log10(hr)
    return max(_fspl(distance_km, frequency_mhz), loss)


def _shf_path_loss(distance_km, frequency_mhz, terrain_type):
    terrain = terrain_type.strip().lower()
    f_ghz = frequency_mhz / 1000.0
    if "suburb" in terrain or "light" in terrain:
        clutter = 2.0 * f_ghz * distance_km
    elif "dense" in terrain or "urban" in terrain:
        clutter = 5.0 * f_ghz * distance_km
    else:
        clutter = 0.0
    return _fspl(distance_km, frequency_mhz) + clutter


def _shf_near_ground_penalty_db(tx_height_m, rx_height_m, terrain_type):
    if min(tx_height_m, rx_height_m) >= 5.0:
        return 0.0
    terrain = terrain_type.strip().lower()
    if "dense" in terrain or "urban" in terrain:
        return 10.0
    if "suburb" in terrain or "light" in terrain:
        return 5.0
    return 0.0


def classify_path_loss_model(frequency_mhz, terrain_type="free space", tx_height_m=0.0, is_los=False):
    is_free_space = "free space" in terrain_type.lower() or "air" in terrain_type.lower()
    hata_ok = _cost231_valid(frequency_mhz, tx_height_m)
    upper_uhf = frequency_mhz >= 1000.0 and not hata_ok

    if frequency_mhz > 2000.0:
        return "SHF FSPL + clutter"
    if is_los:
        if is_free_space:
            return "FSPL"
        if upper_uhf:
            return "Upper-UHF FSPL + terrain correction"
        if hata_ok:
            return "Two-Ray Ground Reflection"
        return "Egli"
    if is_free_space:
        return "FSPL"
    if upper_uhf:
        return "Upper-UHF FSPL + terrain correction"
    if hata_ok:
        return "COST-231 Hata"
    return "Egli"


def calculate_path_loss(
    distance_km,
    frequency_mhz,
    terrain_type="free space",
    diffraction_loss_db=0.0,
    tx_height_m=0.0,
    rx_height_m=0.0,
    is_los=False,
):
    if distance_km <= 0:
        return 0.0

    is_free_space = "free space" in terrain_type.lower() or "air" in terrain_type.lower()
    hata_ok = _cost231_valid(frequency_mhz, tx_height_m)
    upper_uhf = frequency_mhz >= 1000.0 and not hata_ok

    if frequency_mhz > 2000.0:
        loss = (
            _shf_path_loss(distance_km, frequency_mhz, terrain_type)
            + _shf_near_ground_penalty_db(tx_height_m, rx_height_m, terrain_type)
        )
        if not is_los:
            loss += diffraction_loss_db
        return round(loss, 2)

    if is_los:
        if is_free_space or upper_uhf:
            loss = _fspl(distance_km, frequency_mhz)
            if upper_uhf and not is_free_space:
                loss += _terrain_correction_db(terrain_type)
        elif hata_ok:
            loss = _two_ray_path_loss(distance_km, frequency_mhz, tx_height_m, rx_height_m)
        else:
            loss = _egli_path_loss(distance_km, frequency_mhz, tx_height_m, rx_height_m, terrain_type)
        return round(loss, 2)

    if is_free_space or upper_uhf:
        loss = _fspl(distance_km, frequency_mhz)
        if upper_uhf and not is_free_space:
            loss += _terrain_correction_db(terrain_type)
    elif hata_ok:
        loss = _cost231_hata_path_loss(distance_km, frequency_mhz, terrain_type, tx_height_m, rx_height_m)
    else:
        loss = _egli_path_loss(distance_km, frequency_mhz, tx_height_m, rx_height_m, terrain_type)
    return round(loss + diffraction_loss_db, 2)


def calculate_path_loss_details(
    distance_km,
    frequency_mhz,
    terrain_type="free space",
    diffraction_loss_db=0.0,
    tx_height_m=0.0,
    rx_height_m=0.0,
    is_los=False,
):
    path_loss_db = calculate_path_loss(
        distance_km,
        frequency_mhz,
        terrain_type,
        diffraction_loss_db,
        tx_height_m,
        rx_height_m,
        is_los,
    )
    return {
        "path_loss_db": path_loss_db,
        "model": classify_path_loss_model(frequency_mhz, terrain_type, tx_height_m, is_los),
        "is_los": is_los,
        "diffraction_loss_db": round(diffraction_loss_db, 1),
    }


def calculate_received_power(eirp_dbm, path_loss_db):
    return round(eirp_dbm - path_loss_db, 2)


def calculate_sensing_distance(
    eirp_dbm,
    freq_mhz,
    terrain_type,
    rx_gain_dbi,
    rx_sensitivity_dbm,
    diffraction_loss_db=0.0,
    tx_height_m=0.0,
    rx_height_m=0.0,
    is_los=False,
):
    max_loss = eirp_dbm + rx_gain_dbi - rx_sensitivity_dbm - diffraction_loss_db
    lo = 0.001
    hi = 1.0
    while calculate_path_loss(hi, freq_mhz, terrain_type, 0.0, tx_height_m, rx_height_m, is_los) < max_loss and hi < 500:
        hi *= 2.0

    for _ in range(60):
        mid = (lo + hi) / 2.0
        if calculate_path_loss(mid, freq_mhz, terrain_type, 0.0, tx_height_m, rx_height_m, is_los) < max_loss:
            lo = mid
        else:
            hi = mid

    distance_km = (lo + hi) / 2.0
    is_free_space = "free space" in terrain_type.lower() or "air" in terrain_type.lower()
    if (freq_mhz > 2000.0 or (freq_mhz >= 1000.0 and not _cost231_valid(freq_mhz, tx_height_m))) and not is_free_space:
        distance_km = min(distance_km, _radio_horizon_km(tx_height_m, rx_height_m))
    return round(max(0.001, distance_km), 3)


def calculate_eirp_dbm(tx_power_dbm, antenna_gain_dbi=0.0, cable_loss_db=0.0):
    return round(tx_power_dbm + antenna_gain_dbi - cable_loss_db, 2)

def bresenham_line(x0, y0, x1, y1):
    """
    Yields the coordinates of a line between (x0, y0) and (x1, y1).
    Used to trace RF rays across the matrix grid.
    """
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    x, y = x0, y0
    sx = -1 if x0 > x1 else 1
    sy = -1 if y0 > y1 else 1
    if dx > dy:
        err = dx / 2.0
        while x != x1:
            yield x, y
            err -= dy
            if err < 0:
                y += sy
                err += dx
            x += sx
    else:
        err = dy / 2.0
        while y != y1:
            yield x, y
            err -= dx
            if err < 0:
                x += sx
                err += dy
            y += sy
    yield x, y

def calculate_fspl_grid(tx_lat, tx_lon, freq_mhz, tx_power_dbm, lats, lons, elevations, tx_height_m=2.0):
    """
    Applies Free Space Path Loss and Terrain Masking (Viewshed) to an entire grid.
    """
    rows, cols = elevations.shape
    
    # 1. Calculate distance matrix in km
    distance_km = haversine_vectorized(tx_lat, tx_lon, lats, lons)
    distance_km[distance_km == 0] = 0.001 # Prevent divide-by-zero
    distance_m = distance_km * 1000.0

    # 2. Vectorized FSPL calculation retained for the legacy heatmap view.
    fspl_matrix = 20 * np.log10(distance_km) + 20 * np.log10(freq_mhz) + 32.44
    rx_power_matrix = tx_power_dbm - fspl_matrix

    # 3. Terrain Masking (Viewshed)
    # Find the matrix indices closest to our Transmitter
    tx_row_idx = np.abs(lats[:, 0] - tx_lat).argmin()
    tx_col_idx = np.abs(lons[0, :] - tx_lon).argmin()
    
    tx_altitude = elevations[tx_row_idx, tx_col_idx] + tx_height_m
    
    # Initialize a shadow mask (False = Line of Sight, True = Blocked by terrain)
    shadow_mask = np.zeros((rows, cols), dtype=bool)

    # Generate the perimeter pixels to shoot our rays toward
    perimeter_points = []
    for r in range(rows):
        perimeter_points.extend([(r, 0), (r, cols - 1)])
    for c in range(1, cols - 1):
        perimeter_points.extend([(0, c), (rows - 1, c)])

    # Shoot a ray to every pixel on the edge of the map
    for edge_r, edge_c in perimeter_points:
        max_angle = -np.inf
        
        for r, c in bresenham_line(tx_row_idx, tx_col_idx, edge_r, edge_c):
            dist = distance_m[r, c]
            if dist == 0: continue
            
            # Calculate the angle of elevation from the Tx to this point on the terrain
            angle = (elevations[r, c] - tx_altitude) / dist
            
            if angle < max_angle:
                # The terrain dropped below our highest seen angle; we are in a shadow
                shadow_mask[r, c] = True
            else:
                # We have line-of-sight, update the new highest angle
                max_angle = angle

    # 4. Apply Diffraction Penalty
    # If a point is in the shadow mask, we apply a massive penalty (e.g., 40 dB loss)
    # For Phase 2, we can swap this hard penalty with real Deygout knife-edge math
    rx_power_matrix[shadow_mask] -= 40.0 

    # 5. Flatten the matrices to prep for JSON export
    output_data = []
    
    for i in range(rows):
        for j in range(cols):
            # Only send points above the noise floor to save browser memory
            if rx_power_matrix[i, j] > -110:
                output_data.append({
                    "lat": round(float(lats[i, j]), 5),
                    "lon": round(float(lons[i, j]), 5),
                    "elev": float(elevations[i, j]),
                    "power_dbm": round(float(rx_power_matrix[i, j]), 2)
                })
                
    return output_data
