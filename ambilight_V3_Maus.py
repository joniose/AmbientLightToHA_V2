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

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

def get_mouse_position():
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def get_active_monitor(sct):
    mx, my = get_mouse_position()
    # sct.monitors[0] enthält alle Monitore vereint -> ab Index 1 die Einzelmonitore prüfen
    for monitor in sct.monitors[1:]:
        left = monitor["left"]
        top = monitor["top"]
        right = left + monitor["width"]
        bottom = top + monitor["height"]

        if left <= mx < right and top <= my < bottom:
            return monitor

    return sct.monitors[1]  # Fallback: Erster Monitor

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

def get_average_color(frame, min_saturation=50, min_value=40):
    # Bild verkleinern für extrem schnelle Verarbeitung
    small = cv2.resize(frame, (160, 90))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)

    # 1. Neutrale Pixel filtern (Weiß, Grau, Schwarz)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    color_mask = (saturation > min_saturation) & (value > min_value)

    if not np.any(color_mask):
        return (0, 0, 0)

    # 2. Nur die echten Farbpixel (Hue-Kanal: 0-179) betrachten
    hue_colored = hsv[:, :, 0][color_mask]

    # 3. Das Hue-Histogramm berechnen
    counts, bins = np.histogram(hue_colored, bins=18, range=(0, 180))
    dominant_bin = np.argmax(counts)
    
    dominant_hue = int((bins[dominant_bin] + bins[dominant_bin + 1]) / 2)

    # 4. Alle Pixel nehmen, die zu diesem dominanten Farbton gehören
    hue_mask = color_mask & (np.abs(hsv[:, :, 0].astype(int) - dominant_hue) < 10)
    dominant_pixels = small[hue_mask]

    if len(dominant_pixels) == 0:
        return (0, 0, 0)

    # 5. Mittleren BGR-Wert der dominanten Farbgruppe berechnen
    avg_bgr = dominant_pixels.mean(axis=0)

    hsv_single = cv2.cvtColor(np.uint8([[avg_bgr]]), cv2.COLOR_BGR2HSV)
    hsv_single[0, 0, 1] = 255  # Sättigung auf Maximum
    hsv_single[0, 0, 2] = max(hsv_single[0, 0, 2], 200)  # Helligkeit anheben

    final_bgr = cv2.cvtColor(hsv_single, cv2.COLOR_HSV2BGR)[0, 0]

    return (int(final_bgr[0]), int(final_bgr[1]), int(final_bgr[2]))

def grab_screen_mss(sct):
    monitor = get_active_monitor(sct)
    sct_img = sct.grab(monitor)
    img = np.array(sct_img)
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

last_sent = 0

with mss.MSS() as sct:
    while True:
        try:
            frame = grab_screen_mss(sct)
        except Exception:
            log("Error grabbing screen via mss:\n" + traceback.format_exc())
            frame = None

        if frame is None:
            time.sleep(1)
            continue

        b, g, r = get_average_color(frame)

        if time.time() - last_sent > 1:
            send_to_ha(r, g, b)
            last_sent = time.time()
            log(f"Send: R={r}, G={g}, B={b}")

        time.sleep(0.1)