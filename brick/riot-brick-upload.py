""" riot-brick-upload.py
Retrieves cached readings from riot.db and uploads to AWS IoT using REST API.
"""
# TODO: Check Internet connectivity before upload

import time
import json
from os import environ
import sqlite3
import requests

FREQUENCY_S = 60
SQLITE_DATABASE = "db/riot.db"
SQLITE_TABLE = "sensor_data"
AWS_IOT_CERT_DIRECTORY = "certs/"
# Load AWS IoT thing certificate locations from environment variables
if "AWS_IOT_THING_CERT" in environ:
    AWS_IOT_THING_CERT = environ["AWS_IOT_THING_CERT"]
else:
    raise OSError("Environment variable AWS_IOT_THING_CERT not found")
if "AWS_IOT_THING_KEY" in environ:
    AWS_IOT_THING_KEY = environ["AWS_IOT_THING_KEY"]
else:
    raise OSError("Environment variable AWS_IOT_THING_KEY not found")
if "AWS_IOT_THING_CA" in environ:
    AWS_IOT_THING_CA = environ["AWS_IOT_THING_CA"]
else:
    raise OSError("Environment variable AWS_IOT_THING_CA not found")
if "AWS_IOT_ENDPOINT" in environ:
    AWS_IOT_ENDPOINT = environ["AWS_IOT_ENDPOINT"]
else:
    raise OSError("Environment variable AWS_IOT_ENDPOINT not found")

class Uploader():
    """ Controller to check local SQLite database / table, and upload
    any cached events """
    # pylint: disable=too-few-public-methods

    def __init__(self):
        """ Initialise with some parameters """
        self.aws_iot_uploader = AWSIoTUploader()
        self.conn = None
        self.cur = None
        self.sensor_data_table = SQLITE_TABLE
        print("Uploader initialised")

    def run(self):
        """ Run the uploader application continuously """
        while True:
            print("Uploader run started")
            start_time = time.time()
            self.conn = sqlite3.connect(SQLITE_DATABASE)
            self.cur = self.conn.cursor()
            try:
                rows = self.cur.execute(
                    "SELECT id, payload FROM " +
                    self.sensor_data_table +
                    " WHERE processed = 0"
                )
                cached_records = []
                for row in rows:
                    cached_records.append(row)
                print("Discovered", len(cached_records), "cached records")
                for cached_record in cached_records:
                    _cached_record_id = int(cached_record[0])
                    _cached_record_json = json.loads(cached_record[1].replace("'", '"'))
                    # Attempt to upload data
                    _response = self.aws_iot_uploader.upload(_cached_record_json)
                    if _response.status_code == 200:
                        self.cur.execute(
                            "UPDATE " +
                            self.sensor_data_table +
                            " SET processed = 1 WHERE id = " +
                            str(_cached_record_id)
                        )
                        self.conn.commit()
                        print("Succesfully uploaded record", _cached_record_id)
                    else:
                        print(
                            "Error encountered during upload of",
                            _cached_record_id,
                            "(",
                            _response.status_code, ")"
                        )
            except sqlite3.OperationalError as ex:
                print("Run failed:", ex)
            finally:
                # Always close connection afterwards
                self.conn.close()
            remaining_time = FREQUENCY_S - int(time.time() - start_time)
            if remaining_time > 0:
                time.sleep(remaining_time)

class AWSIoTUploader():
    """ Upload single AWS IoT message using HTTPS, and handle responses """
    # pylint: disable=too-few-public-methods

    def __init__(self):
        """ Initialise requests REST parameters for upload """
        self.aws_iot_endpoint = AWS_IOT_ENDPOINT
        self.aws_iot_certs = (
            AWS_IOT_CERT_DIRECTORY + AWS_IOT_THING_CERT,
            AWS_IOT_CERT_DIRECTORY + AWS_IOT_THING_KEY
        )
        self.aws_ca_certfile = AWS_IOT_CERT_DIRECTORY + AWS_IOT_THING_CA

    def upload(self, data):
        """ Use REST POST to upload single AWS IoT message """
        _response = requests.post(
            url=self.aws_iot_endpoint,
            cert=self.aws_iot_certs,
            verify=self.aws_ca_certfile,
            data=json.dumps(data)
        )
        return _response

def main():
    """ Main application """
    uploader = Uploader()
    uploader.run()

if __name__ == "__main__":
    # Lauch main application
    main()
