""" main.py
Tracker thing; runs on ESP32 (MicroPython)
Communicates with U-blox Neo-6 GPS receiver module using UART to
obtain GPS location data. Then casually broadcasts it, using:

1) LoRaWAN unconfirmed data up using Semtech SX127X LoRa transceiver
2) 2.4GHz radio (slave mode) using Nordic Semiconductor nRF24L01

Requires no acknowledgements. Device simply transitions in to deep sleep until
it repeats the process all over again. Quite boring, really.
"""

# TODO: Flash some status LEDs, to instil some human confidence
# TODO: nRF24L01 code not yet implemented
# TODO: Should probably sync time via GPS as well

from machine import UART, deepsleep    # pylint: disable=import-error
import utime                                # pylint: disable=import-error
import ubinascii                            # pylint: disable=import-error
import ujson                                # pylint: disable=import-error
from micropyGPS import MicropyGPS           # pylint: disable=import-error
from ulora import TTN, uLoRa                # pylint: disable=import-error

# Configuration parameters loaded from external json file
TRACKER_CONFIG_FILE = "config/tracker_config.json"
try:
    with open(TRACKER_CONFIG_FILE, "r") as config_file:
        TRACKER_CONFIG = ujson.load(config_file)
except (OSError, IOError) as ex:
    print(ex)

class Tracker():
    """ This is THE tracker. It handles GPS, uLora and nRF24L01 tasks. """
    # pylint: disable=too-few-public-methods

    def __init__(self, tracker_config):
        """ Instantiate a tracker and its devices """
        self.general_config = tracker_config["GENERAL"]
        self.lora_transceiver = LoraTransceiver(tracker_config["LORA"], tracker_config["LORAWAN"])
        self.gps_receiver = GpsReceiver(tracker_config["GPS"])

    def run(self):
        """ Run the tracker application once. """
        _start_time_ms = utime.ticks_ms()
        _errors = 0
        try:
            _gps_data = self.gps_receiver.get_gps_data()
        except (OSError, TypeError) as ex:
            debug_console(ex)
            _errors += 1
        else:
            _gps_data_bytes = self.gps_receiver.convert_to_bytes(_gps_data)
        # TODO: incorporate status LEDs here
        if not _errors:
            try:
                self.lora_transceiver.unconfirmed_data_up(_gps_data_bytes)
            except (OSError, ValueError, RuntimeError, KeyError) as ex:
                debug_console(ex)
                _errors += 1
            # TODO: nRF24L01 code needs to go here
        if _errors:
            debug_console("There are " + str(_errors) + " errors with the tracker")
        _time_elapsed_ms = utime.ticks_ms() - _start_time_ms
        # Deep sleep for the remaining time
        _time_remaining_ms = self.general_config["TRACKER_FREQ_MS"]-_time_elapsed_ms
        debug_console("Deep sleep for " + str(_time_remaining_ms) + " ms...")
        deepsleep(_time_remaining_ms)

