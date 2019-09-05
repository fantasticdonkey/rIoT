""" riot-brick-upload.py
Retrieves cached JSON data from SQLite3 database and uploads to AWS IoT using REST API.
Marks uploaded messages as processed.
Note that several environment variables need to be set for AWS IoT certificate
and endpoint details. The application also restarts wlan interface if connection is
not detected.
"""

import time
import datetime
import subprocess
import sys
import json
from os import environ
import socket
import sqlite3
import requests

BRICK_CONFIG_FILE = "config/brick_config.json"
with open(BRICK_CONFIG_FILE) as config_file:
    BRICK_CONFIG = json.load(config_file)
DEV_ID = BRICK_CONFIG["dev_id"]

# Load AWS IoT thing certificate locations from environment variables
if "AWS_IOT_THING_CA" in environ:
    AWS_IOT_THING_CA = environ["AWS_IOT_THING_CA"]
else:
    raise OSError("Environment variable AWS_IOT_THING_CA not found")
# Load all trackers (environment variables must be present)
active_trackers = {}
for key, value in BRICK_CONFIG["uploader"]["trackers"].items():
    active_trackers[int(key)] = {}
    environmet_var_cert = "AWS_IOT_" + str(key).upper() + "_CERT"
    environmet_var_key = "AWS_IOT_" + str(key).upper() + "_KEY"
    environmet_var_endpoint = "AWS_IOT_" + str(key).upper() + "_ENDPOINT"
    if environmet_var_cert in environ:
        active_trackers[int(key)]["cert"] = environ[environmet_var_cert]
    else:
        raise OSError("Environment variable " + environmet_var_cert + " not found")
    if environmet_var_key in environ:
        active_trackers[int(key)]["key"] = environ[environmet_var_key]
    else:
        raise OSError("Environment variable " + environmet_var_key + " not found")
    if environmet_var_endpoint in environ:
        active_trackers[int(key)]["endpoint"] = environ[environmet_var_endpoint]
    else:
        raise OSError("Environment variable " + environmet_var_endpoint + " not found")
    active_trackers[int(key)]["name"] = value["name"]

class Uploader():
    """ Controller to check local SQLite database / table, and upload
    any cached events """
    # pylint: disable=too-few-public-methods

    def __init__(self, active_trackers):
        """ Initialise with some parameters """
        self.aws_iot_uploader = AWSIoTUploader(AWS_IOT_THING_CA)
        self.conn = None
        self.cur = None
        self.sensor_database = BRICK_CONFIG["database"]["sqlite_database"]
        self.sensor_data_table = BRICK_CONFIG["database"]["sqlite_table"]
        printf("Uploader initialised")
        self.active_trackers = active_trackers
        printf("Discovered trackers: " + str(self.active_trackers))

    def run(self):
        """ Run the uploader application continuously """
        while True:
            printf("Uploader run started")
            _start_time = time.time()
            test_url = self.active_trackers[0]["endpoint"].split("/")[2].split(":")
            _connection = False
            _wlan_interface = BRICK_CONFIG["uploader"]["wlan_interface"]
            if test_connection(test_url[0], int(test_url[1])):
                _connection = True
            else:
                printf("No connectivity to " + test_url[0] + ":" + str(test_url[1]))
                printf("Restarting wlan interface " + _wlan_interface)
                try:
                    p_reconnect_wifi = subprocess.Popen(
                        ["sudo", "systemctl", "restart", "dhcpdc.service"], stdout=subprocess.PIPE
                    )
                    p_reconnect_wifi.wait()
                except OSError as ex:
                    printf(ex)
                else:
                    printf("Restarted wlan interface " + _wlan_interface)
                    time.sleep(10)
                    if test_connection(test_url[0], int(test_url[1])):
                        _connection = True
            if _connection:
                printf("Connection possible to " + test_url[0] + ":" + str(test_url[1]))
            else:
                printf("Failed to connect to " + test_url[0] + ":" + str(test_url[1]))
            if _connection:
                self.conn = sqlite3.connect(self.sensor_database)
                self.cur = self.conn.cursor()
                try:
                    rows = self.cur.execute(
                        "SELECT id, payload, dev_uid FROM " +
                        self.sensor_data_table +
                        " WHERE processed = 0 ORDER BY id ASC"
                    )
                    cached_records = []
                    for row in rows:
                        cached_records.append(row)
                    printf("Discovered " + str(len(cached_records)) + " cached records")
                    for cached_record in cached_records:
                        _cached_record_id = int(cached_record[0])
                        _cached_record_json = json.loads(cached_record[1].replace("'", '"'))
                        # Attempt to upload data
                        _response = self.aws_iot_uploader.upload(
                            _cached_record_json,
                            self.active_trackers[cached_record[2]]["endpoint"],
                            self.active_trackers[cached_record[2]]["cert"],
                            self.active_trackers[cached_record[2]]["key"]
                        )
                        if _response.status_code == 200:
                            self.cur.execute(
                                "UPDATE " +
                                self.sensor_data_table +
                                " SET processed = 1 WHERE id = " +
                                str(_cached_record_id)
                            )
                            self.conn.commit()
                            printf("Succesfully uploaded record " + str(_cached_record_id))
                        else:
                            printf(
                                "Error encountered during upload of " +
                                str(_cached_record_id) +
                                " (" +
                                str(_response.status_code) +
                                ")"
                            )
                except (
                        sqlite3.OperationalError, requests.exceptions.SSLError,
                        FileNotFoundError
                    ) as ex:
                    printf(ex)
                finally:
                    # Always close connection afterwards
                    self.conn.close()
            _remaining_time = BRICK_CONFIG["uploader"]["frequency_s"] \
                - int(time.time()-_start_time)
            if _remaining_time > 0:
                time.sleep(_remaining_time)

class AWSIoTUploader():
    """ Upload single AWS IoT message using HTTPS, and handle responses """
    # pylint: disable=too-few-public-methods

    def __init__(self, aws_iot_thing_ca):
        """ Initialise requests REST parameters for upload """
        self.aws_ca_certfile = BRICK_CONFIG["uploader"]["cert_dir"] + aws_iot_thing_ca

    def upload(self, data, thing_endpoint, thing_cert, thing_key):
        """ Use REST POST to upload single AWS IoT message
        """
        aws_endpoint = thing_endpoint
        aws_iot_certs = (
            BRICK_CONFIG["uploader"]["cert_dir"] + thing_cert,
            BRICK_CONFIG["uploader"]["cert_dir"] + thing_key
        )
        _response = requests.post(
            url=aws_endpoint,
            cert=aws_iot_certs,
            verify=self.aws_ca_certfile,
            data=json.dumps(data)
        )
        return _response

def test_connection(url, port):
    """ Test connectivity to a URL / port """
    connection = False
    try:
        host = socket.gethostbyname(url)
        _socket = socket.create_connection((host, port), 2)
        connection = True
    except:
        pass
    return connection

def printf(message):
    """ Print to console wrapper, inludes timestamp.
    Flushes buffer to output when using Supervisor """
    print(str(datetime.datetime.now()) + ": " + str(message), flush=True)

def main():
    """ Main application """
    uploader = Uploader(active_trackers)
    uploader.run()

if __name__ == "__main__":
    # Launch main application
    try:
        main()
    except KeyboardInterrupt:
        printf("Uploader stopped")
        sys.exit()
