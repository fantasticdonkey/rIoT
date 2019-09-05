""" riot-brick-sensors.py
Takes readings from connected sensors, and stores payload in a sqlite3 database.
Also stores individual values locally in a CSV file for safekeeping.
"""

# TODO: Photoresistor / UV sensors
# TODO: Persist total distance / time over restarts

import sys
import time
import datetime
import json
import subprocess
import platform
import sqlite3
from haversine import haversine
import gpsd
import psutil
import Adafruit_BME280

BRICK_CONFIG_FILE = "config/brick_config.json"
with open(BRICK_CONFIG_FILE) as config_file:
    BRICK_CONFIG = json.load(config_file)
DEV_ID = BRICK_CONFIG["dev_id"]

class WeatherSensor():
    """ BME280 temperature, pressure and humidity sensor object """

    def __init__(self, weather_sensor_config):
        """ BME280 sensor initialisation """
        try:
            self.weather_sensor = Adafruit_BME280.BME280(
                address=weather_sensor_config["bme280_i2c_address"]
            )
        except OSError as ex:
            printf(ex)

    def get_readings(self):
        """ Read raw data from the BME280 sensor and return formatted.
        Returnes none if no readings are retrieved. """
        _readings = None
        try:
            degrees = round(self.weather_sensor.read_temperature(), 1)
            pascals = round(self.weather_sensor.read_pressure(), 0)
            humidity = round(self.weather_sensor.read_humidity(), 0)
        except OSError as ex:
            printf(ex)
        else:
            _readings = (degrees, pascals, humidity)
        return _readings

class GPSReceiver():
    """ U-blox Neo-6 GPS receiver module connected via UART """

    def __init__(self, gps_receiver_config):
        """ Initialise Neo-6 GPS module """
        gpsd.connect()
        while self.get_gps_fix() < 2:
            printf("Awaiting GPS fix...")
            time.sleep(gps_receiver_config["fix_retry_s"])
        # Set system time to UTC time provided by GPS
        # Important for when there is no internet connectivity (i.e. no NTP)
        # Only works on Linux systems with timedatectl
        time.sleep(gps_receiver_config["fix_retry_s"])
        _gps_time_now = gpsd.get_current().get_time().strftime("%Y-%m-%d %H:%M:%S UTC")
        _time_now = datetime.datetime.now()
        try:
            p_set_time = subprocess.Popen(
                [
                    "sudo",
                    "timedatectl",
                    "set-time",
                    "{:}".format(_gps_time_now)
                ], stdout=subprocess.PIPE
            )
            p_set_time.wait()
        except OSError as ex:
            print(ex)
        else:
            printf(
                "Changed system time from " +
                str(_time_now) +
                " to "+
                str(datetime.datetime.now())
            )
        printf("GPS initialised")
        printf(str(gpsd.state))

    def get_data(self):
        """ Get current data from gpsd """
        _gps_data_out = None
        try:
            _gps_raw_data = gpsd.get_current()
            # Extract only position (lat / long) and altitude values
            _gps_data_out = (
                _gps_raw_data.position(),
                _gps_raw_data.altitude()
            )
        except (UserWarning, gpsd.NoFixError) as ex:
            printf(ex)
        return _gps_data_out

    def get_gps_fix(self):
        """ Check current mode / GPS fix
        0=no mode, 1=no fix, 2=2D fix, 3=3D fix """
        return gpsd.get_current().mode

