import RPi.GPIO as GPIO
import bluetooth
import time
import cv2
import numpy as np
import threading
from picamera2 import Picamera2
from gpiozero import Button  # Note : Plus utilisé pour le switch

# =============================================================================
# Configuration des broches GPIO
# =============================================================================
# Moteur horizontal (rotation continue ou commande BLE)
DIR1 = 5       # Broche direction du moteur horizontal
STEP1 = 6      # Broche pour les pas du moteur horizontal  
ENABLE1 = 13   # Broche enable du moteur horizontal
# Fins de course pour le moteur horizontal
fincourseG = Button(26)  # Fin de course côté gauche (exemple)
fincourseD = Button(19)  # Fin de course côté droit

# Moteur vertical (suivi de l'objet)
DIR2 = 16      # Broche direction du moteur vertical
STEP2 = 20     # Broche pour les pas du moteur vertical
ENABLE2 = 21   # Broche enable du moteur vertical

# =============================================================================
# Initialisation de GPIO
# =============================================================================
GPIO.setmode(GPIO.BCM)
GPIO.setup([DIR1, STEP1, ENABLE1, DIR2, STEP2, ENABLE2], GPIO.OUT)
# Désactivation initiale des moteurs
GPIO.output(ENABLE1, GPIO.HIGH)
GPIO.output(ENABLE2, GPIO.HIGH)

# =============================================================================
# Variables globales pour la gestion BLE (mode manuel) et pour le mode
# =============================================================================
speed_delays = {
    "1": 0.005,   # 25% de la vitesse maximale
    "2": 0.0025,  # 50% de la vitesse maximale
    "3": 0.0005,  # 75% de la vitesse maximale
    "4": 0.0001   # 100% de la vitesse maximale
}
current_delay = speed_delays["4"]
running = False           # Indique si le moteur horizontal doit tourner (mode BLE)
current_direction = GPIO.LOW
motor_thread = None       # Thread de contrôle du moteur horizontal (BLE)
ble_thread = None         # Thread du serveur BLE

# Variable globale pour le mode de fonctionnement ("manuel" ou "automatique")
mode = "manuel"
auto_running = False      # Indique si le thread automatique doit tourner
auto_thread = None        # Thread pour la rotation automatique

# =============================================================================
# Fonctions de contrôle des moteurs
# =============================================================================
def move_motor(direction, step_pin, dir_pin, steps, delay=0.005):
    """Fait tourner un moteur dans une direction donnée (1 ou 0) pour un nombre de pas donné."""
    GPIO.output(dir_pin, GPIO.HIGH if direction == 1 else GPIO.LOW)
    for _ in range(steps):
        GPIO.output(step_pin, GPIO.HIGH)
        time.sleep(delay)
        GPIO.output(step_pin, GPIO.LOW)
        time.sleep(delay)

# ---------------------------------------------------------------------------
# Contrôle du moteur horizontal
# ---------------------------------------------------------------------------
def enable_motor_horizontal():
    GPIO.output(ENABLE1, GPIO.LOW)

def disable_motor_horizontal():
    GPIO.output(ENABLE1, GPIO.HIGH)

def continuous_horizontal_rotation():
    """
    Fait tourner en continu le moteur horizontal.
    La direction est inversée en cas d'activation d'une fin de course.
    Cette fonction s'exécute tant que auto_running est True.
    """
    enable_motor_horizontal()
    direction = 1  # Sens initial
    while auto_running:
        if fincourseD.is_pressed:
            direction = 0
        elif fincourseG.is_pressed:
            direction = 1
        move_motor(direction, STEP1, DIR1, steps=1, delay=0.001)
    print("Fin de la rotation automatique")

def move_motor_continuous_ble():
    """
    Fait tourner le moteur horizontal en mode manuel selon la commande BLE.
    """
    enable_motor_horizontal()
    while running:
        GPIO.output(DIR1, current_direction)
        GPIO.output(STEP1, GPIO.HIGH)
        time.sleep(current_delay)
        GPIO.output(STEP1, GPIO.LOW)
        time.sleep(current_delay)
    print("Fin du contrôle BLE du moteur horizontal")

