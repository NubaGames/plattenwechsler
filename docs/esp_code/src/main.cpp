#include <Arduino.h>

#include "app/AppController.h"

static esp_schlitten::AppController app;

void setup() {
  app.begin();
}

void loop() {
  app.update();
}
