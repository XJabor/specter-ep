import re
import math

class JF12Parser:
    """
    Initial skeleton for extracting RF parameters from technical 
    text blocks found in JF12 or vendor spec sheets.
    """
    def __init__(self):
        # Regex patterns for common military spec formatting
        self.patterns = {
            "power": r"Power:\s*(\d+\.?\d*)\s*(Watts|W|dBm)",
            "frequency": r"Frequency\s*Range:\s*(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s*(MHz|GHz)",
            "nomenclature": r"Nomenclature:\s*([A-Z0-9\-/]+)"
        }

    def parse_text(self, raw_text):
        results = {}
        
        # Extract Nomenclature
        name_match = re.search(self.patterns["nomenclature"], raw_text)
        results["name"] = name_match.group(1) if name_match else "Unknown System"

        # Extract Power and normalize to dBm
        power_match = re.search(self.patterns["power"], raw_text)
        if power_match:
            val = float(power_match.group(1))
            unit = power_match.group(2)
            results["max_power_dbm"] = val if "dBm" in unit else 30 + (10 * math.log10(val))

        return results

# Example Usage:
# parser = JF12Parser()
# print(parser.parse_text("Nomenclature: AN/PRC-117G Power: 20 Watts"))