class SensorController():
    """ Handles all connected sensors """

    def __init__(self, brick_config):
        """ Initialise the controller """
        self.sensors_config = brick_config["sensors"]
        self.logging_config = brick_config["logging"]
        self.weather_sensor = WeatherSensor(self.sensors_config["weather_sensor"])
        self.gps = GPSReceiver(self.sensors_config["gps_receiver"])
        # All of these running stats are reset at app start-up
        self.total_distance_km = 0
        self.total_climb_m = 0
        self.last_data = {}
        self.start_time = datetime.datetime.now()
        self.total_duration_s = 0
        # SQLite3 connection details
        self.conn = None
        self.cur = None
        self.sensor_database = brick_config["database"]["sqlite_database"]
        self.sensor_data_table = brick_config["database"]["sqlite_table"]
        printf("Sensor controller initialised")

    def run(self):
        """ Indefinite loop to run the controller app """
        while True:
            printf("Sensor controller run started")
            _start_time = time.time()
            _current_data, _no_gps_data = self._obtain_measurements()
            if not _no_gps_data:
                self._log_to_file(_current_data)
                self._log_to_database(_current_data)
            printf("Sensor controller run completed")
            _remaining_time = self.sensors_config["frequency_s"] - int(time.time()-_start_time)
            if _remaining_time > 0:
                time.sleep(_remaining_time)

    def _obtain_measurements(self):
        """ Obtain measurements from all devices """
        _collected_data = {}
        _collected_data["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _gps_data = self.gps.get_data()
        if _gps_data:
            _collected_data["position_lat"] = _gps_data[0][0]
            _collected_data["position_long"] = _gps_data[0][1]
            _collected_data["location"] = str(_gps_data[0][0]) + "," + str(_gps_data[0][1])
            _collected_data["altitude"] = _gps_data[1]
            _no_gps_data = False
            if self.last_data:
                if _collected_data["altitude"] > self.last_data["altitude"]:
                    self.total_climb_m = round(
                        self.total_climb_m +
                        _collected_data["altitude"] -
                        self.last_data["altitude"],
                        1
                    )
                _distance_travelled = haversine(
                    (self.last_data["position_lat"], self.last_data["position_long"]),
                    (_collected_data["position_lat"], _collected_data["position_long"])
                )
                self.total_distance_km = round((self.total_distance_km + _distance_travelled), 3)
            self.last_data = _collected_data
        else:
            _no_gps_data = True
        _weather_readings = self.weather_sensor.get_readings()
        _collected_data["temperature"] = _weather_readings[0]
        _collected_data["pressure"] = _weather_readings[1]
        _collected_data["humidity"] = _weather_readings[2]
        _collected_data["total_distance"] = self.total_distance_km
        _collected_data["total_climb"] = self.total_climb_m
        _collected_data["total_time"] = (datetime.datetime.now() - self.start_time).seconds
        _collected_data["dev_id"] = DEV_ID
        _collected_data["cpu"] = psutil.cpu_percent()
        _collected_data["memory"] = psutil.virtual_memory().percent
        _collected_data["disk"] = psutil.disk_usage("/").percent
        _collected_data["system"] = platform.system()
        _collected_data["release"] = platform.release()
        printf(_collected_data)
        return (_collected_data, _no_gps_data)

    def _log_to_file(self, log_data):
        """ Log results to a flat text file """
        if self.logging_config["file_logging"]:
            _log_file = open(
                self.logging_config["file_name"] +
                log_data["timestamp"][:10] +
                "." +
                self.logging_config["file_extension"],
                "a"
            )
            _log_file.write(
                str(log_data["timestamp"]) + "," +
                str(log_data["position_lat"]) + "," +
                str(log_data["position_long"]) + "," +
                str(log_data["altitude"]) + "," +
                str(log_data["temperature"]) + "," +
                str(log_data["pressure"]) + "," +
                str(log_data["humidity"]) + "," +
                str(log_data["total_distance"]) + "," +
                str(log_data["total_climb"]) + "," +
                str(log_data["total_time"]) + "," +
                "\n")
            _log_file.close()

    def _log_to_database(self, log_data):
        """ Log data to local cache database """
        try:
            self.conn = sqlite3.connect(self.sensor_database)
            self.cur = self.conn.cursor()
            self.cur.execute(
                "INSERT INTO " +
                self.sensor_data_table +
                " (payload, dev_uid) VALUES (?, 0)",
                (str(log_data),)
            )
            self.conn.commit()
        except sqlite3.OperationalError as ex:
            printf(ex)
        finally:
            self.conn.close()

def printf(message):
    """ Print to console wrapper, inludes timestamp.
    Flushes buffer to output when using Supervisor """
    print(str(datetime.datetime.now()) + ": " + str(message), flush=True)

def main():
    """ Main program """
    tracker = SensorController(BRICK_CONFIG)
    tracker.run()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        printf("Sensor controller stopped")
        sys.exit()
