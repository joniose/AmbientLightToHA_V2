import cv2
import numpy as np
import requests
import time
import os
import traceback
import mss

HA_URL="http://192.168.138.103:8123/api/states/sensor.dominant_color"
HA_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI4YTI2MzY4MjBjNWY0NGU4OTViMWZjNzcyMGJiMWQ3YiIsImlhdCI6MTc5MDg5MzU2OCwiZXhwIjoyMTA2MjUzNTY4fQ.wJLGUpyGSqEAAM-d_k96eLt8SVtDU_NO8mg_O5v6hNo"

if not HA_URL or not HA_TOKEN:
    raise ValueError("HA_URL or HA_TOKEN not set.")

headers = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "content-type": "application/json",
}

LOGFILE = "ambient.log"

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

def get_average_color(frame, min_saturation=20, boost=1.8):
    small = cv2.resize(frame, (160, 90))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)

    # 1. Sättigung (Kanal 1) im HSV-Raum um 50% anheben
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.5, 0, 255)
    
    # Zurück zu BGR für die Mittelwertberechnung
    enhanced = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    mask = hsv[:, :, 1] > min_saturation
    if not np.any(mask):
        return (0, 0, 0)

    valid = small[mask]
    avg = valid.mean(axis=0)
    avg = np.clip(avg * boost, 0, 255)

    return tuple(map(int, avg))

def grab_screen_mss(sct):
    # Erfasst den primären Monitor
    monitor = sct.monitors[1]
    sct_img = sct.grab(monitor)
    img = np.array(sct_img)
    # BGRA zu BGR umwandeln
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