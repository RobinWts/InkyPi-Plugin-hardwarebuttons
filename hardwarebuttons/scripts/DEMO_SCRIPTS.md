# Demo Scripts for Hardware Buttons Plugin

This directory contains demo scripts that showcase the "Run external bash script" action feature of the Hardware Buttons plugin.

## Available Demo Scripts

### 1. System Status Logger (`demo_system_status.sh`)

**Purpose**: Logs system information (uptime, CPU temperature, memory, disk usage) to a file.

**Use Case**: Bind to a button to quickly check system status without SSH access.

**Setup**:
1. Copy the script to a location accessible by the InkyPi service (e.g., `/home/pi/scripts/` or `/usr/local/bin/`)
2. Make it executable: `chmod +x demo_system_status.sh`
3. In Hardware Buttons plugin settings, add a button and set "Run external bash script" as the action
4. Enter the full path to the script (e.g., `/home/pi/scripts/demo_system_status.sh`)

**Output**: Logs are written to `~/.inkypi_button_logs/system_status.log`

**Example Output**:
```
==========================================
System Status - 2026-02-16 14:30:45
==========================================
Uptime: up 2 days, 5 hours
CPU Temperature: 45.2'C
Memory Usage: 245M/1.0G (24.0%)
Disk Usage: 2.1G/16G (15% used)
Load Average: 0.12, 0.15, 0.18
```

### 2. Button Event Logger (`demo_button_logger.sh`)

**Purpose**: Logs button press events with timestamps and action types (short press, double-click, long press).

**Use Case**: Track button usage patterns, debug button configurations, or create an audit trail.

**Setup**:
1. Copy the script to a location accessible by the InkyPi service
2. Make it executable: `chmod +x demo_button_logger.sh`
3. Option A - Single script for all actions:
   - Bind the same script to short/double/long press actions
   - The script will log all events (you can distinguish by creating separate copies)
4. Option B - Separate scripts for each action:
   ```bash
   cp demo_button_logger.sh demo_button_logger_short.sh
   cp demo_button_logger.sh demo_button_logger_double.sh
   cp demo_button_logger.sh demo_button_logger_long.sh
   ```
   - Bind each copy to the corresponding action type

**Output**: Logs are written to `~/.inkypi_button_logs/button_events.log`

**Example Output**:
```
[2026-02-16 14:30:45] SHORT_PRESS detected
[2026-02-16 14:30:47] DOUBLE_CLICK detected
[2026-02-16 14:30:50] LONG_PRESS detected
```

### 3. LED Control - Turn Off (`demo_led_off.sh`)

**Purpose**: Turns off the Raspberry Pi activity LED (useful for Pi Zero and other models).

**Use Case**: Disable the LED for a cleaner look, reduce power consumption, or avoid light pollution in dark environments.

**Setup**:
1. Copy the script to a location accessible by the InkyPi service
2. Make it executable: `chmod +x demo_led_off.sh`
3. **Important**: The script requires `sudo` permissions. Ensure the InkyPi service user has passwordless sudo access for LED control:
   ```bash
   # Add to /etc/sudoers.d/inkypi-led (use visudo for safety)
   # Replace 'pi' with your InkyPi service user
   pi ALL=(ALL) NOPASSWD: /bin/sh -c echo* > /sys/class/leds/*
   ```
4. In Hardware Buttons plugin settings, bind this script to a button action

**Output**: Logs LED state changes to `~/.inkypi_button_logs/led_control.log` and saves the current LED state for restoration.

**Note**: The script automatically detects the LED path (`led0`, `ACT`, or `led1`) and saves the current state before turning it off.

### 4. LED Control - Restore (`demo_led_restore.sh`)

**Purpose**: Restores the Raspberry Pi activity LED to its normal function.

**Use Case**: Turn the LED back on after using `demo_led_off.sh`.

**Setup**:
1. Copy the script to a location accessible by the InkyPi service
2. Make it executable: `chmod +x demo_led_restore.sh`
3. Same sudo permissions required as `demo_led_off.sh` (see above)
4. In Hardware Buttons plugin settings, bind this script to a different button action (or the same button with a different press type)

**Output**: Restores the LED to its previous state (saved by `demo_led_off.sh`) and logs the restoration.

**Example Usage**:
- Bind `demo_led_off.sh` to **short press** on GPIO 17
- Bind `demo_led_restore.sh` to **double-click** on GPIO 17
- Short press turns LED off, double-click restores it

**Note**: If no saved state exists, the script defaults to `mmc0` trigger (normal activity LED behavior).

## Viewing Logs

View the logs via SSH:
```bash
# View system status log
cat ~/.inkypi_button_logs/system_status.log

# View button events log
cat ~/.inkypi_button_logs/button_events.log

# View LED control log
cat ~/.inkypi_button_logs/led_control.log

# Watch logs in real-time
tail -f ~/.inkypi_button_logs/*.log
```

## Customization Ideas

You can modify these scripts or create your own to:
- Send notifications (email, webhook, etc.)
- Trigger other system commands
- Update display content
- Control other GPIO devices
- Integrate with home automation systems
- Create custom shortcuts for common tasks

## Security Notes

- Scripts run with the same permissions as the InkyPi service user
- Scripts have a 30-second timeout enforced by the plugin
- Use absolute paths when configuring scripts in the plugin settings
- Test scripts manually before binding them to buttons
- Keep scripts simple and avoid long-running operations

## Troubleshooting

- **Script not executing**: Check file permissions (`chmod +x`) and ensure the path is absolute
- **No output**: Check that the log directory exists and is writable
- **Timeout errors**: Ensure scripts complete within 30 seconds
- **Permission errors**: Verify the InkyPi service user has access to the script location
- **LED scripts fail**: Ensure sudo permissions are configured (see LED Control scripts setup above). Test manually: `sudo sh -c "echo none > /sys/class/leds/led0/trigger"`
