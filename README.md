# Hardware Buttons plugin for InkyPi

This plugin lets you attach physical buttons to your Raspberry Pi and bind them to InkyPi actions: next/previous playlist item, force refresh, shutdown, reboot, restart InkyPi, or run a custom script. Each button supports **short press**, **double-click**, and **long press** with configurable timings.

The same patch of core files is needed as for the [pluginManager](https://github.com/RobinWts/InkyPi-Plugin-PluginManager), it will be automatically applied on first access of the settings panel of this plugin, if you want to know more, see pluginManager docs.

## How to use the plugin

1. **Open settings**  
   In the InkyPi web UI, go to **Plugins** and open **Hardware Buttons**.

2. **Set timings (optional)**  
   Adjust the three timing values (in milliseconds):
   - **Short press (max)**: press shorter than this is treated as “short” (default 500 ms).
   - **Double-click interval (max)**: max time between two presses to count as double-click (default 500 ms).
   - **Long press (min)**: hold at least this long for “long press” (default 1000 ms).

3. **Add a button**  
   Click **Add button**, then:
   - Enter the **GPIO pin** number (BCM numbering, e.g. `27`).
   - Choose an action for **Short press**, **Double-click**, and **Long press** (or leave “No action”).
   - For **Run external bash script**, optionally set the script path in the text field (absolute path).

4. **Save**  
   Click **Save** to apply. Buttons are reloaded automatically; no need to restart InkyPi.

You can add several buttons (each with its own GPIO pin) and remove any with the **×** control.

## Available actions

- **Core:** Trigger refresh (next in playlist), Force refresh (re-show current), Next playlist item, Previous playlist item.
- **System:** Shutdown, Reboot, Restart InkyPi service, Run external bash script (with optional script path).

Other plugins can register extra actions that appear under “Current plugin” or “Other plugins” in the dropdowns.

## Wiring buttons on a Raspberry Pi Zero 2 W

The **Raspberry Pi Zero 2 W** has a **40-pin GPIO header** (0.1 in / 2.54 mm pitch). On the base Zero 2 W the header is **unpopulated**; you can solder a 40-pin header or use pogo pins. The Zero 2 **WH** variant comes with the header pre-soldered.

Use **BCM GPIO numbers** in the plugin (the same numbers used by gpiozero and most Python GPIO docs). Do **not** use “physical pin” numbers.

### Simple two-wire button (recommended)

A typical momentary pushbutton is wired between a **GPIO** pin and **GND**. The Pi’s internal pull-up is used, so no external resistor is needed.

| Button leg | Pi connection |
|------------|----------------|
| Leg 1      | **GPIO** |
| Leg 2      | **GND** (e.g. physical pin 6, 9, 14, 20, 25, 30, 34, or 39) |

When the button is **released**, the GPIO is pulled high (3.3 V). When **pressed**, the pin is shorted to GND and reads low. The plugin uses this “active low” behaviour.

### Example: one button on GPIO 27 (Raspberry Pi Zero 2 W)

- **GPIO 27** = **physical pin 13** (see diagram below).
- **GND** = e.g. **physical pin 9** (next to GPIO 17) or **physical pin 6**.

So you need two wires: one from one button leg to **pin 13**, one from the other leg to **pin 9** (or another GND).

### 40-pin header (BCM GPIO, top view)

Use this to pick a GPIO and a GND near it:

```
        3V3  (1) (2)  5V
       GPIO2 (3) (4)  5V
       GPIO3 (5) (6)  GND     <- GND
       GPIO4 (7) (8)  GPIO14
        GND (9) (10) GPIO15
      GPIO17 (11)(12) GPIO18
      GPIO27 (13)(14) GND
      GPIO22 (15)(16) GPIO23
        3V3 (17)(18) GPIO24
      GPIO10 (19)(20) GND
       GPIO9 (21)(22) GPIO25
      GPIO11 (23)(24) GPIO8
        GND (25)(26) GPIO7
       ...
        GND (39)(40) GND
```

**Safe GPIOs for buttons** (avoid pins used by your display or HAT): **2**, **3**, **4**, **17**, **27**, **22**, **23**, **24**, **25**.  
Avoid **8, 9, 10, 11** if you use SPI for the e-ink display; avoid **2, 3** if you use I2C.

### Multiple buttons

Repeat the same wiring for each button: each button uses one GPIO and one GND. You can use the same GND for all buttons (e.g. pin 6 or 9). Example for three buttons:

- Button A: GPIO 27 (pin 13) ↔ GND (pin 9)
- Button B: GPIO 22 (pin 15) ↔ GND (pin 9)
- Button C: GPIO 23 (pin 16) ↔ GND (pin 9)

In the plugin, add three buttons with GPIO pins **27**, **22**, and **23**.

## Requirements

- **Raspberry Pi** (e.g. Zero 2 W, 4, 3) with GPIO available.
- **Python**: `gpiozero` (see `requirements.txt` in this folder). On a full InkyPi install, GPIO dependencies may already be installed.
- **No GPIO on dev machines**: the plugin still loads; button handling is simply disabled when gpiozero or GPIO is unavailable.

## Notes

- Only **one action** runs at a time; further button presses or API calls are ignored until the current action finishes or times out (about 2 minutes).
- **External script**: use an absolute path to a script; the plugin runs it with `bash` and a 30 s timeout. Restrict paths to avoid running arbitrary commands.
- After changing settings, click **Save**; the button manager reloads config without restarting InkyPi.
