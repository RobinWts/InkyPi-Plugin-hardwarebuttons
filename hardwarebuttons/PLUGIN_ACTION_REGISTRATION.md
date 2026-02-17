# Plugin Action Registration Guide

This guide explains how plugin developers can register custom actions that can be bound to hardware buttons.

## Overview

The Hardware Buttons plugin provides a registration system that allows any InkyPi plugin to expose actions that users can bind to physical buttons. This enables rich interactions like:

- **Weather plugin**: "Update Weather Now", "Next City", "Previous City"
- **Calendar plugin**: "Sync Calendar", "Next Event", "Previous Event"
- **Image folder plugin**: "Next Image", "Previous Image", "Random Image"
- **Todo list plugin**: "Add Task", "Complete Current Task", "Next Task"


## Two Types of Actions

### 1. Anytime Actions

**Anytime actions** can be triggered at any moment, regardless of what is currently displayed on the screen.

**Use cases:**
- Reload/refresh plugin data from an API
- Toggle a plugin setting or mode
- Trigger a background task
- Send a notification

**Characteristics:**
- Each action has a descriptive label shown in the button binding UI
- Actions appear in the "Other Plugins" section of the dropdown
- Can be executed even when a different plugin is displayed

**Example:** A weather plugin's "Update Weather Now" action can be triggered even when a clock plugin is currently displayed.

### 2. Display Actions

**Display actions** can only be triggered when an instance of the registering plugin is currently displayed on the screen.

**Use cases:**
- Navigate through slides or pages within a plugin
- Interact with the currently displayed content
- Context-specific actions that only make sense for the active view

**Characteristics:**
- Plugins register an array of 0-6 display actions
- The UI shows generic labels: "Display Action 1", "Display Action 2", etc.
- Actions appear in the "Current Plugin" section of the dropdown
- When triggered, the system checks which plugin is displayed and executes the corresponding action

**Example:** An image folder plugin's "Next Image" and "Previous Image" actions only work when that image folder instance is displayed.

## How to Register Actions