class GpsReceiver():
    """ U-blox Neo-6 GPS receiver, accessible using UART. """

    def __init__(self, gps_config):
        """ Instantiate GPS with UART interface. """
        # Ready UART connection
        self.uart = UART(1, gps_config["GPS_UART_BAUD"])
        self.uart.init(
            gps_config["GPS_UART_BAUD"],
            rx=gps_config["GPS_UART_RX"],
            tx=gps_config["GPS_UART_TX"],
            bits=8,
            parity=None,
            stop=1
        )
        self.gps = MicropyGPS(location_formatting="dd")
        self.gps_fix = False
        self.gps_timeout_ms = gps_config["GPS_TIMEOUT_MS"]
        self.gps_timeout_check_ms = gps_config["GPS_TIMEOUT_CHECK_MS"]
        utime.sleep_ms(gps_config["GPS_LOAD_TIME_MS"])

    def get_gps_data(self):
        """ Retrieve GPS data via UART, and parse using GPS parser (blocking). """
        _gps_data = {}
        _gps_retries = 0
        self.gps_fix = False
        _start_time_ms = utime.ticks_ms()
        while not self.gps_fix:
            for _data in self.uart.read():
                self.gps.update(chr(_data))
            if self.gps.fix_type != 1:
                self.gps_fix = True
                _gps_data["latitude"] = self.gps.latitude
                _gps_data["longitude"] = self.gps.longitude
                # Minimum altitude of sea level (0m)
                _altitude = int(self.gps.altitude)
                if _altitude < 0:
                    _altitude = 0
                _gps_data["altitude"] = _altitude
                _gps_data["course"] = self.gps.course
            else:
                _time_elapsed_ms = utime.ticks_ms() - _start_time_ms
                if not _time_elapsed_ms >= self.gps_timeout_ms:
                    _gps_retries += 1
                    utime.sleep_ms(
                        _gps_retries * self.gps_timeout_check_ms - _time_elapsed_ms
                    )
                else:
                    raise OSError("Timed out waiting for GPS fix")
        debug_console("GPS data: " + str(_gps_data))
        return _gps_data

    def convert_to_bytes(self, gps_data):
        """ Apply transformations to GPS data, and create byte array. """
        # pylint: disable=no-self-use
        _data_bytes = b""
        _lat_int_offset = 90
        _long_int_offset = 180
        _lat_long_offset = 6
        lat_int, lat_frac = str(gps_data["latitude"][0]).split(".")
        long_int, long_frac = str(gps_data["longitude"][0]).split(".")
        if gps_data["latitude"][1] == "S":
            lat_int = -lat_int
        if gps_data["longitude"][1] == "W":
            long_int = -long_int
        _data_bytes += (int(lat_int) + _lat_int_offset).to_bytes(1, "big")
        _data_bytes += (int(lat_frac[:_lat_long_offset])).to_bytes(3, "big")
        _data_bytes += (int(long_int) + _long_int_offset).to_bytes(2, "big")
        _data_bytes += (int(long_frac[:_lat_long_offset])).to_bytes(3, "big")
        _data_bytes += (int(gps_data["altitude"])).to_bytes(2, "big")
        _data_bytes += (int(gps_data["course"] * 10)).to_bytes(2, "big")
        debug_console("GPS data in bytes: " + str(ubinascii.hexlify(_data_bytes)))
        return _data_bytes

class LoraTransceiver:
    """ Semtech SX1276 transceiver and the LoRaWAN protocol. """
    # pylint: disable=too-few-public-methods

    def __init__(self, lora_config, lorawan_config):
        """ Initialise a ulora object with Semtech SX127X parameters and
        LoRaWAN details """
        self.lora = uLoRa(
            cs=lora_config["LORA_CS"],
            sck=lora_config["LORA_SCK"],
            mosi=lora_config["LORA_MOSI"],
            miso=lora_config["LORA_MISO"],
            irq=lora_config["LORA_IRQ"],
            rst=lora_config["LORA_RST"],
            datarate=lora_config["LORA_DATARATE"],
            ttn_config=TTN(
                dev_address=self._convert_to_bytearray(lorawan_config["LORAWAN_DEVADDR"]),
                net_key=self._convert_to_bytearray(lorawan_config["LORAWAN_NWKEY"]),
                app_key=self._convert_to_bytearray(lorawan_config["LORAWAN_APPKEY"]),
                country=lorawan_config["LORAWAN_REGION"]
            ),
            fport=lorawan_config["LORAWAN_FPORT"]
        )

    def unconfirmed_data_up(self, data):
        """ Send raw LoRaWAN raw packets using SX127X. """
        debug_console("Sending LoRa packet: " + str(ubinascii.hexlify(data)))
        self.lora.send_data(data, len(data), self.lora.frame_counter)
        debug_console("LoRa bytes sent: " + str(len(data)))
        self.lora.frame_counter += 1

    def _convert_to_bytearray(self, str_list):
        """ JSON byte arrays are stored as list of strings. Convert these into
        real bytearray. """
        # pylint: disable=no-self-use
        _bytearray = []
        for _byte_str in str_list:
            _bytearray.append(int(_byte_str))
        return bytearray(_bytearray)

def debug_console(print_message):
    """ Timestamped display to console for debugging purposes. """
    if bool(TRACKER_CONFIG["GENERAL"]["DEBUG_CONSOLE"]):
        print(
            _current_timestamp() + " " +
            str(print_message)
        )

def _current_timestamp():
    """ Convert time into readable format. Useful for debugging. """
    year, month, day, hour, minute, second = utime.localtime()[:6]
    return str(_add_leading_zero(day)) + \
        str(_add_leading_zero(month))+ \
        str(year) + \
        " " + \
        str(_add_leading_zero(hour)) + \
        str(_add_leading_zero(minute)) + \
        str(_add_leading_zero(second))

def _add_leading_zero(digit):
    """ Add leading zero to digit, for nicer formatting. """
    return "{:02d}".format(digit)

def main():
    """ Main tracker program. That's about it. """
    try:
        tracker = Tracker(TRACKER_CONFIG)
        tracker.run()
    except OSError as ex:
        debug_console(ex)

if __name__ == "__main__":
    main()
