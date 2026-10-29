// Edge 2 (OPSIONAL): ESP32 + MPU6050 + buzzer + tombol.
//  - publish accelerometer + gyroscope ke  fallguard/<PROJECT_ID>/edge2/sensor  (10 Hz)
//  - subscribe fallguard/<PROJECT_ID>/alert -> buzzer berbunyi sampai tombol ditekan
//  - tombol -> publish fallguard/<PROJECT_ID>/edge2/ack
//
// Library (Library Manager): "PubSubClient", "Adafruit MPU6050", "Adafruit Unified Sensor".
// Kabel: MPU6050 SDA->GPIO21, SCL->GPIO22, VCC->3V3, GND->GND
//        Buzzer aktif -> GPIO25 (+) dan GND, Tombol -> GPIO27 dan GND (INPUT_PULLUP)
// Salin secrets.h.example menjadi secrets.h lalu isi (secrets.h TIDAK di-commit).
// CATATAN: sketch ini belum dikompilasi di perangkat keras; uji dan sesuaikan pin Anda.

#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include "secrets.h"   // WIFI_SSID, WIFI_PASS, PROJECT_ID, MQTT_HOST

const int PIN_BUZZER = 25;
const int PIN_BUTTON = 27;

WiFiClient net;
PubSubClient mqtt(net);
Adafruit_MPU6050 mpu;

char tSensor[96], tAlert[96], tAck[96], tStatus[96];
volatile bool alarmOn = false;
unsigned long lastSend = 0;

void onMessage(char* topic, byte* payload, unsigned int len) {
  char buf[256];
  unsigned int n = len < sizeof(buf) - 1 ? len : sizeof(buf) - 1;
  memcpy(buf, payload, n);
  buf[n] = 0;
  if (strstr(buf, "\"FALL\"")) alarmOn = true;
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) delay(300);
}

void connectMqtt() {
  while (!mqtt.connected()) {
    String cid = "fg-edge2-" + String((uint32_t)ESP.getEfuseMac(), HEX);
    if (mqtt.connect(cid.c_str(), tStatus, 0, true, "offline")) {
      mqtt.publish(tStatus, "online", true);
      mqtt.subscribe(tAlert);
    } else {
      delay(1500);
    }
  }
}

void setup() {
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  snprintf(tSensor, sizeof(tSensor), "fallguard/%s/edge2/sensor", PROJECT_ID);
  snprintf(tAlert, sizeof(tAlert), "fallguard/%s/alert", PROJECT_ID);
  snprintf(tAck, sizeof(tAck), "fallguard/%s/edge2/ack", PROJECT_ID);
  snprintf(tStatus, sizeof(tStatus), "fallguard/%s/edge2/status", PROJECT_ID);

  Wire.begin(21, 22);
  if (!mpu.begin()) { while (true) delay(1000); }   // MPU6050 tidak terdeteksi: periksa kabel
  mpu.setAccelerometerRange(MPU6050_RANGE_16_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);

  connectWifi();
  mqtt.setServer(MQTT_HOST, 1883);
  mqtt.setCallback(onMessage);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWifi();
  if (!mqtt.connected()) connectMqtt();
  mqtt.loop();

  digitalWrite(PIN_BUZZER, alarmOn && ((millis() / 400) % 2 == 0) ? HIGH : LOW);
  if (alarmOn && digitalRead(PIN_BUTTON) == LOW) {
    alarmOn = false;
    digitalWrite(PIN_BUZZER, LOW);
    mqtt.publish(tAck, "{\"device\":\"edge2\",\"ok\":true}");
    delay(300);
  }

  if (millis() - lastSend >= 100) {   // 10 Hz
    lastSend = millis();
    sensors_event_t a, g, temp;
    mpu.getEvent(&a, &g, &temp);        // a: m/s^2, g: rad/s
    float mag = sqrtf(a.acceleration.x * a.acceleration.x +
                      a.acceleration.y * a.acceleration.y +
                      a.acceleration.z * a.acceleration.z);
    float gyro = sqrtf(g.gyro.x * g.gyro.x + g.gyro.y * g.gyro.y + g.gyro.z * g.gyro.z);
    char msg[200];
    snprintf(msg, sizeof(msg),
             "{\"device\":\"edge2\",\"t\":%lu,\"ax\":%.3f,\"ay\":%.3f,\"az\":%.3f,\"mag\":%.3f,\"gyro\":%.3f}",
             millis(), a.acceleration.x, a.acceleration.y, a.acceleration.z, mag, gyro);
    mqtt.publish(tSensor, msg);
  }
}
