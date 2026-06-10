/*
 * GENSET sensor node — Wemos D1 mini
 * INA219 (voltage/current/power) + MPU6050 (acceleration/vibration)
 *
 * Publishes one plain number to each of FOUR topics, once per second:
 *     gen/voltage     e.g. 12.345    (V)
 *     gen/current     e.g. 250.500   (mA)
 *     gen/power       e.g. 3.092     (W)   power = V * I
 *     gen/vibration   e.g. 9.811     (m/s^2, acceleration magnitude)
 *
 * The dashboard subscribes to these same four topics (see app/config.py).
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
const char* mqtt_server     = "genmonitor.ddns.net";        // your broker IP
const int   mqtt_port       = 8000;
const char* mqtt_username   = "akbar";
const char* mqtt_password   = "akbar2026";
const char* mqtt_client_id  = "wemos-genset";        // make this unique per device

// One topic per measurement. Change the "gen" prefix here AND in the
// dashboard's .env (MQTT_TOPIC_PREFIX) to keep both sides matching.
const char* topic_voltage   = "gen/voltage";
const char* topic_current   = "gen/current";
const char* topic_power     = "gen/power";
const char* topic_vibration = "gen/vibration";

const unsigned long PUBLISH_INTERVAL_MS = 1000;      // publish rate

// ----------------------------- Globals ------------------------------------
Adafruit_INA219 ina219;
Adafruit_MPU6050 mpu;
WiFiClient espClient;
PubSubClient client(espClient);

bool mpuOk = false;
unsigned long lastPublish = 0;

// ----------------------------- Helpers ------------------------------------
// Publish a float as a plain string (e.g. 12.345). Returns false on failure.
bool publishFloat(const char* topic, float value) {
  char buf[24];
  snprintf(buf, sizeof(buf), "%.3f", value);
  bool ok = client.publish(topic, buf);
  Serial.print(topic);
  Serial.print(" = ");
  Serial.print(buf);
  Serial.println(ok ? "" : "  (PUBLISH FAILED)");
  return ok;
}

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
      Serial.print(client.state());   // negative = network, positive = protocol
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
    Serial.println("MPU6050 not found — vibration will report 0");
  }

  connectWiFi();

  client.setServer(mqtt_server, mqtt_port);
  client.setBufferSize(256);
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
  float power_W    = busV * current_mA / 1000.0;      // P = V * I  (V * mA / 1000 = W)

  // ----- Read MPU6050 -----
  float vibration = 0;
  if (mpuOk) {
    sensors_event_t a, g, temp;
    mpu.getEvent(&a, &g, &temp);
    float ax = a.acceleration.x;
    float ay = a.acceleration.y;
    float az = a.acceleration.z;
    // Magnitude of the acceleration vector (m/s^2).
    // NOTE: includes gravity, so it idles around 9.81 m/s^2 at rest.
    // For "vibration only", use: fabs(vibration - 9.81)
    vibration = sqrt(ax * ax + ay * ay + az * az);
  }

  // ----- Publish each value to its own topic -----
  Serial.println("---- publishing ----");
  publishFloat(topic_voltage,   busV);
  publishFloat(topic_current,   current_mA);
  publishFloat(topic_power,     power_W);
  publishFloat(topic_vibration, vibration);
}
