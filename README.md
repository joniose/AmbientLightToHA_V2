# Ambient Light To Home Assistant

This project captures the dominant color of your screen and sends it as a sensor to [Home Assistant](https://www.home-assistant.io/).  
You can then use this sensor to control LED lights (e.g., via `light.turn_on`) and create an Ambilight effect.

It works on any Python-compatible device, such as PCs, Raspberry Pis, or small servers.

---

Forked and changed, that the area under the mouse takes the color. After time x it changes to the most color of the screen the ouse is on.

---

## 🔧 Requirements

- Python 3.9+
- Install dependencies:
  ```bash
  pip install opencv-python numpy requests mss
  ```

---

## ⚙️ Setup

Before running the script, you need to edit the variables:

### Windows 
```
HA_URL="http://192.xxx.xxx.xx:8123/api/states/sensor.dominant_color"
HA_TOKEN="LONG_LIVED_ACCESS_TOKEN"
```

> 📝 To generate a **Long-Lived Access Token**, open your Home Assistant profile (bottom left in the HA UI), scroll down to **Long-Lived Access Tokens**, and create a new one.

---

## ▶️ Usage

Run the script with:

```bash
python ambient.py
```

The script will:
- Take regular screenshots (~once per second, configurable),
- Calculate the dominant color (gray/black filtered out),
- Send the values to Home Assistant as `sensor.dominant_color`.

---

## 🏠 Home Assistant Integration

After the first run, a new sensor will appear in HA:

```
sensor.dominant_color
```

This sensor contains:
- **state** → `"R,G,B"` of the main color
- **attributes** → `r`, `g`, `b` as separate values

Example automation to control LEDs:

```yaml
alias: Ambilight Sync
description: Synchronisiert die Bildschirmfarbe mit den LEDs
triggers:
  - entity_id: sensor.dominant_color
    trigger: state
actions:
  - action: light.turn_on
    target:
      entity_id:
        - light.schlafzimmer_sterne
    data:
      rgb_color:
        - '{{ state_attr(''sensor.dominant_color'', ''r'') | int }}'
        - '{{ state_attr(''sensor.dominant_color'', ''g'') | int }}'
        - '{{ state_attr(''sensor.dominant_color'', ''b'') | int }}'
      brightness_pct: 10
      transition: 0.2

```

## 🎉 Example

Start a movie → the script detects the dominant screen color → your LED strips automatically follow the color ✨
