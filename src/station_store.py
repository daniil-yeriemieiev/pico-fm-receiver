"""
Temporary Session Storage Module for Auto-Scan Results.

Manages a session-scoped CSV file on the Pico W flash to store discovered FM
stations during runtime. The file is overwritten on each new auto-scan and
automatically removed when the application exits.
"""

import os


class StationStore:
    """
    Temporary file-backed storage for scanned FM radio stations.

    Each station record is stored as a CSV line: ``rssi,frequency,rds``.
    """

    def __init__(self, filepath="autoscan_tmp.csv"):
        """
        Initialize the temporary station store.

        :param str filepath: Path to the session file on the Pico filesystem.
        """
        self.filepath = filepath

    def clear(self):
        """
        Create or overwrite the session file with empty content.
        """
        with open(self.filepath, "w") as f:
            f.write("")

    def add(self, rssi, frequency, rds):
        """
        Append a single discovered station to the session file.

        :param int rssi: Measured signal strength (RSSI).
        :param float frequency: Station frequency in MHz.
        :param str rds: Decoded RDS station name or placeholder.
        """
        clean_rds = (rds or "---").replace("\n", " ").replace("\r", " ").strip()
        with open(self.filepath, "a") as f:
            f.write(f"{int(rssi)},{frequency:.1f},{clean_rds}\n")

    def load(self):
        """
        Read all stored stations from the session file.

        :return: List of ``(rssi, frequency, rds)`` tuples. Returns an empty
                 list if the file does not exist or cannot be parsed.
        :rtype: list
        """
        stations = []
        try:
            with open(self.filepath, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(",", 2)
                    if len(parts) == 3:
                        stations.append((int(parts[0]), float(parts[1]), parts[2]))
        except OSError:
            pass
        return stations

    def cleanup(self):
        """
        Delete the temporary session file if it exists.

        :return: ``True`` if the file was removed, ``False`` otherwise.
        :rtype: bool
        """
        try:
            os.remove(self.filepath)
            return True
        except OSError:
            return False