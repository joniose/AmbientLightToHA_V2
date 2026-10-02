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

# Größe des Bereichs um die Maus (in Pixeln)
ROI_SIZE = 10 

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

def get_mouse_position():
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def get_mouse_roi(sct, box_size=ROI_SIZE):
    mx, my = get_mouse_position()
    half = box_size // 2

    # Gesamter virtueller Desktop-Bereich (sct.monitors[0])
    all_monitors = sct.monitors[0]
    
    # Koordinaten des Quadrats um die Maus berechnen
    left = mx - half
    top = my - half
    
    # Verhindern, dass die Box außerhalb des Bildschirms liegt
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

def get_average_color(frame, min_saturation=50, min_value=40):
    small = cv2.resize(frame, (100, 100))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)

    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    color_mask = (saturation > min_saturation) & (value > min_value)

    if not np.any(color_mask):
        return (0, 0, 0)

    hue_colored = hsv[:, :, 0][color_mask]

    counts, bins = np.histogram(hue_colored, bins=18, range=(0, 180))
    dominant_bin = np.argmax(counts)
    dominant_hue = int((bins[dominant_bin] + bins[dominant_bin + 1]) / 2)

    hue_mask = color_mask & (np.abs(hsv[:, :, 0].astype(int) - dominant_hue) < 10)
    dominant_pixels = small[hue_mask]

    if len(dominant_pixels) == 0:
        return (0, 0, 0)

    avg_bgr = dominant_pixels.mean(axis=0)

    hsv_single = cv2.cvtColor(np.uint8([[avg_bgr]]), cv2.COLOR_BGR2HSV)
    hsv_single[0, 0, 1] = 255
    hsv_single[0, 0, 2] = max(hsv_single[0, 0, 2], 200)

    final_bgr = cv2.cvtColor(hsv_single, cv2.COLOR_HSV2BGR)[0, 0]

    return (int(final_bgr[0]), int(final_bgr[1]), int(final_bgr[2]))

def grab_mouse_area_mss(sct):
    roi = get_mouse_roi(sct)
    sct_img = sct.grab(roi)
    img = np.array(sct_img)
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

last_sent = 0

with mss.MSS() as sct:
    while True:
        try:
            frame = grab_mouse_area_mss(sct)
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