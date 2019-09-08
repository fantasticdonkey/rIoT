Go outdoors. Equipped with random homemade IoT gizmos. 'Cause we wanna. 

Overview
===============

Here are the major components of the project:

Trackers
---------------

Trackers are ESP32 development boards running MicroPython that are attached to:

- U-blox Neo-6 GPS receiver (UART interface)
- Semtech SX127X LoRa transceiver (SPI)
- Nordic Semiconductor nRF24L01+ transceiver (SPI)

In short, trackers periodically take GPS readings and broadcasts these out via LoRa (LoRaWAN) and 2.4 GHz radio.  For the remainder of the time, they will remain in deep sleep.

Trackers need to be small, lightweight and last over a day (ideally multiple) on a single battery charge. They also need to have zero dependencies on the remainder of the project.

Brick
---------------

Multiple trackers will send their GPS data to a single brick.  The brick will also take its own GPS readings, but also have other sensors attached as well.

The brick also runs a sqlite3 database to buffer payloads (both for itself and the trackers) and uploads them to AWS IOT via REST API when Internect connetion is detected.

A RF receiver application runs on the brick to receive payloads from the trackers using a nRF24L01+ receiver.

The Things Network (TTN)
---------------

A single application is configured in The Things Network, with our trackers registered. Any data received by an open, public LoRaWAN gateway for our application is dispatched to our AWS IoT Core instance using the TTN->AWS IoT integration. 

The tracker devices are only expected to perform an unconfirmed data upload operation.

AWS
---------------

AWS services - specifically AWS IoT - are being used to provide the following functionalities:

- **AWS IoT Core** is used to ingest data from the trackers. Data is further forwarded onto **AWS IoT Events** and **AWS Elasticsearch Service**.
- **AWS Elasticsearch Service** is used to store all data being received from the field.
- **AWS IoT Events** operates a detector model that monitors for non-responsive trackers. **AWS Simple Email Service** is used to dispatch notification emails relating to tracker state changes.

There are **AWS Lambda** functions deployed to perform integration between the services, such as for:

- Making shadow document updates for a device in **AWS IoT Core**.
- Sending notification emails to recipients using **AWS Simple Email Service**.

Project structure
===============

There is a number of directories storing files required by different aspects of the project. These are described below:

- **/tracker** - Contains MicroPython code that runs on the ESP32-based GPS tracker devices.
- **/ttn** - Contains code specific to The Things Network, such as the payload format decoder.
- **/aws-lambda** - Contains AWS Lambda functions in Python 3.X.
- **/brick** - Contains Python code running on the Raspberry Pi.
- **/docs** - Random glossy literature that would make a salesperson proud.

Further information
=============

The Semtech SX1276 LoRA transceiver datasheet can be found here:

- https://www.semtech.com/uploads/documents/DS_SX1276-7-8-9_W_APP_V6.pdf 

The LoRaWAN specification can be found here:

- https://lora-alliance.org/resource-hub/lorawantm-specification-v11
