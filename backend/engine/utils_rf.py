import numpy as np

def watts_to_dbm(watts):
    """Converts Watts to decibel-milliwatts (dBm)."""
    if watts <= 0:
        return -np.inf
    return 10 * np.log10(watts * 1000)

def dbm_to_watts(dbm):
    """Converts decibel-milliwatts (dBm) to Watts."""
    return (10 ** (dbm / 10)) / 1000

def freq_to_wavelength(freq_mhz):
    """Converts frequency in MHz to wavelength in meters."""
    # Speed of light approx 300,000 km/s
    return 300.0 / freq_mhz

def calculate_eirp_dbm(tx_power_dbm, cable_loss_db, antenna_gain_dbi):
    """
    Calculates Effective Isotropic Radiated Power (EIRP).
    Ensures power strictly uses dBm and gain uses dBi.
    """
    return tx_power_dbm - cable_loss_db + antenna_gain_dbi