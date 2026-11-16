#include <Bluepad32.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// =====================================================
// PINES Y CONFIGURACIÓN OLED
// =====================================================
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
#define SCREEN_ADDRESS 0x3C

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// Variable para evitar actualizar la pantalla innecesariamente
String estadoActualOLED = "";

ControllerPtr myControllers[BP32_MAX_GAMEPADS];

// =====================================================
// PINES L298N
// =====================================================
#define ENA 14
#define IN1 27
#define IN2 26
#define IN3 25
#define IN4 33
#define ENB 32

// =====================================================
// LEDS
// =====================================================
#define LED1 4
#define LED2 5

// =====================================================
// CONFIGURACIÓN DE VELOCIDAD
// 255 * 0.50 = 127
// =====================================================
#define MAX_SPEED 127

// =====================================================
// FUNCIONES DE MOTORES - L298N
// =====================================================

void motorA(int velocidad) {

  velocidad = constrain(velocidad, -MAX_SPEED, MAX_SPEED);

  if (velocidad > 0) {

    digitalWrite(IN1, HIGH);
    digitalWrite(IN2, LOW);
    analogWrite(ENA, velocidad);

  } 
  else if (velocidad < 0) {

    digitalWrite(IN1, LOW);
    digitalWrite(IN2, HIGH);
    analogWrite(ENA, -velocidad);

  } 
  else {

    digitalWrite(IN1, LOW);
    digitalWrite(IN2, LOW);
    analogWrite(ENA, 0);
  }
}


void motorB(int velocidad) {

  velocidad = constrain(velocidad, -MAX_SPEED, MAX_SPEED);

  if (velocidad > 0) {

    digitalWrite(IN3, HIGH);
    digitalWrite(IN4, LOW);
    analogWrite(ENB, velocidad);

  } 
  else if (velocidad < 0) {

    digitalWrite(IN3, LOW);
    digitalWrite(IN4, HIGH);
    analogWrite(ENB, -velocidad);

  } 
  else {

    digitalWrite(IN3, LOW);
    digitalWrite(IN4, LOW);
    analogWrite(ENB, 0);
  }
}


// =====================================================
// FRENO
// =====================================================

void freno() {

  analogWrite(ENA, 0);
  analogWrite(ENB, 0);

  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
}


// =====================================================
// DETENER
// =====================================================

void detener() {

  motorA(0);
  motorB(0);
}


// =====================================================
// ACTUALIZAR PANTALLA OLED
// =====================================================

void actualizarOLED(String estado, int bateria = -1) {

  // Evita redibujar si el estado no cambió
  if (estado == estadoActualOLED) {
    return;
  }

  estadoActualOLED = estado;

  display.clearDisplay();

  // Texto principal
  display.setTextSize(2);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 15);
  display.println(estado);

  // Batería del mando
  if (bateria >= 0) {

    display.setTextSize(1);
    display.setCursor(0, 50);

    display.print("Bat. Mando: ");
    display.print(bateria);
    display.println("%");
  }

  display.display();
}


// =====================================================
// CONTROL DEL CARRO
// =====================================================

void controlarCarro(ControllerPtr ctl) {

  // ===================================================
  // LED 1 - BOTÓN L1
  // ===================================================

  digitalWrite(LED1, ctl->l1() ? HIGH : LOW);


  // ===================================================
  // LED 2 - BOTÓN R1
  // ===================================================

  digitalWrite(LED2, ctl->r1() ? HIGH : LOW);


  // ===================================================
  // R2 = FRENO PRIORITARIO
  // ===================================================

  if (ctl->r2()) {

    freno();

    actualizarOLED("FRENANDO", ctl->battery());

    return;
  }


  // ===================================================
  // LECTURA DEL D-PAD
  // ===================================================

  uint8_t dpad = ctl->dpad();


  // ===================================================
  // ADELANTE
  // ===================================================

  if (dpad & 0x01) {

    motorA(MAX_SPEED);
    motorB(MAX_SPEED);

    actualizarOLED("ADELANTE", ctl->battery());
  }


  // ===================================================
  // ATRÁS
  // ===================================================

  else if (dpad & 0x02) {

    motorA(-MAX_SPEED);
    motorB(-MAX_SPEED);

    actualizarOLED("ATRAS", ctl->battery());
  }


  // ===================================================
  // IZQUIERDA
  // ===================================================

  else if (dpad & 0x08) {

    motorA(-MAX_SPEED);
    motorB(MAX_SPEED);

    actualizarOLED("IZQUIERDA", ctl->battery());
  }


  // ===================================================
  // DERECHA
  // ===================================================

  else if (dpad & 0x04) {

    motorA(MAX_SPEED);
    motorB(-MAX_SPEED);

    actualizarOLED("DERECHA", ctl->battery());
  }


  // ===================================================
  // SIN MOVIMIENTO
  // ===================================================

  else {

    detener();

    actualizarOLED("CONECTADO", ctl->battery());
  }
}


