""" riot-iotevents-status.py
Lambda function to respond to IoT Events changing state of a device. Does the following:
-Update device shadow of tracker with latest state
-Sends notification email using AWS SES
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
    """ Main Lambda function to action notification events """
    thing_name = str(event["payload"]["detector"]["keyValue"])
    state_name = event["payload"]["state"]["stateName"]
    print("Thing:", thing_name)
    # Update reported state of tracker
    _data = {"state": {"reported": {"status": state_name}}}
    _response = AWS_IOT_CLIENT.update_thing_shadow(
        thingName=thing_name,
        payload=json.dumps(_data)
    )
    print(_response, _data)
    _current_shadow = json.loads(AWS_IOT_CLIENT.get_thing_shadow(
        thingName=thing_name
    )["payload"].read())["state"]["reported"]
    print(_current_shadow)
    # Send status change email
    if state_name == "responding":
        SUBJECT = "Happy days! " + event["payload"]["detector"]["keyValue"] + " is alive and well."
    elif state_name == "not-responding":
        SUBJECT = "Oh no! We've not heard from " +\
        event["payload"]["detector"]["keyValue"] + " in a while..."
    elif state_name == "lost":
        SUBJECT = "Oops! " + event["payload"]["detector"]["keyValue"] + " appears to be lost."
    BODY_TEXT = "Last reported data: " + str(_current_shadow)
    BODY_HTML = """<html>
    <head></head>
    <body>
    <h1>""" + SUBJECT + """</h1>
    Last reported data: """ + str(_current_shadow) + """.
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
