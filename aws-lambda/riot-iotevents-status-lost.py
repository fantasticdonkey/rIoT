""" riot-iotevents-status-lost.py
AWS Lambda function to respond to IoT Events changing a tracker's state into
"lost" from any other state.  On entering this state, it does the following:

- Updates tracker's Shadow document in AWS IoT Core with the new state: lost.
- Sends notification email using AWS SES

Relies on environment variables being set up for the Lambda function, as well as
use of role with correct permissions for SES and AWS IoT.
"""

import os
import json
import boto3
from botocore.exceptions import ClientError

AWS_SES_SENDER = os.environ["AWS_SES_SENDER"]
AWS_SES_RECIPIENT = os.environ["AWS_SES_RECIPIENT"]
AWS_REGION = os.environ["AWS_REGION_NAME"]
AWS_SES_CLIENT = boto3.client("ses", region_name=AWS_REGION)
AWS_IOT_CLIENT = boto3.client("iot-data", region_name=AWS_REGION)

def lambda_handler(event, context):
    """ Single Lambda function to interface with SES and AWS IoT """
    # Send status change email
    SUBJECT = event["payload"]["detector"]["keyValue"] + " is lost"
    BODY_TEXT = (
        "Tracker " + event["payload"]["detector"]["keyValue"] + " is probably lost"
    )
    BODY_HTML = """<html>
    <head></head>
    <body>"""
    event["payload"]["detector"]["keyValue"] + ": tracker is probably lost" """
    </body>
    </html>
    """
    CHARSET = "UTF-8"
    try:
        response = AWS_SES_CLIENT.send_email(
            Destination={
                "ToAddresses": [
                    AWS_SES_RECIPIENT,
                ],
            },
            Message={
                "Body": {
                    "Html": {
                        "Charset": CHARSET,
                        "Data": BODY_HTML,
                    },
                    "Text": {
                        "Charset": CHARSET,
                        "Data": BODY_TEXT,
                    },
                },
                "Subject": {
                    "Charset": CHARSET,
                    "Data": SUBJECT,
                },
            },
            Source=AWS_SES_SENDER,
        )
    except ClientError as ex:
        print(ex.response["Error"]["Message"])
    else:
        print("Email sent! Message ID:", response["MessageId"])
    # Update reported state of tracker
    _data = {"state": {"reported": {"status": "responding"}}}
    try:
        _response = AWS_IOT_CLIENT.update_thing_shadow(
            thingName=event["payload"]["detector"]["keyValue"],
            payload=json.dumps(_data)
        )
    except ClientError as ex:
        print(ex.response["Error"]["Message"])
    else:
        print(_response, _data)
