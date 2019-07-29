""" rosie_update_deviceshadow.py
Update device shadows with GPS data based on incoming TTN LoRaWAN payload.
"""

import json
import boto3
from botocore.exceptions import ClientError

client = boto3.client("iot-data")

def lambda_handler(event, context):
    """ Update reported state of device shadow with LoRaWAN payload """
    _data = {"state": {"reported": event}}
    response = client.update_thing_shadow(
        thingName = event["dev_id"],
        payload = json.dumps(_data)
    )
    print(response, _data)