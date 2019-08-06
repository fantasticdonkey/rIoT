Elasticsearch Indexes
===============

**riot-trackers**

Payloads received from TTN (LoRaWAN) are stored in this index.

- **payload_fields.location** is explicitly defined as a **geo_point** type to ensure it can be used in mapping.

.. code-block:: JSON
	PUT riot-trackers
	{
	  "mappings": {
	    "dev_id": {
	      "properties": {
	        "timestamp": {
	          "type": "date",
	          "format": "yyyy-MM-dd HH:mm:ss"
	        },
	        "payload_fields.location": {
	          "type": "geo_point"
	        }
	      }
	    }
	  }
	}

