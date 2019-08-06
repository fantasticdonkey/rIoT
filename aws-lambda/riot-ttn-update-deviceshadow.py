""" riot-ttn-update-deviceshadow.py
Update device shadow document of a thing in AWS IoT Core
with GPS data based on incoming TTN LoRaWAN payload.
"""

import json
import boto3
from botocore.exceptions import ClientError

client = boto3.client("iot-data")

def lambda_handler(event, context):
    """ Update reported state of thing in device shadow with LoRaWAN payload """
    _data = {"state": {"reported": event}}
    try:
        response = client.update_thing_shadow(
            thingName = event["dev_id"],
            payload = json.dumps(_data)
        )
    except ClientError as ex:
        print(ex.response["Error"]["Message"])
    else:
        print(_response, _data)