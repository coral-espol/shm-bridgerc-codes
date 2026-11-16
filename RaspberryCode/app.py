
import os
import csv
import time
import math
import threading
from collections import deque
from datetime import datetime

import numpy as np
import cv2
import serial

from scipy.signal import hilbert
from gpiozero import DigitalInputDevice
from flask import Flask, jsonify, render_template, Response, send_from_directory
from ai_edge_litert.interpreter import Interpreter


app = Flask(__name__)

# ==========================================
# RUTAS Y PARÁMETROS DEL SISTEMA
# ==========================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CARPETA_CAPTURAS = os.path.join(BASE_DIR, "capturas")
CSV_REGISTRO = os.path.join(BASE_DIR, "danos_puente.csv")
MODEL_PATH = os.path.join(BASE_DIR, "modelo_shm_multiclase.tflite")

LONGITUD_PUENTE_M = 1.0
UMBRAL_CONFIANZA_CAPTURA = 85.0
MODO_INVERTIR_COLOR = True

os.makedirs(CARPETA_CAPTURAS, exist_ok=True)

if not os.path.exists(CSV_REGISTRO):
    with open(CSV_REGISTRO, mode="w", newline="") as f:
        csv.writer(f).writerow([
            "Timestamp", "Sentido", "Distancia_Acumulada_m",
            "Posicion_Puente_X_m", "Tipo_Defecto", "Confianza_IA",
            "Vib_Acel_m_s2", "Frec_Hilbert_Hz", "Ruta_Foto",
            "Latitud", "Longitud", "Satelites"
        ])


# ==========================================
# 1. MOTOR IA LITERT / TFLITE
# ==========================================

interpreter = None
input_details = None
output_details = None

try:
    if os.path.exists(MODEL_PATH):
        interpreter = Interpreter(
            model_path=MODEL_PATH,
            num_threads=1
        )
        interpreter.allocate_tensors()

        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()

except Exception as e:
    print("Error al cargar el modelo IA:", e)


# ==========================================
# 2. ODOMETRÍA LM393
# ==========================================

METROS_POR_PULSO = (math.pi * 0.065) / 20


class OdometriaRobot:

    def __init__(self):

        self.sensor = DigitalInputDevice(10, pull_up=True)

        self.pt = 0
        self.ptr = 0

        self.bd = False
        self.bf = False

        self.tu = 0
        self.tc = time.time()

        self.pp = 0
        self.vel = 0.0

        self.sen = "IDA"

        threading.Thread(
            target=self._loop,
            daemon=True
        ).start()

    def _loop(self):

        while True:

            v = self.sensor.value
            t = time.time()

            if v == 0 and not self.bd:

                if (t - self.tu) > 0.008:

                    self.bd = True
                    self.tu = t

                    if not self.bf:

                        self.pt += 1
                        self.ptr += 1

                        if (self.ptr * METROS_POR_PULSO) >= LONGITUD_PUENTE_M:
                            self.bf = True

            elif v == 1 and self.bd:

                if (t - self.tu) > 0.008:
                    self.bd = False
                    self.tu = t

            time.sleep(0.004)

    def cambiar_sentido(self, n):

        if n != self.sen:

            self.ptr = 0
            self.bf = False
            self.sen = n
            self.tc = time.time()
            self.pp = self.pt

    def reiniciar(self):

        self.pt = 0
        self.ptr = 0
        self.bf = False
        self.pp = 0
        self.tc = time.time()
        self.vel = 0.0
        self.sen = "IDA"

    def obtener_telemetria(self):

        t = time.time()

        if (t - self.tc) >= 0.25:

            self.vel = (
                ((self.pt - self.pp) * METROS_POR_PULSO) /
                (t - self.tc)
                if not self.bf else 0.0
            )

            self.pp = self.pt
            self.tc = t

        dt = self.pt * METROS_POR_PULSO
        dtr = self.ptr * METROS_POR_PULSO

        if self.sen == "IDA":
            pp = min(dtr, LONGITUD_PUENTE_M)
        else:
            pp = max(LONGITUD_PUENTE_M - dtr, 0.0)

        return {
            "distancia_total_m": round(dt, 3),
            "posicion_puente_m": round(pp, 3),
            "velocidad_ms": round(self.vel, 2),
            "sentido": self.sen,
            "bloqueado": self.bf
        }


