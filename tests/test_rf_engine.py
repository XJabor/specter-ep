import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import create_app
from engine.propagation import (
    calculate_eirp_dbm,
    calculate_path_loss,
    calculate_path_loss_details,
    calculate_received_power,
    calculate_sensing_distance,
    directional_gain_db,
)
from engine.terrain import check_line_of_sight
from engine.utils_rf import watts_to_dbm
from pipeline.jf12_parser import JF12Parser


class PropagationTests(unittest.TestCase):
    def test_watts_to_dbm(self):
        self.assertAlmostEqual(watts_to_dbm(1), 30.0, places=6)
        self.assertAlmostEqual(watts_to_dbm(10), 40.0, places=6)

    def test_eirp_and_received_power(self):
        self.assertEqual(calculate_eirp_dbm(37, 2, 1), 38)
        self.assertEqual(calculate_received_power(38, 120), -82)

    def test_directional_gain_rolloff(self):
        self.assertEqual(directional_gain_db(20, 90, 90, 30), 20)
        self.assertAlmostEqual(directional_gain_db(20, 90, 105, 30), 17, places=6)
        self.assertEqual(directional_gain_db(20, 90, 180, 30), 0)

    def test_path_loss_model_selection(self):
        vhf = calculate_path_loss_details(5, 300, "rural", tx_height_m=2, rx_height_m=2, is_los=True)
        self.assertEqual(vhf["model"], "Egli")

        elevated_los = calculate_path_loss_details(5, 900, "rural", tx_height_m=35, rx_height_m=2, is_los=True)
        self.assertEqual(elevated_los["model"], "Two-Ray Ground Reflection")

        elevated_nlos = calculate_path_loss_details(5, 900, "rural", tx_height_m=35, rx_height_m=2, is_los=False)
        self.assertEqual(elevated_nlos["model"], "COST-231 Hata")

        shf = calculate_path_loss_details(2, 5000, "dense forest", tx_height_m=2, rx_height_m=2, is_los=False)
        self.assertEqual(shf["model"], "SHF FSPL + clutter")

    def test_loss_and_range_are_sensible(self):
        loss_1km = calculate_path_loss(1, 300, "free space", is_los=True)
        self.assertAlmostEqual(loss_1km, 81.98, places=1)

        range_km = calculate_sensing_distance(39, 300, "rural", 0, -100, tx_height_m=2, rx_height_m=2, is_los=True)
        self.assertGreater(range_km, 1)


class TerrainTests(unittest.TestCase):
    def test_line_of_sight_clear_profile(self):
        profile = [
            {"distance_km": 0, "elevation_m": 10},
            {"distance_km": 0.5, "elevation_m": 10},
            {"distance_km": 1.0, "elevation_m": 10},
        ]
        los = check_line_of_sight(profile, 300, 2, 2)
        self.assertTrue(los["is_los"])
        self.assertEqual(los["diffraction_loss_db"], 0.0)

    def test_line_of_sight_blocked_profile(self):
        profile = [
            {"distance_km": 0, "elevation_m": 0},
            {"distance_km": 0.5, "elevation_m": 100},
            {"distance_km": 1.0, "elevation_m": 0},
        ]
        los = check_line_of_sight(profile, 300, 2, 2)
        self.assertFalse(los["is_los"])
        self.assertGreater(los["diffraction_loss_db"], 0)


class ParserTests(unittest.TestCase):
    def test_jf12_watts_to_dbm_conversion(self):
        parsed = JF12Parser().parse_text("Nomenclature: AN/PRC-117G Power: 20 Watts")
        self.assertAlmostEqual(parsed["max_power_dbm"], 30 + 10 * math.log10(20), places=6)


class ApiContractTests(unittest.TestCase):
    def test_runtime_config_contract(self):
        app = create_app()
        client = app.test_client()
        response = client.get("/api/v1/config")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["status"], "success")
        self.assertIn("terrain_path", body)
        self.assertIn("default_map_center", body)

    def test_terrain_status_and_source_contract(self):
        app = create_app()
        client = app.test_client()
        status_response = client.get("/api/v1/terrain/status")
        self.assertEqual(status_response.status_code, 200)
        status_body = status_response.get_json()
        self.assertEqual(status_body["status"], "success")
        self.assertIn("terrain", status_body)
        self.assertIn("elevation_source_count", status_body["terrain"])

        source_response = client.post("/api/v1/terrain/source", json={
            "path": str(ROOT / "data_store" / "terrain_cache" / "Oahu_Tiff.tif")
        })
        self.assertEqual(source_response.status_code, 200)
        source_body = source_response.get_json()
        self.assertEqual(source_body["status"], "success")
        self.assertEqual(source_body["terrain"]["imagery_source_count"], 1)
        self.assertEqual(source_body["terrain"]["elevation_source_count"], 0)

    def test_footprint_contract_includes_metadata(self):
        app = create_app()
        client = app.test_client()
        response = client.post("/api/v1/footprint", json={
            "tx_lat": 21.4765,
            "tx_lon": -157.9647,
            "freq_mhz": 300,
            "tx_power_dbm": 37,
            "antenna_gain_dbi": 2,
            "tx_height_m": 2,
            "rx_sensitivity_dbm": -100,
            "terrain": "rural",
            "num_bearings": 8,
            "num_samples": 6,
            "max_radius_km": 1,
        })
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(len(body["polygon_points"]), 8)
        self.assertEqual(len(body["sectors"]), 8)
        self.assertIn("summary", body)
        self.assertIn("terrain", body)
        self.assertIn("warnings", body)
        self.assertIn("model", body["sectors"][0])
        self.assertIn("diffraction_loss_db", body["sectors"][0])


if __name__ == "__main__":
    unittest.main()
