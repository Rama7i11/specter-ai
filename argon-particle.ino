#include "Particle.h"
#include "LiquidCrystal_I2C_Spark.h"

SYSTEM_MODE(AUTOMATIC);
SYSTEM_THREAD(ENABLED);

LiquidCrystal_I2C *lcd;

// Pins
const int BUTTON_PIN = D2;
const int BUZZER_PIN = D3;
const int RED_LED = D4;
const int GREEN_LED = D5;
const int POT_PIN = A1;

// Timing
unsigned long lastButtonPress = 0;
unsigned long lastHeartbeat = 0;
unsigned long lastModeCheck = 0;

const unsigned long debounceDelay = 350;
const unsigned long heartbeatInterval = 15000;
const unsigned long modeCheckInterval = 250;

// State
String currentMode = "MONITOR";
String lastMode = "";
String latestIP = "0.0.0.0";
String latestAlert = "NONE";
int latestSeverity = 0;
int attackCount = 0;
bool showingCriticalScreen = false;

// Function declarations
void beep(int durationMs);
void alertBuzz();
void successBuzz();
void setRedLED(bool state);
void updateModeFromKnob();
void showIdleScreen();
void showModeScreen();
void showAlert(String alertType, String ip, int severity);
void showDefenseExecuting();
void showDefenseSuccess();
void showDefenseDenied(String reason);
void showIncomingBriefing();
void sendHeartbeat();
void printLineScroll(int row, String text, int delayMs = 250);

int receiveAlert(String data);
int receiveDefenseExecuting(String data);
int receiveDefenseSuccess(String data);
int receiveDefenseDenied(String data);
int receiveBriefing(String data);

void setup() {
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    pinMode(BUZZER_PIN, OUTPUT);
    pinMode(RED_LED, OUTPUT);
    pinMode(GREEN_LED, OUTPUT);
    pinMode(POT_PIN, INPUT);

    digitalWrite(BUZZER_PIN, LOW);
    digitalWrite(RED_LED, LOW);
    digitalWrite(GREEN_LED, LOW);

    Particle.function("alert", receiveAlert);
    Particle.function("executing", receiveDefenseExecuting);
    Particle.function("defenseOK", receiveDefenseSuccess);
    Particle.function("denied", receiveDefenseDenied);
    Particle.function("briefing", receiveBriefing);

    lcd = new LiquidCrystal_I2C(0x27, 16, 2);
    lcd->init();
    lcd->backlight();

    lcd->clear();
    lcd->setCursor(0, 0);
    lcd->print("SPECTER-AI");
    lcd->setCursor(0, 1);
    lcd->print("WEARABLE SOC");

    delay(1500);

    updateModeFromKnob();
    lastMode = currentMode;
    showIdleScreen();
}

void loop() {
    // Wake button
    if (digitalRead(BUTTON_PIN) == LOW) {
        if (millis() - lastButtonPress > debounceDelay) {
            lastButtonPress = millis();

            lcd->clear();
            lcd->setCursor(0, 0);
            lcd->print("WAKE SIGNAL");
            lcd->setCursor(0, 1);
            lcd->print("AI LISTENING");

            digitalWrite(GREEN_LED, HIGH);
            successBuzz();

            Particle.publish("aegis/wake_ai", "wake_specter_ai", PRIVATE);

            delay(1200);
            digitalWrite(GREEN_LED, LOW);
            showIdleScreen();
        }
    }

    // Mode dial
    if (millis() - lastModeCheck > modeCheckInterval) {
        lastModeCheck = millis();
        updateModeFromKnob();

        if (currentMode != lastMode && !showingCriticalScreen) {
            lastMode = currentMode;
            showModeScreen();
            Particle.publish("aegis/mode_change", currentMode, PRIVATE);
            delay(1000);
            showIdleScreen();
        }
    }

    // Heartbeat
    if (millis() - lastHeartbeat > heartbeatInterval) {
        lastHeartbeat = millis();
        sendHeartbeat();
    }
}

void updateModeFromKnob() {
    int value = analogRead(POT_PIN);

    if (value < 1300) {
        currentMode = "MONITOR";
    } else if (value < 2700) {
        currentMode = "ALERT_ONLY";
    } else {
        currentMode = "DEFENSE_READY";
    }
}

void showIdleScreen() {
    showingCriticalScreen = false;

    lcd->clear();
    lcd->setCursor(0, 0);
    lcd->print("SPECTER-AI");

    lcd->setCursor(0, 1);
    printLineScroll(1, "MODE:" + currentMode, 200);
}

void showModeScreen() {
    lcd->clear();
    lcd->setCursor(0, 0);
    lcd->print("AUTH MODE:");

    lcd->setCursor(0, 1);
    printLineScroll(1, currentMode, 200);
}

int receiveAlert(String data) {
    // Expected:
    // SQL_INJECTION,192.168.1.55,10

    int firstComma = data.indexOf(',');
    int secondComma = data.indexOf(',', firstComma + 1);

    if (firstComma == -1 || secondComma == -1) {
        return -1;
    }

    latestAlert = data.substring(0, firstComma);
    latestIP = data.substring(firstComma + 1, secondComma);
    latestSeverity = data.substring(secondComma + 1).toInt();
    attackCount++;

    showAlert(latestAlert, latestIP, latestSeverity);

    Particle.publish("aegis/alert_received", data, PRIVATE);

    return 1;
}