odometria = OdometriaRobot()


# ==========================================
# 3. GPS
# ==========================================

class LectorGPS:

    def __init__(self):

        self.latitud = None
        self.longitud = None
        self.satelites = 0
        self.fijado = False

        try:

            self.ser = serial.Serial(
                "/dev/serial0",
                9600,
                timeout=1.0
            )

            threading.Thread(
                target=self._loop,
                daemon=True
            ).start()

        except Exception as e:

            print("GPS no disponible:", e)
            self.ser = None

    def _loop(self):

        while self.ser:

            try:

                l = self.ser.readline().decode(
                    "ascii", "replace"
                ).strip()

                if l.startswith("$GPGGA") or l.startswith("$GNGGA"):

                    p = l.split(",")

                    if len(p) > 7:

                        self.satelites = (
                            int(p[7]) if p[7].isdigit() else 0
                        )

                        self.fijado = p[6] != "0"

                        if p[2] and p[4]:

                            rl = float(p[2])
                            rlo = float(p[4])

                            dl = int(rl / 100)
                            dlo = int(rlo / 100)

                            self.latitud = (
                                dl + (rl - dl * 100) / 60
                            ) * (-1 if p[3] == "S" else 1)

                            self.longitud = (
                                dlo + (rlo - dlo * 100) / 60
                            ) * (-1 if p[5] == "W" else 1)

            except Exception:
                pass

            time.sleep(0.1)

    def obtener_datos(self):

        return {
            "latitud": self.latitud,
            "longitud": self.longitud,
            "satelites": self.satelites,
            "fijado": self.fijado
        }


gps = LectorGPS()


# ==========================================
# 4. SENSOR ADXL345
# ==========================================

try:

    import board
    import busio
    import adafruit_adxl34x

    accelerometer = adafruit_adxl34x.ADXL345(
        busio.I2C(board.SCL, board.SDA)
    )

except Exception as e:

    print("ADXL345 no disponible:", e)
    accelerometer = None


historial_vibracion = []
fs = 20.0

ultima_vibracion_val = 0.0
ultima_frecuencia_val = 0.0


def loop_vibracion():

    global historial_vibracion
    global ultima_vibracion_val

    while True:

        try:

            if accelerometer:

                z = accelerometer.acceleration[2] - 9.81

            else:

                z = (
                    0.8 * math.sin(2 * math.pi * 3.5 * time.time())
                    + 0.2 * np.random.randn()
                )

        except Exception:

            z = 0.0

        ultima_vibracion_val = round(z, 2)

        historial_vibracion.append(z)

        if len(historial_vibracion) > 40:
            historial_vibracion.pop(0)

        time.sleep(1.0 / fs)


threading.Thread(
    target=loop_vibracion,
    daemon=True
).start()


# ==========================================
# 5. REGISTRO DE FALLAS
# ==========================================

fallas_detectadas = []
ultimo_registro_falla = 0


