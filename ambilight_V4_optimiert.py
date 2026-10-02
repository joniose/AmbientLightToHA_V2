import cv2
import numpy as np
import requests
import time
import os
import mss
import ctypes

HA_URL = os.environ.get("HA_URL")
HA_TOKEN = os.environ.get("HA_TOKEN")

if not HA_URL or not HA_TOKEN:
    raise ValueError("HA_URL or HA_TOKEN not set.")

headers = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "content-type": "application/json",
}

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

def get_mouse_position():
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def get_active_monitor(sct):
    mx, my = get_mouse_position()
    # sct.monitors[0] ist die Kombination aller Monitore -> ab Index 1 suchen
    for monitor in sct.monitors[1:]:
        left = monitor["left"]
        top = monitor["top"]
        right = left + monitor["width"]
        bottom = top + monitor["height"]

        if left <= mx < right and top <= my < bottom:
            return monitor

    return sct.monitors[1]  # Fallback: Primärer Monitor

def send_to_ha(session, r, g, b):
    data = {
        "state": f"{r},{g},{b}",
        "attributes": {
            "friendly_name": "Ambilight Color",
            "r": int(r),
            "g": int(g),
            "b": int(b)
        }
    }
    try:
        session.post(HA_URL, headers=headers, json=data, timeout=0.2)
    except Exception:
        pass

def get_dominant_vibrant_color(frame, min_sat=50, min_val=40):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    h = hsv[:, :, 0]
    s = hsv[:, :, 1]
    v = hsv[:, :, 2]

    # Filter gegen Weiß/Grau/Schwarz
    mask = (s > min_sat) & (v > min_val)

    if not np.any(mask):
        return (0, 0, 0)

    # Dominanten Farbton ermitteln
    hue_counts, hue_bins = np.histogram(h[mask], bins=18, range=(0, 180))
    max_bin = np.argmax(hue_counts)
    target_hue = (hue_bins[max_bin] + hue_bins[max_bin + 1]) // 2

    pure_hsv = np.uint8([[[target_hue, 255, 245]]])
    pure_bgr = cv2.cvtColor(pure_hsv, cv2.COLOR_HSV2BGR)[0, 0]

    return int(pure_bgr[0]), int(pure_bgr[1]), int(pure_bgr[2])

def main():
    session = requests.Session()
    last_r, last_g, last_b = -1, -1, -1

    with mss.MSS() as sct:
        while True:
            t_start = time.time()

            # 1. Monitor ermitteln, auf dem sich der Mauszeiger befindet
            active_monitor = get_active_monitor(sct)

            # 2. Aktiven Monitor erfassen & direkt herunterrechnen
            sct_img = sct.grab(active_monitor)
            img = np.array(sct_img, dtype=np.uint8)[:, :, :3]
            small_frame = cv2.resize(img, (80, 45), interpolation=cv2.INTER_NEAREST)

            # 3. Dominante Farbe berechnen
            b, g, r = get_dominant_vibrant_color(small_frame)

            # 4. Nur bei Farbänderung an Home Assistant senden
            if (r, g, b) != (last_r, last_g, last_b):
                print(f"Monitor: {active_monitor['left']}x{active_monitor['top']} -> Farbe: R={r}, G={g}, B={b}")
                send_to_ha(session, r, g, b)
                last_r, last_g, last_b = r, g, b

            elapsed = time.time() - t_start
            sleep_time = max(0.01, 0.033 - elapsed)
            time.sleep(sleep_time)

if __name__ == "__main__":
    main()