""" riot-check-proximity.py
Lambda function to check if current GPS location is within the boundaries
of a known location stored in DynamoDB. Updates device's shadow document
with location information, and notifies all users registered in Cognito.
"""

import os
import json
import boto3
from botocore.exceptions import ClientError
import haversine

# Environment variables for AWS parameters
AWS_SES_SENDER = os.environ["AWS_SES_SENDER"]
AWS_REGION = os.environ["AWS_REGION_NAME"]
AWS_COGNITO_USERPOOL_ID = os.environ["AWS_COGNITO_USERPOOL_ID"]
# Boto3 clients for AWS resources
AWS_SES_CLIENT = boto3.client("ses", region_name=AWS_REGION)
AWS_IOT_CLIENT = boto3.client("iot-data", region_name=AWS_REGION)
AWS_COGNITO_IDP_CLIENT = boto3.client("cognito-idp", region_name=AWS_REGION)
AWS_DYNAMODB_CLIENT = boto3.resource("dynamodb")

def lambda_handler(event, context):
    """ Main Lambda function """
    thing_id = event["dev_id"]
    current_position = (event["position_lat"], event["position_long"])
    current_shadow = get_thing_shadow(thing_id)
    table = AWS_DYNAMODB_CLIENT.Table("riot-geo-data")
    geo_points = table.scan()["Items"]
    for geo_point in geo_points:
        _distance_km = haversine.haversine(
            (geo_point["latitude"], geo_point["longitude"]),
            current_position
        )
        if "current_location" not in current_shadow:
            current_shadow["current_location"] = ""
        if "previous_locations" not in current_shadow:
            current_shadow["previous_locations"] = []
        if _distance_km < geo_point["approach_distance_km"]:
            if str(geo_point["location"]) != str(current_shadow["current_location"]):
                send_notify_email(geo_point, current_shadow)
                current_shadow["current_location"] = geo_point["location"]
                if geo_point["location"] not in current_shadow["previous_locations"]:
                    current_shadow["previous_locations"].append(geo_point["location"])
                    print(current_shadow["previous_locations"])
                update_thing_shadow(thing_id, current_shadow)

def get_thing_shadow(dev_id):
    """ Retrieve AWS IoT thing's shadow document """
    current_shadow = json.loads(
        AWS_IOT_CLIENT.get_thing_shadow(
            thingName=dev_id
        )["payload"].read()
    )["state"]["reported"]
    print(current_shadow)
    return current_shadow

def update_thing_shadow(dev_id, data):
    """ Update the AWS IoT thing's shadow document """
    reported_data = {"state": {"reported": ""}}
    reported_data["state"]["reported"] = data
    AWS_IOT_CLIENT.update_thing_shadow(
        thingName=dev_id,
        payload=json.dumps(reported_data)
    )

def send_notify_email(geo_point, event):
    """ Notify all users registered in Cognito's user pool """
    # Obtain list of email recipients from Cognito
    cognito_users = AWS_COGNITO_IDP_CLIENT.list_users(
        UserPoolId=AWS_COGNITO_USERPOOL_ID,
        AttributesToGet=[
            "email",
        ],
        Limit=50
    )
    cognito_email_addresses = []
    for cognito_user in cognito_users["Users"]:
        cognito_email_addresses.append(cognito_user["Attributes"][0]["Value"])
    # Send status change email
    SUBJECT = "Reached: " + geo_point["name"] + "!"
    BODY_TEXT = geo_point["description"]
    BODY_HTML = """<html>
    <head></head>
    <body>
    <h1>""" + geo_point["message"] + """</h1>
    <h2>""" + event["timestamp"] + """ (<i>""" + event["dev_id"] + """</i>)</h2>
    <h3>Distance: """ + str(event["total_distance"]) + """ km,
    Time: """ + _seconds_to_hours_minutes(event["total_time"]) + """</h3>
    <p align=center><img style="width:80%; height:80%; border:none;" 
    src=\"""" + geo_point["image_url"] + """\"></p>
    <p>""" + geo_point["description"] + """</p>
    <p>For more information visit: """ + geo_point["url"] + """</p>
    </body>
    </html>
    """
    CHARSET = "UTF-8"
    try:
        response = AWS_SES_CLIENT.send_email(
            Destination={
                "ToAddresses": cognito_email_addresses,
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
    except ClientError as e:
        print(e.response["Error"]["Message"])
    else:
        print("Email sent! Message ID:", response["MessageId"])

def _seconds_to_hours_minutes(seconds):
    """ Converts seconds in integer to hours and minutes (in string) """
    hours, seconds = seconds // 3600, seconds % 3600
    minutes = seconds // 60
    hours_minutes_string = str(hours).zfill(2) + " hours " + str(minutes).zfill(2) + " minutes"
    return hours_minutes_string