def capturar_y_registrar_falla(
    dt, pp, tipo, conf, fbgr, gps_d, sen
):

    global ultimo_registro_falla

    if time.time() - ultimo_registro_falla > 3.0:

        ultimo_registro_falla = time.time()

        nf = (
            f"{tipo.lower()}tot{int(dt * 1000)}mm"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        )

        ra = os.path.join(CARPETA_CAPTURAS, nf)

        falla = {
            "hora": datetime.now().strftime("%H:%M:%S"),
            "sentido": sen,
            "dist_total_m": round(dt, 3),
            "pos_puente_m": round(pp, 3),
            "tipo": tipo,
            "confianza": f"{int(conf)}%",
            "acel_z": ultima_vibracion_val,
            "frec_hz": ultima_frecuencia_val,
            "foto": f"/capturas/{nf}",
            "lat": gps_d["latitud"],
            "lon": gps_d["longitud"],
            "sats": gps_d["satelites"]
        }

        fallas_detectadas.append(falla)

        def save():

            try:

                cv2.imwrite(
                    ra,
                    fbgr,
                    [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                )

            except Exception:
                pass

            try:

                with open(CSV_REGISTRO, "a", newline="") as f:

                    csv.writer(f).writerow([
                        falla["hora"],
                        falla["sentido"],
                        falla["dist_total_m"],
                        falla["pos_puente_m"],
                        falla["tipo"],
                        falla["confianza"],
                        falla["acel_z"],
                        falla["frec_hz"],
                        falla["foto"],
                        falla["lat"],
                        falla["lon"],
                        falla["sats"]
                    ])

            except Exception:
                pass

        threading.Thread(
            target=save,
            daemon=True
        ).start()


# ==========================================
# 6. FILTRO OPENCV
# ==========================================

def verificar_corrosion_estructural(roi_bgr):

    hsv = cv2.cvtColor(
        roi_bgr,
        cv2.COLOR_BGR2HSV
    )

    mascara_oxido = cv2.inRange(
        hsv,
        np.array([0, 50, 40]),
        np.array([25, 255, 255])
    )

    gray = cv2.cvtColor(
        roi_bgr,
        cv2.COLOR_BGR2GRAY
    )

    bordes = cv2.Canny(
        gray,
        60,
        150
    )

    bordes_gruesos = cv2.dilate(
        bordes,
        np.ones((3, 3), np.uint8),
        iterations=1
    )

    varillas_oxidadas = cv2.bitwise_and(
        mascara_oxido,
        bordes_gruesos
    )

    pixeles_validos = cv2.countNonZero(
        varillas_oxidadas
    )

    total_pixeles = (
        roi_bgr.shape[0] * roi_bgr.shape[1]
    )

    porcentaje = (
        pixeles_validos / total_pixeles
    ) * 100.0

    return porcentaje > 0.8


# ==========================================
# 7. CÁMARA
# ==========================================

ultimo_frame_bgr = None
ultimo_frame_roi = None

lock_frame = threading.Lock()


def inicializar_camara():

    try:

        from picamera2 import Picamera2

        cam = Picamera2()

        cam.configure(
            cam.create_preview_configuration(
                main={
                    "size": (480, 360),
                    "format": "RGB888"
                },
                controls={
                    "AwbEnable": True
                }
            )
        )

        cam.start()
        time.sleep(1)

        return "picam2", cam

    except Exception:
        pass

    try:

        cap = cv2.VideoCapture(
            0,
            cv2.CAP_V4L2
        )

        cap.set(3, 480)
        cap.set(4, 360)

        if cap.isOpened():
            return "cv2", cap

    except Exception:
        pass

    return "none", None


cam_tipo, cam_obj = inicializar_camara()


def hilo_captura_camara():

    global ultimo_frame_bgr
    global ultimo_frame_roi

    while True:

        frame = None

        if cam_tipo == "picam2":

            try:

                fr = cam_obj.capture_array()

                if fr is not None:

                    if MODO_INVERTIR_COLOR:
                        frame = cv2.cvtColor(
                            fr,
                            cv2.COLOR_RGB2BGR
                        )
                    else:
                        frame = fr.copy()

            except Exception:
                pass

        elif cam_tipo == "cv2":

            try:

                ret, fr = cam_obj.read()

                if ret and fr is not None:
                    frame = fr

            except Exception:
                pass

        if frame is not None:

            h, w = frame.shape[:2]

            y1 = int(h * 0.2)
            y2 = int(h * 0.9)

            x1 = int(w * 0.15)
            x2 = int(w * 0.85)

            with lock_frame:

                ultimo_frame_bgr = frame

                ultimo_frame_roi = frame[
                    y1:y2,
                    x1:x2
                ].copy()

        time.sleep(0.3)


threading.Thread(
    target=hilo_captura_camara,
    daemon=True
).start()


# ==========================================
# 8. INTELIGENCIA ARTIFICIAL
# ==========================================

ia_tipo_detectado = "SANO"
ia_confianza = 0.0

memoria_predicciones = deque(maxlen=4)


def worker_inferencia_ia():

    global ia_tipo_detectado
    global ia_confianza

    while True:

        roi = None
        frame_full = None

        with lock_frame:

            if ultimo_frame_roi is not None:

                roi = ultimo_frame_roi.copy()
                frame_full = ultimo_frame_bgr.copy()

        if roi is not None and interpreter is not None:

            try:

                roi_rgb = cv2.cvtColor(
                    roi,
                    cv2.COLOR_BGR2RGB
                )

                sh = input_details[0]["shape"]

                data = np.expand_dims(
                    cv2.resize(
                        roi_rgb,
                        (sh[2], sh[1])
                    ),
                    axis=0
                ).astype(input_details[0]["dtype"])

                interpreter.set_tensor(
                    input_details[0]["index"],
                    data
                )

                interpreter.invoke()

                pred = interpreter.get_tensor(
                    output_details[0]["index"]
                )[0]

                idx = int(np.argmax(pred))

                conf_max = (
                    float(pred[np.argmax(pred)]) * 100.0
                )

                etiq = "SANO"

                if conf_max >= UMBRAL_CONFIANZA_CAPTURA:

                    if idx == 1:

                        etiq = "FISURA"

                    elif idx == 0:

                        if verificar_corrosion_estructural(roi):
                            etiq = "CORROSION"
                        else:
                            etiq = "SANO"
                            conf_max = 99.0

                    else:

                        etiq = "SANO"

                memoria_predicciones.append(etiq)

                if memoria_predicciones.count("FISURA") >= 3:

                    ia_tipo_detectado = "FISURA"
                    ia_confianza = conf_max

                elif memoria_predicciones.count("CORROSION") >= 3:

                    ia_tipo_detectado = "CORROSION"
                    ia_confianza = conf_max

                else:

                    ia_tipo_detectado = "SANO"
                    ia_confianza = conf_max

                if ia_tipo_detectado in ["FISURA", "CORROSION"]:

                    h, w = frame_full.shape[:2]

                    y1 = int(h * 0.2)
                    y2 = int(h * 0.9)

                    x1 = int(w * 0.15)
                    x2 = int(w * 0.85)

                    color = (
                        (0, 0, 255)
                        if ia_tipo_detectado == "FISURA"
                        else (0, 255, 0)
                    )

                    cv2.rectangle(
                        frame_full,
                        (x1, y1),
                        (x2, y2),
                        color,
                        2
                    )

                    cv2.putText(
                        frame_full,
                        f"{ia_tipo_detectado} [{int(ia_confianza)}%]",
                        (x1, max(y1 - 8, 20)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        color,
                        2
                    )

                    od = odometria.obtener_telemetria()

                    capturar_y_registrar_falla(
                        od["distancia_total_m"],
                        od["posicion_puente_m"],
                        ia_tipo_detectado,
                        ia_confianza,
                        frame_full,
                        gps.obtener_datos(),
                        od["sentido"]
                    )

            except Exception as e:

                print("Error en inferencia IA:", e)

        time.sleep(0.8)


threading.Thread(
    target=worker_inferencia_ia,
    daemon=True
).start()


# ==========================================
# 9. STREAMING DE VIDEO
# ==========================================

def generar_frames():

    while True:

        frame = None

        with lock_frame:

            if ultimo_frame_bgr is not None:
                frame = ultimo_frame_bgr.copy()

        if frame is not None:

            h, w = frame.shape[:2]

            y1 = int(h * 0.2)
            y2 = int(h * 0.9)

            x1 = int(w * 0.15)
            x2 = int(w * 0.85)

            if ia_tipo_detectado == "FISURA":

                color = (0, 0, 255)

                texto = (
                    f"FISURA [{int(ia_confianza)}%]"
                )

                cv2.rectangle(
                    frame, (x1, y1), (x2, y2), color, 2
                )

                cv2.putText(
                    frame, texto,
                    (x1, max(y1 - 8, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, color, 2
                )

            elif ia_tipo_detectado == "CORROSION":

                color = (0, 255, 0)

                texto = (
                    f"CORROSION REAL [{int(ia_confianza)}%]"
                )

                cv2.rectangle(
                    frame, (x1, y1), (x2, y2), color, 2
                )

                cv2.putText(
                    frame, texto,
                    (x1, max(y1 - 8, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, color, 2
                )

            else:

                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    (40, 160, 40),
                    1
                )

                cv2.putText(
                    frame,
                    f"SANO [{int(ia_confianza)}%]",
                    (x1, max(y1 - 8, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (50, 220, 50),
                    1
                )

            ret, buffer = cv2.imencode(
                ".jpg",
                frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), 60]
            )

            if ret:

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + buffer.tobytes()
                    + b"\r\n"
                )

        else:

            time.sleep(0.1)

        time.sleep(0.4)


# ==========================================
# 10. RUTAS FLASK
# ==========================================

@app.route("/")
def index():

    return render_template("index.html")


@app.route("/video_feed")
def video_feed():

    return Response(
        generar_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/capturas/<path:filename>")
def servir_capturas(filename):

    return send_from_directory(
        CARPETA_CAPTURAS,
        filename
    )


@app.route("/api/sentido", methods=["POST"])
def api_sentido():

    from flask import request

    odometria.cambiar_sentido(
        request.get_json().get("sentido", "IDA")
    )

    return jsonify({"status": "ok"})


@app.route("/api/telemetria")
def api_telemetria():

    global ultima_frecuencia_val

    odom = odometria.obtener_telemetria()
    d_gps = gps.obtener_datos()

    r = np.array(
        historial_vibracion,
        dtype=float
    )

    t = list(range(len(r)))

    fi = [0.0] * len(r)
    env = r.tolist()

    if len(r) >= 12:

        try:

            a = hilbert(r)

            env = np.abs(a).tolist()

            fc = (
                np.diff(np.unwrap(np.angle(a)))
                / (2.0 * np.pi) * fs
            ).tolist()

            if len(fc) > 0:
                fc.insert(0, fc[0])

            if len(fc) < len(r):

                fi = fc + [0.0] * (
                    len(r) - len(fc)
                )

            else:

                fi = fc[:len(r)]

            ultima_frecuencia_val = round(
                fi[-1], 2
            )

        except Exception:
            pass

    return jsonify({
        "timestamp": time.time(),
        "odometria": odom,
        "gps": d_gps,
        "fallas": fallas_detectadas,
        "hilbert": {
            "t": t,
            "raw": r.tolist(),
            "envolvente": env,
            "frecuencia": fi
        }
    })


@app.route("/api/toggle_color", methods=["POST"])
def toggle():

    global MODO_INVERTIR_COLOR

    MODO_INVERTIR_COLOR = not MODO_INVERTIR_COLOR

    return jsonify({"ok": 1})


@app.route("/api/reset", methods=["POST"])
def rst():

    global fallas_detectadas
    global ultimo_registro_falla

    odometria.reiniciar()

    fallas_detectadas.clear()

    ultimo_registro_falla = 0

    return jsonify({"ok": 1})


# ==========================================
# 11. EJECUCIÓN DEL SERVIDOR
# ==========================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        threaded=True
    )