// =====================================================
// CUANDO SE CONECTA EL CONTROL
// =====================================================

void onConnectedController(ControllerPtr ctl) {

  for (int i = 0; i < BP32_MAX_GAMEPADS; i++) {

    if (myControllers[i] == nullptr) {

      Serial.printf(
        "CONTROL CONECTADO - index=%d\n",
        i
      );

      myControllers[i] = ctl;

      actualizarOLED(
        "CONECTADO",
        ctl->battery()
      );

      break;
    }
  }
}


// =====================================================
// CUANDO SE DESCONECTA EL CONTROL
// =====================================================

void onDisconnectedController(ControllerPtr ctl) {

  for (int i = 0; i < BP32_MAX_GAMEPADS; i++) {

    if (myControllers[i] == ctl) {

      Serial.printf(
        "CONTROL DESCONECTADO - index=%d\n",
        i
      );

      myControllers[i] = nullptr;

      // Detener inmediatamente los motores
      freno();

      // Apagar LEDs
      digitalWrite(LED1, LOW);
      digitalWrite(LED2, LOW);

      actualizarOLED(
        "ESPERANDO\nMANDO..."
      );

      break;
    }
  }
}


// =====================================================
// PROCESAR CONTROLADORES
// =====================================================

void processControllers() {

  for (auto myController : myControllers) {

    if (myController &&
        myController->isConnected()) {

      if (myController->isGamepad()) {

        controlarCarro(myController);
      }
    }
  }
}


// =====================================================
// SETUP
// =====================================================

void setup() {

  Serial.begin(115200);


  // ===================================================
  // I2C OLED
  // SDA = GPIO 21
  // SCL = GPIO 22
  // ===================================================

  Wire.begin(21, 22);


  // ===================================================
  // INICIALIZAR OLED
  // ===================================================

  if (!display.begin(
        SSD1306_SWITCHCAPVCC,
        SCREEN_ADDRESS)) {

    Serial.println(
      F("Fallo al iniciar OLED. Revisa conexiones.")
    );

  } 
  else {

    display.clearDisplay();

    display.setTextSize(2);
    display.setTextColor(SSD1306_WHITE);

    display.setCursor(0, 15);

    display.println("INICIANDO...");

    display.display();

    delay(1000);
  }


  // ===================================================
  // CONFIGURAR PINES L298N
  // ===================================================

  pinMode(ENA, OUTPUT);

  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);

  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);

  pinMode(ENB, OUTPUT);


  // ===================================================
  // CONFIGURAR LEDs
  // ===================================================

  pinMode(LED1, OUTPUT);
  pinMode(LED2, OUTPUT);

  digitalWrite(LED1, LOW);
  digitalWrite(LED2, LOW);


  // ===================================================
  // MOTORES DETENIDOS AL INICIAR
  // ===================================================

  freno();


  // ===================================================
  // INICIAR BLUEPAD32
  // ===================================================

  BP32.setup(
    &onConnectedController,
    &onDisconnectedController
  );


  // ===================================================
  // MENSAJE INICIAL
  // ===================================================

  actualizarOLED(
    "ESPERANDO\nMANDO..."
  );

  Serial.println(
    "Sistema listo. Esperando control..."
  );
}


// =====================================================
// LOOP PRINCIPAL
// =====================================================

void loop() {

  // Actualizar Bluepad32
  BP32.update();

  // Procesar controles
  processControllers();

  // Pequeña pausa para estabilidad
  delay(20);
}