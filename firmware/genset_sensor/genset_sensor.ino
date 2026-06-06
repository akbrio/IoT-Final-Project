/*
 * GENSET sensor node — Wemos D1 mini
 * INA219 (voltage/current/power) + MPU6050 (acceleration/vibration)
 * Publishes one combined JSON message to MQTT topic "akbar" once per second.
 *
 * Payload shape (matches the dashboard's app/config.py):
 *   {"voltage":12.345,"current":250.500,"power":3.092,
 *    "accel":{"x":..,"y":..,"z":..},"vibration":9.811}
 *
 * Libraries (install via Library Manager):
 *   - PubSubClient (Nick O'Leary)
 *   - Adafruit INA219
 *   - Adafruit MPU6050  (+ Adafruit Unified Sensor, Adafruit BusIO)
 */

#include <Wire.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <Adafruit_INA219.h>
#include <Adafruit_MPU6050.h>

// ----------------------------- Configuration -----------------------------
const char* ssid           = "AAR";
const char* password        = "";                    // empty = open network
const char* mqtt_server     = "akbar.serveblog.net"; // must resolve to your broker IP
const int   mqtt_port       = 1883;
const char* mqtt_username   = "akbar";
const char* mqtt_password   = "akbar2026";
const char* mqtt_topic      = "akbar";
const char* mqtt_client_id  = "wemos-genset";        // make this unique per device

const unsigned long PUBLISH_INTERVAL_MS = 1000;      // publish rate

// ----------------------------- Globals ------------------------------------
Adafruit_INA219 ina219;
Adafruit_MPU6050 mpu;
WiFiClient espClient;
PubSubClient client(espClient);

bool mpuOk = false;
unsigned long lastPublish = 0;

// ----------------------------- WiFi ---------------------------------------
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.print("Connecting to WiFi");
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi connected, IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi connect timed out — will retry in loop()");
  }
}

// ----------------------------- MQTT ---------------------------------------
void connectMQTT() {
  if (WiFi.status() != WL_CONNECTED) return;

  while (!client.connected()) {
    Serial.print("Connecting to MQTT... ");
    if (client.connect(mqtt_client_id, mqtt_username, mqtt_password)) {
      Serial.println("connected");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());   // negative codes = network, positive = protocol
      Serial.println(" — retrying in 2s");
      delay(2000);
      if (WiFi.status() != WL_CONNECTED) return;  // bail out to fix WiFi first
    }
  }
}

// ----------------------------- Setup --------------------------------------
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println();
  Serial.println("Program started");

  Wire.begin(D2, D1);   // SDA=D2, SCL=D1 on the Wemos D1 mini

  if (!ina219.begin()) {
    Serial.println("INA219 not found — check wiring/address!");
  }
  mpuOk = mpu.begin();
  if (!mpuOk) {
    Serial.println("MPU6050 not found — vibration/accel will report 0");
  }

  connectWiFi();

  client.setServer(mqtt_server, mqtt_port);
  client.setBufferSize(512);   // headroom so the JSON is never dropped
  client.setKeepAlive(30);
  connectMQTT();
}

// ----------------------------- Loop ---------------------------------------
void loop() {
  // Keep the link healthy. These return quickly when already connected.
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  if (!client.connected())          connectMQTT();
  client.loop();   // must run every iteration for MQTT keepalive

  // Non-blocking pacing: only publish every PUBLISH_INTERVAL_MS.
  unsigned long now = millis();
  if (now - lastPublish < PUBLISH_INTERVAL_MS) return;
  lastPublish = now;

  // ----- Read INA219 -----
  float busV       = ina219.getBusVoltage_V();        // Volts
  float current_mA = ina219.getCurrent_mA();          // mA
  float power_W    = ina219.getPower_mW() / 1000.0;    // W (measured by the chip)

  // ----- Read MPU6050 -----
  float ax = 0, ay = 0, az = 0, vibration = 0;
  if (mpuOk) {
    sensors_event_t a, g, temp;
    mpu.getEvent(&a, &g, &temp);
    ax = a.acceleration.x;
    ay = a.acceleration.y;
    az = a.acceleration.z;
    // Magnitude of the acceleration vector (m/s^2).
    // NOTE: this includes gravity, so it idles around 9.81 m/s^2 at rest.
    // For "vibration only", use: fabs(vibration - 9.81)
    vibration = sqrt(ax * ax + ay * ay + az * az);
  }

  // ----- Build JSON -----
  char payload[256];
  int n = snprintf(payload, sizeof(payload),
    "{\"voltage\":%.3f,\"current\":%.3f,\"power\":%.3f,"
    "\"accel\":{\"x\":%.3f,\"y\":%.3f,\"z\":%.3f},\"vibration\":%.3f}",
    busV, current_mA, power_W, ax, ay, az, vibration);

  if (n < 0 || n >= (int)sizeof(payload)) {
    Serial.println("Payload truncated — skipping publish");
    return;
  }

  Serial.print("Payload: ");
  Serial.println(payload);

  if (!client.publish(mqtt_topic, payload)) {
    Serial.println("Publish failed (check buffer size / connection)");
  }
}