# ---------------------------------------------------------------------------
# Contrôle du moteur vertical
# ---------------------------------------------------------------------------
def enable_motor_vertical():
    GPIO.output(ENABLE2, GPIO.LOW)

def disable_motor_vertical():
    GPIO.output(ENABLE2, GPIO.HIGH)

def control_motor_vertical(error_x, threshold=30):
    """
    Utilise le moteur vertical pour corriger l'erreur horizontale de l'objet.
    Si error_x > threshold, le moteur tourne dans le sens permettant de recentrer l'objet.
    Le nombre de pas est proportionnel à l'écart (limité ici à 5 pas).
    """
    if abs(error_x) < threshold:
        return
    direction = 0 if error_x > 0 else 1
    steps = min(abs(error_x) // 10, 5)
    move_motor(direction, STEP2, DIR2, steps, delay=0.001)

# =============================================================================
# Serveur BLE pour le mode manuel
# =============================================================================
def ble_control():
    """
    Gère le contrôle du moteur horizontal via Bluetooth.
    Les commandes reçues sont traitées différemment selon le mode.
    En mode manuel, les commandes attendues sont :
      - "G" : tourner à gauche (direction HIGH)
      - "D" : tourner à droite (direction LOW)
      - "S" : arrêter le moteur
      - "1", "2", "3", "4" : ajuster la vitesse (délai de pas)
    De plus, la commande "A" permet de passer en mode automatique.
    """
    global running, current_direction, current_delay, motor_thread, mode, auto_running, auto_thread
    try:
        server_socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        server_socket.bind(("", bluetooth.PORT_ANY))
        server_socket.listen(1)
        port = server_socket.getsockname()[1]
        bluetooth.advertise_service(server_socket, "StepperControl",
                                    service_classes=[bluetooth.SERIAL_PORT_CLASS],
                                    profiles=[bluetooth.SERIAL_PORT_PROFILE])
        print(f"BLE: En attente de connexion sur le port {port}...")
        client_socket, client_address = server_socket.accept()
        print(f"BLE: Connexion acceptée depuis {client_address}")
        while True:
            data = client_socket.recv(1024).decode('utf-8').strip()
            if not data:
                break
            print(f"BLE: Commande reçue : {data}")
            # Si on reçoit la lettre "A", on bascule immédiatement en mode automatique
            if data.upper() == "A":
                mode = "automatique"
                auto_running = True
                print("Mode automatique activé via commande 'A'")
                if auto_thread is None or not auto_thread.is_alive():
                    auto_thread = threading.Thread(target=continuous_horizontal_rotation)
                    auto_thread.daemon = True
                    auto_thread.start()
                continue
            # Traitement des commandes en mode manuel
            if mode == "manuel":
                if data.upper() == "G":
                    print("BLE: Déplacement à gauche")
                    current_direction = GPIO.HIGH
                    running = True
                    if motor_thread is None or not motor_thread.is_alive():
                        motor_thread = threading.Thread(target=move_motor_continuous_ble)
                        motor_thread.start()
                elif data.upper() == "D":
                    print("BLE: Déplacement à droite")
                    current_direction = GPIO.LOW
                    running = True
                    if motor_thread is None or not motor_thread.is_alive():
                        motor_thread = threading.Thread(target=move_motor_continuous_ble)
                        motor_thread.start()
                elif data.upper() == "S":
                    running = False
                    print("BLE: Arrêt du moteur")
                elif data in speed_delays:
                    current_delay = speed_delays[data]
                    print(f"BLE: Vitesse réglée à {data} (délai : {current_delay:.4f}s)")
                else:
                    print("BLE: Commande non reconnue")
            else:
                print("BLE: Commande ignorée (mode non manuel)")
    except Exception as e:
        print("BLE: Erreur", e)
    finally:
        try:
            client_socket.close()
            server_socket.close()
            print("BLE: Connexion fermée")
        except:
            pass

# =============================================================================
# Détection, verrouillage et suivi de l'objet avec gestion des modes
# =============================================================================
def shape_detection_and_tracking():
    """
    Détecte et verrouille l'objet lorsqu'il est stabilisé dans une zone centrale.
    Le moteur vertical corrige la position de l'objet.
   
    Modes de fonctionnement :
      - Mode manuel : Le contrôle horizontal est géré par BLE.
      - Mode automatique : Le moteur horizontal tourne en continu.
   
    Le mode peut être basculé via :
      - les touches 'm' (manuel), 'a' (automatique),
      - ou par la réception de la commande "A" via BLE.
    """
    global mode, ble_thread, running, motor_thread, auto_running, auto_thread
    # Initialisation de la caméra
    picam2 = Picamera2()
    config = picam2.create_preview_configuration(main={"size": (640, 480)})
    picam2.configure(config)
    picam2.start()
    time.sleep(1)

    frame_width, frame_height = 640, 480
    center_width, center_height = 200, 200
    top_left = ((frame_width - center_width) // 2, (frame_height - center_height) // 2)
    bottom_right = (top_left[0] + center_width, top_left[1] + center_height)

    selection_complete = False
    locked_object = None  # (x, y, w, h)
    center_frames_count = 0
    CENTER_FRAMES_THRESHOLD = 45

    # Activation du moteur vertical
    enable_motor_vertical()

    # Démarrer le serveur BLE si le mode est manuel et s'il n'est pas déjà lancé
    if mode == "manuel" and (ble_thread is None or not ble_thread.is_alive()):
        ble_thread = threading.Thread(target=ble_control)
        ble_thread.daemon = True
        ble_thread.start()

    while True:
        frame = picam2.capture_array()
        if frame is None:
            continue

        # Prétraitement de l'image pour la détection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Affichage de la zone centrale
        if not selection_complete:
            cv2.rectangle(frame, top_left, bottom_right, (255, 0, 0), 2)

        largest_area = 0
        largest_contour = None
        object_in_center = False

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 800:
                continue
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            x, y, w, h = cv2.boundingRect(approx)
            if not selection_complete:
                if (top_left[0] < x < bottom_right[0] and
                    top_left[1] < y < bottom_right[1] and
                    (x + w) < bottom_right[0] and
                    (y + h) < bottom_right[1]):
                    if area > largest_area:
                        largest_area = area
                        largest_contour = (x, y, w, h)
                        object_in_center = True
            else:
                if locked_object is not None:
                    lx, ly, lw, lh = locked_object
                    cx_lock = lx + lw // 2
                    cy_lock = ly + lh // 2
                    cx = x + w // 2
                    cy = y + h // 2
                    distance = np.hypot(cx - cx_lock, cy - cy_lock)
                    if distance < 100:
                        locked_object = (x, y, w, h)

        if not selection_complete and largest_contour is not None:
            locked_object = largest_contour
            if object_in_center:
                center_frames_count += 1
            else:
                center_frames_count = max(0, center_frames_count - 1)
            if center_frames_count >= CENTER_FRAMES_THRESHOLD:
                selection_complete = True

        # Affichage du mode courant sur l'image
        cv2.putText(frame, f"Mode: {mode}", (10, frame_height - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        if not selection_complete:
            cv2.putText(frame,
                        f"Stabilisez: {center_frames_count}/{CENTER_FRAMES_THRESHOLD}",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1,
                        (0, 255, 0),
                        2)
        else:
            if locked_object:
                x, y, w, h = locked_object
                cx_obj = x + w // 2
                cy_obj = y + h // 2

                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2.circle(frame, (cx_obj, cy_obj), 5, (0, 255, 0), -1)

                error_x = cx_obj - frame_width // 2
                control_motor_vertical(error_x)
                cv2.putText(frame, "Tracking", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        cv2.imshow("Tracking", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('m'):
            if mode != "manuel":
                mode = "manuel"
                auto_running = False
                print("Mode manuel activé")
        elif key == ord('a'):
            if mode != "automatique":
                mode = "automatique"
                auto_running = True
                print("Mode automatique activé")
                if auto_thread is None or not auto_thread.is_alive():
                    auto_thread = threading.Thread(target=continuous_horizontal_rotation)
                    auto_thread.daemon = True
                    auto_thread.start()

    disable_motor_vertical()
    cv2.destroyAllWindows()
    picam2.close()
    GPIO.cleanup()

if __name__ == "__main__":
    try:
        shape_detection_and_tracking()
    except KeyboardInterrupt:
        GPIO.cleanup()