For a simple example for registering both types of actions see [Plugin-HWButtonRegTest](https://github.com/RobinWts/InkyPi-Plugin-HWButtonRegTest).

### Step 1: Create a Blueprint (if you don't have one)

Your plugin needs a Flask Blueprint to register actions. If you don't have one yet:

```python
# In your plugin folder, create api.py
from flask import Blueprint

my_plugin_bp = Blueprint("my_plugin_api", __name__)

# In your plugin class file (e.g., my_plugin.py)
from plugins.base_plugin.base_plugin import BasePlugin

class MyPlugin(BasePlugin):
    @classmethod
    def get_blueprint(cls):
        from . import api
        return api.my_plugin_bp
    
    def generate_image(self, settings, device_config):
        # Your plugin logic...
        pass
```

See [Advanced Plugin Development](../../../docs/advanced_plugin_development.md) for more details on blueprints.

### Step 2: Register Actions in Blueprint Initialization

Use `Blueprint.record_once` to register your actions when the blueprint is loaded:

```python
# In api.py
from flask import Blueprint

my_plugin_bp = Blueprint("my_plugin_api", __name__)

@my_plugin_bp.record_once
def _register_actions(state):
    """Register button actions when blueprint is initialized."""
    # Import action_registry from hardwarebuttons plugin
    try:
        from plugins.hardwarebuttons import action_registry
    except ImportError:
        # Hardware buttons plugin not installed; skip registration
        return
    
    # Define your action callbacks
    def reload_data(refs):
        """Reload plugin data (anytime action)."""
        device_config = refs.get("device_config")
        # Your reload logic here...
        pass
    
    def next_item(refs):
        """Navigate to next item (display action)."""
        current_instance = refs.get("current_plugin_instance")
        if current_instance:
            # Get current settings
            settings = current_instance.settings
            # Update navigation state...
            pass
    
    def prev_item(refs):
        """Navigate to previous item (display action)."""
        current_instance = refs.get("current_plugin_instance")
        if current_instance:
            settings = current_instance.settings
            # Update navigation state...
            pass
    
    # Register actions
    action_registry.register_actions(
        plugin_id="my_plugin",
        anytime_actions={
            "reload": {
                "label": "Reload My Plugin Data",
                "callback": reload_data
            }
        },
        display_actions=[
            next_item,  # Display Action 1
            prev_item,  # Display Action 2
        ]
    )
```

## Action Callback Signature

All action callbacks receive a single `refs` dict containing:

| Key | Type | Description | Available For |
|-----|------|-------------|---------------|
| `device_config` | `Config` | Device configuration, playlists, plugins | All actions |
| `refresh_task` | `RefreshTask` | Trigger manual refreshes | All actions |
| `app` | Flask app | Flask application instance | All actions |
| `current_plugin_instance` | `PluginInstance` or `None` | Currently displayed plugin instance | Display actions only |

### Using the Refs

```python
def my_action(refs):
    # Get device config
    device_config = refs.get("device_config")
    
    # Access resolution
    width, height = device_config.get_resolution()
    
    # Get refresh task to trigger display updates
    refresh_task = refs.get("refresh_task")
    
    # Get Flask app to create app context if needed
    app = refs.get("app")
    with app.app_context():
        # Can now access current_app, etc.
        pass
    
    # For display actions: get current instance
    current_instance = refs.get("current_plugin_instance")
    if current_instance:
        # Access instance settings, name, etc.
        settings = current_instance.settings
        instance_name = current_instance.name
```

## Complete Examples

### Example 1: Image Folder Plugin with Navigation

```python
# In image_folder/api.py
from flask import Blueprint

image_folder_bp = Blueprint("image_folder_api", __name__)

@image_folder_bp.record_once
def _register_actions(state):
    try:
        from plugins.hardwarebuttons import action_registry
    except ImportError:
        return
    
    def reload_images(refs):
        """Reload images from folder (anytime action)."""
        device_config = refs.get("device_config")
        # Trigger re-scan of image folder
        # (implementation depends on your plugin structure)
        pass
    
    def next_image(refs):
        """Show next image (display action)."""
        current_instance = refs.get("current_plugin_instance")
        if not current_instance:
            return
        
        device_config = refs.get("device_config")
        refresh_task = refs.get("refresh_task")
        
        # Get current index from settings
        settings = current_instance.settings
        current_index = settings.get("current_index", 0)
        image_count = settings.get("image_count", 1)
        
        # Advance to next image
        next_index = (current_index + 1) % image_count
        settings["current_index"] = next_index
        
        # Persist the change
        device_config.write_config()
        
        # Trigger a refresh to show the new image
        from refresh_task import ManualRefresh
        refresh_task.manual_update(ManualRefresh("image_folder", settings))
    
    def prev_image(refs):
        """Show previous image (display action)."""
        current_instance = refs.get("current_plugin_instance")
        if not current_instance:
            return
        
        device_config = refs.get("device_config")
        refresh_task = refs.get("refresh_task")
        settings = current_instance.settings
        
        current_index = settings.get("current_index", 0)
        image_count = settings.get("image_count", 1)
        
        # Go to previous image
        prev_index = (current_index - 1) % image_count
        settings["current_index"] = prev_index
        device_config.write_config()
        
        from refresh_task import ManualRefresh
        refresh_task.manual_update(ManualRefresh("image_folder", settings))
    
    def random_image(refs):
        """Show random image (display action)."""
        current_instance = refs.get("current_plugin_instance")
        if not current_instance:
            return
        
        import random
        device_config = refs.get("device_config")
        refresh_task = refs.get("refresh_task")
        settings = current_instance.settings
        
        image_count = settings.get("image_count", 1)
        settings["current_index"] = random.randint(0, image_count - 1)
        device_config.write_config()
        
        from refresh_task import ManualRefresh
        refresh_task.manual_update(ManualRefresh("image_folder", settings))
    
    action_registry.register_actions(
        plugin_id="image_folder",
        anytime_actions={
            "reload": {
                "label": "Reload Image Folder",
                "callback": reload_images
            }
        },
        display_actions=[
            next_image,    # Display Action 1
            prev_image,    # Display Action 2
            random_image,  # Display Action 3
        ]
    )
```

### Example 2: Weather Plugin with City Navigation

```python
# In weather/api.py
from flask import Blueprint

weather_bp = Blueprint("weather_api", __name__)

@weather_bp.record_once
def _register_actions(state):
    try:
        from plugins.hardwarebuttons import action_registry
    except ImportError:
        return
    
    def update_weather(refs):
        """Force update weather data (anytime action)."""
        # Clear cache, fetch fresh data
        # This can run even when weather isn't displayed
        pass
    
    def next_city(refs):
        """Show next city in the list (display action)."""
        current_instance = refs.get("current_plugin_instance")
        if not current_instance:
            return
        
        settings = current_instance.settings
        cities = settings.get("cities", ["New York"])
        current_city_index = settings.get("current_city_index", 0)
        
        # Cycle to next city
        next_index = (current_city_index + 1) % len(cities)
        settings["current_city_index"] = next_index
        
        device_config = refs.get("device_config")
        device_config.write_config()
        
        # Refresh display with new city
        refresh_task = refs.get("refresh_task")
        from refresh_task import ManualRefresh
        refresh_task.manual_update(ManualRefresh("weather", settings))
    
    def prev_city(refs):
        """Show previous city (display action)."""
        current_instance = refs.get("current_plugin_instance")
        if not current_instance:
            return
        
        settings = current_instance.settings
        cities = settings.get("cities", ["New York"])
        current_city_index = settings.get("current_city_index", 0)
        
        prev_index = (current_city_index - 1) % len(cities)
        settings["current_city_index"] = prev_index
        
        device_config = refs.get("device_config")
        device_config.write_config()
        
        refresh_task = refs.get("refresh_task")
        from refresh_task import ManualRefresh
        refresh_task.manual_update(ManualRefresh("weather", settings))
    
    action_registry.register_actions(
        plugin_id="weather",
        anytime_actions={
            "update": {
                "label": "Update Weather Now",
                "callback": update_weather
            }
        },
        display_actions=[
            next_city,  # Display Action 1
            prev_city,  # Display Action 2
        ]
    )
```

### Example 3: Calendar Plugin with Sync

```python
# In calendar/api.py
from flask import Blueprint

calendar_bp = Blueprint("calendar_api", __name__)

@calendar_bp.record_once
def _register_actions(state):
    try:
        from plugins.hardwarebuttons import action_registry
    except ImportError:
        return
    
    def sync_calendar(refs):
        """Sync calendar from remote source (anytime action)."""
        # Fetch latest events from Google Calendar, etc.
        pass
    
    def toggle_view(refs):
        """Toggle between day/week/month view (display action)."""
        current_instance = refs.get("current_plugin_instance")
        if not current_instance:
            return
        
        settings = current_instance.settings
        views = ["day", "week", "month"]
        current_view = settings.get("view", "week")
        current_index = views.index(current_view)
        next_index = (current_index + 1) % len(views)
        settings["view"] = views[next_index]
        
        device_config = refs.get("device_config")
        device_config.write_config()
        
        refresh_task = refs.get("refresh_task")
        from refresh_task import ManualRefresh
        refresh_task.manual_update(ManualRefresh("calendar", settings))
    
    action_registry.register_actions(
        plugin_id="calendar",
        anytime_actions={
            "sync": {
                "label": "Sync Calendar",
                "callback": sync_calendar
            }
        },
        display_actions=[
            toggle_view,  # Display Action 1
        ]
    )
```

## Best Practices

### 1. Check for Hardware Buttons Plugin

Always wrap your registration in a try/except to handle cases where the hardware buttons plugin is not installed:

```python
try:
    from plugins.hardwarebuttons import action_registry
except ImportError:
    return  # Hardware buttons plugin not installed
```

### 2. Validate Current Instance

For display actions, always check that `current_plugin_instance` exists:

```python
def my_display_action(refs):
    current_instance = refs.get("current_plugin_instance")
    if not current_instance:
        return  # Not displayed or no instance info
    # ... proceed with action
```

### 3. Persist State Changes

If your action modifies plugin instance settings, persist them:

```python
def my_action(refs):
    current_instance = refs.get("current_plugin_instance")
    if current_instance:
        settings = current_instance.settings
        settings["my_field"] = new_value
        
        device_config = refs.get("device_config")
        device_config.write_config()  # Persist to disk
```

### 4. Trigger Refresh After State Change

If your action changes what should be displayed, trigger a manual refresh:

```python
def my_action(refs):
    # Update state...
    
    refresh_task = refs.get("refresh_task")
    from refresh_task import ManualRefresh
    refresh_task.manual_update(ManualRefresh("my_plugin", settings))
```

### 5. Thread Safety

Action callbacks are executed from the GPIO thread, not from a Flask request context. If you need to access Flask features:

```python
def my_action(refs):
    app = refs.get("app")
    with app.app_context():
        # Now you can use current_app, etc.
        from flask import current_app
        # ...
```

### 6. Error Handling

The action registry will catch and log exceptions from your callbacks, but it's good practice to handle errors gracefully:

```python
def my_action(refs):
    try:
        # Your action logic
        pass
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Action failed: {e}")
        # Optionally show an error on display
```

### 7. Limit Display Actions

Maximum of 6 display actions per plugin. Keep them focused and essential.

### 8. Use Descriptive Labels

For anytime actions, use clear, action-oriented labels:
- ✅ "Reload Weather Data"
- ✅ "Sync Calendar Now"
- ❌ "Weather"
- ❌ "Update"

## Document Your Actions

In your plugin's README.md, document the available actions:

```markdown
## Hardware Button Actions

This plugin supports the following button actions:

### Anytime Actions
- **Reload Images**: Re-scans the configured folder for new images

### Display Actions (when plugin is displayed)
1. **Next Image**: Shows the next image in the folder
2. **Previous Image**: Shows the previous image
3. **Random Image**: Jumps to a random image
```

## Testing Your Actions

1. Start InkyPi with your plugin installed
2. Open Hardware Buttons settings
3. Verify your actions appear in the dropdown
4. Configure a button binding for your action
5. Test the button press
6. Check logs for any errors: `journalctl -u inkypi.service -f`

## Troubleshooting

### Actions Don't Appear in Dropdown

- Verify your plugin has a `get_blueprint()` method
- Check that `register_actions()` is called in `@blueprint.record_once`
- Look for registration errors in the logs
- Restart InkyPi after making changes

### Display Actions Not Working

- Ensure the plugin instance is currently displayed
- Check that `get_refresh_info().plugin_id` matches your plugin_id
- Verify action index is within the registered array bounds
- Check logs for "no display actions registered" messages

### Actions Raise Exceptions

- Ensure callbacks handle the `refs` dict correctly
- Validate `current_plugin_instance` exists for display actions
- Check that imports (like `refresh_task.ManualRefresh`) are available
- Wrap risky code in try/except blocks

## Advanced Topics

### Refreshing Another Plugin Instance

You can trigger a refresh of any plugin instance from your action:

```python
def my_action(refs):
    device_config = refs.get("device_config")
    refresh_task = refs.get("refresh_task")
    
    # Find a specific playlist and instance
    pm = device_config.get_playlist_manager()
    playlist = pm.get_playlist("Default")
    if playlist:
        instance = playlist.find_plugin("clock", "My Clock")
        if instance:
            from refresh_task import PlaylistRefresh
            refresh_task.manual_update(PlaylistRefresh(playlist, instance, force=True))
```

### Accessing Plugin Data

Store and retrieve plugin-specific data:

```python
import os
import json

def save_plugin_data(plugin_id, key, value):
    from utils.app_utils import resolve_path
    plugins_dir = resolve_path("plugins")
    data_file = os.path.join(plugins_dir, plugin_id, "plugin_data.json")
    
    data = {}
    if os.path.isfile(data_file):
        with open(data_file) as f:
            data = json.load(f)
    
    data[key] = value
    
    with open(data_file, "w") as f:
        json.dump(data, f, indent=2)
```

### Conditional Actions

Register different actions based on configuration:

```python
@my_bp.record_once
def _register_actions(state):
    from plugins.hardwarebuttons import action_registry
    
    # Check if certain features are enabled
    app = state.app
    device_config = app.config.get("DEVICE_CONFIG")
    plugin_config = device_config.get_config("my_plugin", default={})
    
    actions_to_register = {}
    
    if plugin_config.get("feature_x_enabled"):
        actions_to_register["feature_x"] = {
            "label": "Trigger Feature X",
            "callback": feature_x_callback
        }
    
    if actions_to_register:
        action_registry.register_actions(
            plugin_id="my_plugin",
            anytime_actions=actions_to_register
        )
```

## See Also

- [Advanced Plugin Development](../../../docs/advanced_plugin_development.md) - Blueprint registration and core services
- [Hardware Buttons Plugin README](./README.md) - Installing and configuring the hardware buttons plugin
- [Building InkyPi Plugins](../../../docs/building_plugins.md) - General plugin development guide