int receiveDefenseExecuting(String data) {
    updateModeFromKnob();

    if (currentMode != "DEFENSE_READY") {
        showDefenseDenied("MODE:" + currentMode);
        Particle.publish("aegis/defense_denied", "MODE_NOT_READY:" + currentMode, PRIVATE);
        return -2;
    }

    showDefenseExecuting();
    Particle.publish("aegis/defense_executing", data, PRIVATE);

    return 1;
}

int receiveDefenseSuccess(String data) {
    showDefenseSuccess();
    Particle.publish("aegis/defense_confirmed", data, PRIVATE);
    return 1;
}

int receiveDefenseDenied(String data) {
    // Example data:
    // MODE_MONITOR_REQUIRED_DEFENSE_READY
    // MODE_ALERT_ONLY_REQUIRED_DEFENSE_READY

    String displayReason = "MODE:" + currentMode;

    if (data.indexOf("MODE_MONITOR") >= 0) {
        displayReason = "MODE:MONITOR";
    } else if (data.indexOf("MODE_ALERT_ONLY") >= 0) {
        displayReason = "MODE:ALERT_ONLY";
    } else if (data.indexOf("MODE_DEFENSE_READY") >= 0) {
        displayReason = "MODE:DEFENSE_READY";
    }

    showDefenseDenied(displayReason);
    Particle.publish("aegis/defense_denied", data, PRIVATE);
    return 1;
}

int receiveBriefing(String data) {
    showIncomingBriefing();
    Particle.publish("aegis/briefing_displayed", data, PRIVATE);
    return 1;
}

void showAlert(String alertType, String ip, int severity) {
    showingCriticalScreen = true;

    lcd->clear();
    lcd->setCursor(0, 0);
    lcd->print("ATTACK DETECTED");

    if (alertType == "SQL_INJECTION") {
        printLineScroll(1, "SQL INJ:" + ip, 220);
    } else {
        printLineScroll(1, "THREAT:" + ip, 220);
    }

    int pulses = constrain(severity, 3, 10);

    for (int i = 0; i < pulses; i++) {
        setRedLED(true);
        alertBuzz();
        setRedLED(false);
        delay(100);
    }

    lcd->clear();
    lcd->setCursor(0, 0);
    lcd->print("AI AWAITING");

    printLineScroll(1, "AUTH:" + currentMode, 220);

    delay(3500);
    showIdleScreen();
}

void showDefenseExecuting() {
    showingCriticalScreen = true;

    lcd->clear();
    lcd->setCursor(0, 0);
    lcd->print("DEPLOYING");
    lcd->setCursor(0, 1);
    lcd->print("DEFENSE...");

    setRedLED(true);
    alertBuzz();
    delay(300);
    setRedLED(false);

    delay(2000);
    showIdleScreen();
}

void showDefenseSuccess() {
    showingCriticalScreen = true;

    setRedLED(false);
    digitalWrite(BUZZER_PIN, LOW);

    lcd->clear();
    lcd->setCursor(0, 0);
    lcd->print("THREAT BLOCKED");
    lcd->setCursor(0, 1);
    lcd->print("SYSTEM SAFE");

    digitalWrite(GREEN_LED, HIGH);
    successBuzz();

    delay(3000);

    digitalWrite(GREEN_LED, LOW);
    showIdleScreen();
}

void showDefenseDenied(String reason) {
    showingCriticalScreen = true;

    lcd->clear();
    lcd->setCursor(0, 0);
    lcd->print("ACCESS DENIED");

    printLineScroll(1, reason, 220);

    for (int i = 0; i < 3; i++) {
        setRedLED(true);
        beep(90);
        setRedLED(false);
        delay(120);
    }

    delay(2500);
    showIdleScreen();
}

void showIncomingBriefing() {
    showingCriticalScreen = true;

    lcd->clear();
    lcd->setCursor(0, 0);
    lcd->print("INCOMING");
    lcd->setCursor(0, 1);
    lcd->print("BRIEFING...");

    digitalWrite(GREEN_LED, HIGH);
    beep(150);
    delay(150);
    digitalWrite(GREEN_LED, LOW);

    delay(2500);
    showIdleScreen();
}

void sendHeartbeat() {
    String msg = String::format(
        "{\"device\":\"argon\",\"project\":\"Specter-AI\",\"status\":\"online\",\"mode\":\"%s\",\"ip\":\"%s\"}",
        currentMode.c_str(),
        latestIP.c_str()
    );

    Particle.publish("aegis/heartbeat", msg, PRIVATE);
}

void printLineScroll(int row, String text, int delayMs) {
    if (text.length() <= 16) {
        lcd->setCursor(0, row);
        lcd->print("                ");
        lcd->setCursor(0, row);
        lcd->print(text);
        return;
    }

    for (int i = 0; i <= text.length() - 16; i++) {
        lcd->setCursor(0, row);
        lcd->print(text.substring(i, i + 16));
        delay(delayMs);
    }
}

void setRedLED(bool state) {
    digitalWrite(RED_LED, state ? HIGH : LOW);
}

void alertBuzz() {
    beep(80);
    delay(80);
    beep(80);
}

void successBuzz() {
    beep(280);
}

void beep(int durationMs) {
    unsigned long start = millis();

    while (millis() - start < durationMs) {
        digitalWrite(BUZZER_PIN, HIGH);
        delayMicroseconds(250);
        digitalWrite(BUZZER_PIN, LOW);
        delayMicroseconds(250);
    }
}
