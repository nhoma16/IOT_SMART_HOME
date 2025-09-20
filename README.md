# ❄️ AC Dashboard – IoT Monitoring & Control

This project is a **Python-based GUI application** built with **PyQt5**, designed to monitor and control an air conditioning system (or similar IoT setup).  
It integrates **MQTT** for communication, **SQLite** for persistent storage, and **Matplotlib** for real-time data visualization.

---

## 🚀 Features

- 📊 **Real-time monitoring** of Temperature (°C) and Humidity (%)  
- 🔔 **Automatic warnings** when temperature exceeds a threshold (default: `30°C`)  
- 🟢 **Relay control indicator** (ON/OFF)  
- 🎛 **Manual button** to emulate relay toggle (via MQTT)  
- 📉 **Live graphs** of temperature & humidity (last 200 samples)  
- 💾 **Local database storage** (`sensor_data.db`)  
- 📑 **Show last 10 DB records** in a popup window  

---

## ⚙️ How It Works

- Every **5 seconds** the app simulates a new temperature and humidity reading and publishes it to the MQTT broker.  
- Sensor data is displayed in the GUI, plotted on a dynamic graph, and saved to the database.  
- If **temperature ≥ 30°C**, a warning is logged and the **relay turns ON automatically**.  
- Manual button presses are also published over MQTT and toggle the relay state.  
- The **“Show Last 10 DB Records”** button lets you quickly check recent entries.  

---

## 🗄️ Database

- The app creates a file named `sensor_data.db` on first run.  
- Stored fields:
  - `timestamp` – when the data was recorded  
  - `temperature` – temperature in °C  
  - `humidity` – humidity in %  
  - `relay_status` – `1` = ON, `0` = OFF  

---

## 🛠️ Requirements

Install dependencies with:

```bash
pip install pyqt5 matplotlib paho-mqtt
