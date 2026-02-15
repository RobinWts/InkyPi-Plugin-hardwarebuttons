# Core Changes Required for Hardware Buttons Plugin

This plugin uses the same core patch as the Plugin Manager: **blueprint registration support**.

## Quick Start – How to Apply the Patch

1. Open a terminal/SSH session on your Raspberry Pi.
2. Navigate to your InkyPi directory (e.g. `/home/pi/InkyPi`).
3. Run the patch script:
   ```bash
   cd /home/pi/InkyPi
   bash src/plugins/hardwarebuttons/patch-core.sh
   ```
4. The script will apply the necessary core changes and restart the InkyPi service.
5. Reload the Hardware Buttons settings page in your browser.

If the Plugin Manager has already been used and the patch was applied, no further action is needed.

## What the Patch Does

The patch adds a generic mechanism so any plugin can register Flask API routes (blueprints):

- **`src/plugins/plugin_registry.py`** – adds `register_plugin_blueprints(app)`.
- **`src/inkypi.py`** – imports and calls `register_plugin_blueprints(app)` at startup.

Only one application of this patch is required; it is shared by all plugins that need blueprint support.

## Undoing the Patch

To restore the original core files:

```bash
cd /home/pi/InkyPi
git checkout src/plugins/plugin_registry.py src/inkypi.py
sudo systemctl restart inkypi.service
```

Replace `inkypi` with your service name if different.
