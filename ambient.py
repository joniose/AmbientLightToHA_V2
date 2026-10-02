import cv2
import numpy as np
import requests
import time
import os
import traceback
import mss
import ctypes

HA_URL = "http://192.168.138.103:8123/api/states/sensor.dominant_color"
HA_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI4YTI2MzY4MjBjNWY0NGU4OTViMWZjNzcyMGJiMWQ3YiIsImlhdCI6MTc5MDg5MzU2OCwiZXhwIjoyMTA2MjUzNTY4fQ.wJLGUpyGSqEAAM-d_k96eLt8SVtDU_NO8mg_O5v6hNo"

if not HA_URL or not HA_TOKEN:
    raise ValueError("HA_URL or HA_TOKEN not set.")

headers = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "content-type": "application/json",
}

LOGFILE = "ambient.log"

# Einstellungen
ROI_SIZE = 10            # Bereich um die Maus in Pixeln
IDLE_TIMEOUT = 5.0        # Zeit in Sekunden bis zum Umschalten auf Vollbild

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

def get_mouse_position():
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def get_active_monitor(sct, mx, my):
    for monitor in sct.monitors[1:]:
        left = monitor["left"]
        top = monitor["top"]
        right = left + monitor["width"]
        bottom = top + monitor["height"]

        if left <= mx < right and top <= my < bottom:
            return monitor

    return sct.monitors[1]

def get_mouse_roi(sct, mx, my, box_size=ROI_SIZE):
    half = box_size // 2
    all_monitors = sct.monitors[0]
    
    left = mx - half
    top = my - half
    
    left = max(all_monitors["left"], min(left, all_monitors["left"] + all_monitors["width"] - box_size))
    top = max(all_monitors["top"], min(top, all_monitors["top"] + all_monitors["height"] - box_size))

    return {
        "left": left,
        "top": top,
        "width": box_size,
        "height": box_size
    }

def log(msg):
    with open(LOGFILE, "a") as f:
        f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + str(msg) + "\n")

def send_to_ha(r, g, b):
    data = {
        "state": f"{r},{g},{b}",
        "attributes": {
            "friendly_name": "Ambilight Color",
            "r": r,
            "g": g,
            "b": b
        }
    }
    try:
        requests.post(HA_URL, headers=headers, json=data, timeout=2)
    except Exception:
        log("Error sending data:\n" + traceback.format_exc())

# 1. Auswertung für das Maus-Umfeld (Fokus auf dominante Einzelfarbe)
def get_dominant_color_roi(frame, min_saturation=40):
    small = cv2.resize(frame, (100, 100))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)

    # 1. Bildhelligkeit (Value-Kanal) sichern
    avg_value = hsv[:, :, 2].mean()

    # Wenn der Bereich unter der Maus sehr dunkel ist (z.B. < 15/255 Helligkeit)
    if avg_value < 15:
        return (0, 0, 0)

    # 2. Bunte Pixel filtern (auch bei geringerer Helligkeit zulassen)
    saturation = hsv[:, :, 1]
    color_mask = saturation > min_saturation

    # Falls gar keine Sättigung da ist (z. B. grauer/dunkler Hintergrund), 
    # dimme entsprechend der reinen Helligkeit des Bildes runter
    if not np.any(color_mask):
        val = int(avg_value)
        return (val, val, val)

    # 3. Dominanten Farbton ermitteln
    hue_colored = hsv[:, :, 0][color_mask]
    counts, bins = np.histogram(hue_colored, bins=18, range=(0, 180))
    dominant_bin = np.argmax(counts)
    dominant_hue = int((bins[dominant_bin] + bins[dominant_bin + 1]) / 2)

    # 4. Zielfarbe zusammenbauen: Bunter Farbton + echte Helligkeit des Zeigerumfelds
    pure_hsv = np.uint8([[[dominant_hue, 255, int(avg_value)]]])
    final_bgr = cv2.cvtColor(pure_hsv, cv2.COLOR_HSV2BGR)[0, 0]

    return (int(final_bgr[0]), int(final_bgr[1]), int(final_bgr[2]))

# 2. Auswertung für den GANZEN Bildschirm (Maximale Farbsättigung & Ausfiltern unbunter Flächen)
def get_vibrant_fullscreen_color(frame, min_saturation=60, boost=1.5):
    small = cv2.resize(frame, (160, 90))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)

    # Farbsättigung aller Pixel verdoppeln
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 2.0, 0, 255)

    # Entsättigte & dunkle Flächen (Weiß/Grau/Schwarz) konsequent herausfiltern
    saturation_mask = hsv[:, :, 1] > min_saturation
    value_mask = hsv[:, :, 2] > 40
    combined_mask = saturation_mask & value_mask

    if not np.any(combined_mask):
        return (0, 0, 0)

    enhanced = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    valid_pixels = enhanced[combined_mask]

    avg = valid_pixels.mean(axis=0)
    avg = np.clip(avg * boost, 0, 255)

    return (int(avg[0]), int(avg[1]), int(avg[2]))

# Bewegungsüberwachung
last_mouse_pos = (0, 0)
last_move_time = time.time()
last_sent = 0

with mss.MSS() as sct:
    while True:
        try:
            mx, my = get_mouse_position()
            now = time.time()

            if (mx, my) != last_mouse_pos:
                last_mouse_pos = (mx, my)
                last_move_time = now

            # Modus-Auswahl basierend auf Inaktivität
            is_mouse_active = (now - last_move_time) < IDLE_TIMEOUT

            if is_mouse_active:
                capture_area = get_mouse_roi(sct, mx, my)
            else:
                capture_area = get_active_monitor(sct, mx, my)

            sct_img = sct.grab(capture_area)
            img = np.array(sct_img)
            frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        except Exception:
            log("Error grabbing screen via mss:\n" + traceback.format_exc())
            frame = None

        if frame is None:
            time.sleep(1)
            continue

        # Berechnung passend zum aktiven Erfassungs-Modus
        if is_mouse_active:
            b, g, r = get_dominant_color_roi(frame)
        else:
            b, g, r = get_vibrant_fullscreen_color(frame)

        if time.time() - last_sent > 1:
            send_to_ha(r, g, b)
            last_sent = time.time()
            log(f"Send: R={r}, G={g}, B={b}")

        time.sleep(0.1)
