""" riot-brick-rfproxys.py
Takes readings from remote trackers via nRF24 receiver, and stores payload in a sqlite3 database.
Also stores individual values locally in a CSV file for safekeeping.
"""

import sys
import time
import datetime
import json
import sqlite3
import nrf24

BRICK_CONFIG_FILE = "config/brick_config.json"
with open(BRICK_CONFIG_FILE) as config_file:
    BRICK_CONFIG = json.load(config_file)
DEV_ID = BRICK_CONFIG["dev_id"]

class NRF():
    """ Represents the nRF24L01+ transceiver.
    It will only be used in receiver mode. """

    def __init__(self, brick_config):
        """ Initialise the nRF """
        self.rfproxy_config = brick_config["rfproxy"]
        self.logging_config = brick_config["logging"]
        self.radio = nrf24.NRF24(
            major=0,
            minor=0,
            ce_pin=self.rfproxy_config["nrf24_ce_pin"],
            irq_pin=self.rfproxy_config["nrf24_irq_pin"]
        )
        self.radio.begin(
            major=0,
            minor=0,
            ce_pin=self.rfproxy_config["nrf24_ce_pin"],
            irq_pin=self.rfproxy_config["nrf24_irq_pin"]
        )
        # Details must match transmit side
        self.radio.setRetries(15, 15)
        self.radio.setPayloadSize(self.rfproxy_config["nrf24_payload_size"])
        self.radio.setChannel(self.rfproxy_config["nrf24_channel"])
        self.radio.setDataRate(nrf24.NRF24.BR_250KBPS)
        self.radio.setPALevel(nrf24.NRF24.PA_MAX)
        self.radio.setAutoAck(1)
        self.pipes = eval(self.rfproxy_config["nrf24_pipes"])
        self.radio.openWritingPipe(self.pipes[0])
        self.radio.openReadingPipe(1, self.pipes[1])
        self.radio.startListening()
        self.radio.stopListening()
        self.radio.printDetails()
        self.radio.startListening()
        # SQLite3 connection details
        self.conn = None
        self.cur = None
        self.sensor_database = brick_config["database"]["sqlite_database"]
        self.sensor_data_table = brick_config["database"]["sqlite_table"]
        printf("RF-proxy controller initialised")

    def run(self):
        """ Indefinite loop to run the app """
        while True:
            try:
                pipe = [0]
                while not self.radio.available(pipe, True):
                    time.sleep(self.rfproxy_config["nrf24_read_frequency_s"])
                recv_buffer = []
                self.radio.read(recv_buffer)
                printf("Bytes received: " + str(recv_buffer))
                # 1st byte of payload used as the shared id. For packet to be valid,
                # receiver must be expecting this id.
                if recv_buffer[0] == self.rfproxy_config["shared_id"]:
                    _received_data = self._process_payload(
                        recv_buffer[1:self.rfproxy_config["nrf24_payload_size"]]
                    )
                    _proxy_received_data = {}
                    _proxy_received_data["rfproxy"] = _received_data
                    _proxy_received_data["dev_id"] = _received_data["dev_id"]
                    self._log_to_database(_received_data["dev_uid"], _proxy_received_data)
                    self._log_to_file(_received_data)
            except KeyboardInterrupt:
                break

    def _process_payload(self, payload):
        """ Convert readings from bytearray payload, and remove neccessary offsets """
        _collected_data = {}
        _collected_data["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _collected_data["dev_uid"] = payload[0]
        _collected_data["dev_id"] = "riot-tracker-" + str(_collected_data["dev_uid"])
        # Remove offsets applied before tranmit
        _gps_latitude =\
            float(
                str(self._convert_bytes_to_int(payload, 1, 1)-90) + "." +\
                str(self._convert_bytes_to_int(payload, 2, 3))
            )
        _gps_longitude =\
            float(
                str(self._convert_bytes_to_int(payload, 5, 2)-180) + "." +\
                str(self._convert_bytes_to_int(payload, 7, 3))
            )
        _collected_data["position_lat"] = _gps_latitude
        _collected_data["position_long"] = _gps_longitude
        printf(_collected_data)
        return _collected_data

    def _convert_bytes_to_int(self, in_bytearray, start_position, num_bytes):
        """ Converts fixed number of bytes into a single integer """
        _temp = bytearray([])
        n_byte = 0
        while n_byte < num_bytes:
            _temp.append(in_bytearray[start_position+n_byte])
            n_byte += 1
        return int.from_bytes(_temp, "big")

    def _log_to_file(self, log_data):
        """ Log results to a flat text file """
        if self.logging_config["file_logging"]:
            _log_file = open(
                self.logging_config["file_name"] +
                "rfproxy_" +
                log_data["timestamp"][:10] +
                "." +
                self.logging_config["file_extension"],
                "a"
            )
            _log_file.write(
                str(log_data["timestamp"]) + "," +
                str(log_data["dev_uid"]) + "," +
                str(log_data["position_lat"]) + "," +
                str(log_data["position_long"]) +
                "\n")
            _log_file.close()

    def _log_to_database(self, dev_uid, log_data):
        """ Log data to local cache database """
        try:
            self.conn = sqlite3.connect(self.sensor_database)
            self.cur = self.conn.cursor()
            self.cur.execute(
                "INSERT INTO " +
                self.sensor_data_table +
                " (payload, dev_uid) VALUES (?, ?)",
                (str(log_data), int(dev_uid),)
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
    nrfproxy = NRF(BRICK_CONFIG)
    nrfproxy.run()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        printf("RF-proxy controller stopped")
        sys.exit()
