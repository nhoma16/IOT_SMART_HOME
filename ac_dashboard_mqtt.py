import sys
import random
import sqlite3
import json
import queue
from datetime import datetime
from collections import deque

import paho.mqtt.client as mqtt
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QFrame, QGridLayout, QMessageBox
)
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# ---------------------- CONFIG ----------------------
DB_FILE = "sensor_data.db"
MQTT_HOST = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "gym/project"
TEMP_THRESHOLD = 30.0

# ---------------------- DATABASE ----------------------
class DataManager:
    def __init__(self, db_name=DB_FILE):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cur = self.conn.cursor()
        self.create_table()

    def create_table(self):
        self.cur.execute('''
            CREATE TABLE IF NOT EXISTS sensor_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                temperature REAL,
                humidity REAL,
                relay_status INTEGER
            )
        ''')
        self.conn.commit()

    def insert(self, timestamp, temp, hum, relay_status):
        self.cur.execute(
            "INSERT INTO sensor_data (timestamp, temperature, humidity, relay_status) VALUES (?, ?, ?, ?)",
            (timestamp, temp, hum, relay_status)
        )
        self.conn.commit()

    def get_last_records(self, limit=10):
        self.cur.execute(
            "SELECT timestamp, temperature, humidity, relay_status FROM sensor_data ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        return self.cur.fetchall()

    def close(self):
        self.conn.close()

# ---------------------- MQTT ----------------------
class MqttClientWrapper:
    def __init__(self, host, port, topic, incoming_queue: queue.Queue, clientName="AC_Client"):
        self.host = host
        self.port = port
        self.topic = topic
        self.queue = incoming_queue
        self.client = mqtt.Client(client_id=clientName)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.connected = False
        try:
            self.client.connect(self.host, self.port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            self.queue.put({"type": "sys", "event": "connect_error", "error": str(e)})

    def on_connect(self, client, userdata, flags, rc):
        self.connected = (rc == 0)
        if self.connected:
            self.client.subscribe(self.topic)
        self.queue.put({"type": "sys", "event": "connected" if rc==0 else "connect_failed", "rc": rc})

    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        self.queue.put({"type": "sys", "event": "disconnected", "rc": rc})

    def on_message(self, client, userdata, msg):
        payload = msg.payload.decode(errors="ignore")
        try:
            data = json.loads(payload)
        except Exception:
            data = {"raw": payload}
        self.queue.put(data)

    def publish(self, data):
        try:
            self.client.publish(self.topic, json.dumps(data))
        except Exception as e:
            self.queue.put({"type": "sys", "event": "publish_error", "error": str(e)})

    def stop(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

# ---------------------- PLOT ----------------------
class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=6, height=3, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi, tight_layout=True)
        self.ax = fig.add_subplot(111)
        super().__init__(fig)
        self.setParent(parent)

# ---------------------- DASHBOARD ----------------------
class ACDashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AC Dashboard")
        self.resize(1000, 600)

        # DB
        self.db = DataManager()

        # MQTT
        self.mqtt_queue = queue.Queue()
        self.mqtt = MqttClientWrapper(MQTT_HOST, MQTT_PORT, MQTT_TOPIC, self.mqtt_queue)

        # Sensor & relay states
        self.temp = 24.0
        self.hum = 50.0
        self.relay_on = False

        # History
        self.max_points = 200
        self.times = deque(maxlen=self.max_points)
        self.temps = deque(maxlen=self.max_points)
        self.hums = deque(maxlen=self.max_points)

        # Timers
        self.update_timer = QTimer()
        self.update_timer.setInterval(5000)  # כל 5 שניות
        self.update_timer.timeout.connect(self.on_update)
        self.update_timer.start()

        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout()
        top_layout = QHBoxLayout()

        # Plot
        self.canvas = MplCanvas(self, width=7, height=4)
        top_layout.addWidget(self.canvas, 3)

        # Right panel
        right_frame = QFrame()
        right_layout = QVBoxLayout()

        # Status
        status_grid = QGridLayout()
        status_grid.addWidget(QLabel("Temperature (°C):"),0,0)
        self.lbl_temp = QLabel(f"{self.temp:.1f}")
        status_grid.addWidget(self.lbl_temp,0,1)
        status_grid.addWidget(QLabel("Humidity (%):"),1,0)
        self.lbl_hum = QLabel(f"{self.hum:.1f}")
        status_grid.addWidget(self.lbl_hum,1,1)
        status_grid.addWidget(QLabel("Relay:"),2,0)
        self.relay_indicator = QLabel()
        self.relay_indicator.setFixedSize(40,40)
        self.relay_indicator.setStyleSheet("background-color: gray; border-radius:6px;")
        status_grid.addWidget(self.relay_indicator,2,1)
        right_layout.addLayout(status_grid)

        # Manual button emulator
        self.btn_manual = QPushButton("Press Button")
        self.btn_manual.clicked.connect(self.manual_button_pressed)
        right_layout.addWidget(self.btn_manual)

        # ✅ הכפתור להצגת 10 הרשומות האחרונות
        self.btn_show_db = QPushButton("Show Last 10 DB Records")
        self.btn_show_db.clicked.connect(self.show_last_records)
        right_layout.addWidget(self.btn_show_db)

        # Logs
        right_layout.addWidget(QLabel("Logs / Warnings:"))
        self.list_logs = QListWidget()
        right_layout.addWidget(self.list_logs,1)

        right_frame.setLayout(right_layout)
        top_layout.addWidget(right_frame,1)
        main_layout.addLayout(top_layout)

        self.setLayout(main_layout)

    def log(self,text):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        item = QListWidgetItem(f"{ts} - {text}")
        self.list_logs.addItem(item)
        self.list_logs.scrollToBottom()
        print(f"{ts} - {text}")

    def manual_button_pressed(self):
        data = {"type":"button_pressed"}
        self.mqtt.publish(data)
        self.log("Manual button pressed → MQTT published")

    def simulate_sensor(self):
        self.temp = round(random.uniform(20,32),2)
        self.hum = round(random.uniform(30,70),2)
        data = {"type":"sensor","temperature":self.temp,"humidity":self.hum}
        self.mqtt.publish(data)

    def process_mqtt_queue(self):
        while not self.mqtt_queue.empty():
            msg = self.mqtt_queue.get_nowait()
            if isinstance(msg, dict):
                # Sensor reading
                if msg.get("type")=="sensor":
                    t = msg.get("temperature")
                    h = msg.get("humidity")
                    if t is not None and h is not None:
                        self.temp = t
                        self.hum = h
                        self.lbl_temp.setText(f"{t:.1f}")
                        self.lbl_hum.setText(f"{h:.1f}")
                        self.times.append(datetime.now().strftime("%H:%M:%S"))
                        self.temps.append(t)
                        self.hums.append(h)
                        # Warnings
                        if t>=TEMP_THRESHOLD:
                            self.log(f"⚠️ High temperature: {t:.1f}°C")
                        # Auto relay
                        self.relay_on = t>=TEMP_THRESHOLD or msg.get("manual_override", False)
                        self.relay_indicator.setStyleSheet("background-color: green;" if self.relay_on else "background-color: gray;")
                        # Save DB
                        self.db.insert(datetime.now().strftime("%Y-%m-%d %H:%M:%S"),t,h,int(self.relay_on))
                # Button press
                if msg.get("type")=="button_pressed":
                    # Toggle relay
                    self.relay_on = not self.relay_on
                    self.relay_indicator.setStyleSheet("background-color: green;" if self.relay_on else "background-color: gray;")
                    self.log(f"Button press received → Relay {'ON' if self.relay_on else 'OFF'}")

    def update_plot(self):
        ax = self.canvas.ax
        ax.clear()
        x = list(range(len(self.temps)))
        ax.plot(x,list(self.temps),label="Temperature")
        ax.plot(x,list(self.hums),label="Humidity")
        ax.set_xlabel("Samples (newest → right)")
        ax.set_ylabel("Value")
        ax.grid(True)
        ax.legend()
        self.canvas.draw()

    def on_update(self):
        self.simulate_sensor()
        self.process_mqtt_queue()
        self.update_plot()

    # ✅ פונקציה חדשה להצגת 10 הרשומות האחרונות מה-DB
    def show_last_records(self):
        try:
            records = self.db.get_last_records(10)
        except Exception as e:
            QMessageBox.information(self, "DB Records", f"Error reading DB: {e}")
            return

        if not records:
            QMessageBox.information(self, "DB Records", "No records found in DB.")
            return
        text = "\n".join([
            f"{ts} | Temp: {t:.1f}°C | Hum: {h:.1f}% | Relay: {'ON' if r else 'OFF'}"
            for ts, t, h, r in records
        ])
        QMessageBox.information(self, "Last 10 DB Records", text)

    def closeEvent(self,event):
        self.update_timer.stop()
        self.mqtt.stop()
        self.db.close()
        event.accept()

# ---------------------- MAIN ----------------------
def main():
    app = QApplication(sys.argv)
    win = ACDashboard()
    win.show()
    sys.exit(app.exec_())

if __name__=="__main__":
    main()
