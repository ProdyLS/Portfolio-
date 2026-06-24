import RPi.GPIO as GPIO  # Contrôle des broches GPIO du Raspberry Pi
import bluetooth  # Communication sans fil Bluetooth
import time  # Gestion des délais
import threading  # Gestion des threads pour exécuter le moteur en parallèle

#CONFIGURATION DES BROCHES GPIO#
DIR_PIN = 5      # Broche pour définir la direction du moteur
STEP_PIN = 6     # Broche pour envoyer les impulsions de pas
ENABLE_PIN = 13  # Broche pour activer ou désactiver le moteur

GPIO.setmode(GPIO.BCM)  # Utilisation de la numérotation BCM
GPIO.setup(DIR_PIN, GPIO.OUT)
GPIO.setup(STEP_PIN, GPIO.OUT)
GPIO.setup(ENABLE_PIN, GPIO.OUT)
GPIO.output(ENABLE_PIN, GPIO.LOW)  # Activation du moteur

#CONFIGURATION DES VITESSES#
speed_delays = {
    "1": 0.005,  # 25% de la vitesse maximale
    "2": 0.0025, # 50% de la vitesse maximale
    "3": 0.0005,  # 75% de la vitesse maximale
    "4": 0.0001  # 100% de la vitesse maximale
}

current_delay = speed_delays["4"]  # Vitesse par défaut
running = False  # État du moteur
current_direction = GPIO.LOW  # Direction par défaut
motor_thread = None  # Thread pour exécuter le moteur

#FONCTION DE CONTRÔLE DU MOTEUR#
def move_motor_continuous():
    while running:
        GPIO.output(DIR_PIN, current_direction)  # Définir la direction
        GPIO.output(STEP_PIN, GPIO.HIGH)  # Envoi d'une impulsion HIGH
        time.sleep(current_delay)  # Attente
        GPIO.output(STEP_PIN, GPIO.LOW)  # Envoi d'une impulsion LOW
        time.sleep(current_delay)  # Attente

def start_motor():
    global motor_thread
    if motor_thread is None or not motor_thread.is_alive():
        motor_thread = threading.Thread(target=move_motor_continuous)
        motor_thread.start()

def stop_motor():
    GPIO.output(STEP_PIN, GPIO.LOW)
    print("Arrêt du moteur")

#CONFIGURATION DU SERVEUR BLUETOOTH#
server_socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
server_socket.bind(("", bluetooth.PORT_ANY))
server_socket.listen(1)

port = server_socket.getsockname()[1]

bluetooth.advertise_service(server_socket, "StepperControl",
                            service_classes=[bluetooth.SERIAL_PORT_CLASS],
                            profiles=[bluetooth.SERIAL_PORT_PROFILE])

print(f"En attente de connexion sur le port {port}...")

client_socket, client_address = server_socket.accept()
print(f"Connexion acceptée depuis {client_address}")

#GESTION DES COMMANDES#
try:
    while True:
        data = client_socket.recv(1024).decode('utf-8').strip()
        if not data:
            break
        
        print(f"Commande reçue : {data}")
        
        if data == "G":
            print("Déplacement à gauche")
            current_direction = GPIO.HIGH
            running = True
            start_motor()
        
        elif data == "D":
            print("Déplacement à droite")
            current_direction = GPIO.LOW
            running = True
            start_motor()
        
        elif data == "S":
            running = False
            stop_motor()
        
        elif data in speed_delays:
            current_delay = speed_delays[data]
            print(f"Vitesse réglée à {data} (délai : {current_delay:.4f}s)")

        else:
            print("Commande non reconnue")

#ARRÊT PROPRE DU PROGRAMME#
except KeyboardInterrupt:
    print("Arrêt du serveur")

finally:
    running = False
    if motor_thread is not None:
        motor_thread.join()
    GPIO.output(ENABLE_PIN, GPIO.HIGH)
    GPIO.cleanup()
    client_socket.close()
    server_socket.close()
    print("Connexion fermée")
