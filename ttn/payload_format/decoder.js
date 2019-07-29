function Decoder(bytes, port) {
  // Decode an uplink message from a buffer
  // (array) of bytes to an object of fields.
  var decoded = {};

  if (port === 1) {
    latitude = Number((bytes[0] - 90).toString().concat(".", ((bytes[1] << 16) + (bytes[2] << 8) + bytes[3]).toString()));
    console.log(latitude);
    longitude = Number((((bytes[4] << 8) +  bytes[5]) - 180).toString().concat(".", ((bytes[6] << 16) + (bytes[7] << 8) + bytes[8]).toString()));
    console.log(longitude);
    altitude = Number((bytes[9] << 8) +  bytes[10]);
    console.log(altitude);
    course = Number((bytes[11] << 8) +  bytes[12]) / 10;
    console.log(course);
    decoded.latitude = latitude;
    decoded.longitude = longitude;
    decoded.altitude = altitude;
    decoded.course = course;
  }

  return decoded;
}