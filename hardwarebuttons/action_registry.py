"""Action registry for hardware button plugin action registration.

This module provides a central registry where plugins can register custom actions
that can be bound to hardware buttons. Two types of actions are supported:

1. Anytime actions: Can be triggered at any time, regardless of what is displayed
2. Display actions: Only triggered when the registering plugin is currently displayed

Thread-safe for registration and execution from GPIO callbacks or API routes.

Architecture:
- Plugins register actions via register_actions() during blueprint initialization
- discovery.py queries the registry to build the action dropdown list
- actions.py executes registered actions when buttons are pressed
- Execution happens in GPIO thread context, outside Flask request context
"""

import logging
import threading

logger = logging.getLogger(__name__)

# Global registry structure
_action_registry = {
    "anytime": {},   # action_id -> {label, plugin_id, callback}
    "display": {},   # plugin_id -> [callback_0, callback_1, ...]
}
_registry_lock = threading.Lock()

# Maximum display actions per plugin (keeps dropdown manageable)
MAX_DISPLAY_ACTIONS = 6


def register_actions(plugin_id, anytime_actions=None, display_actions=None):
    """Register actions for hardware button bindings.
    
    This function should be called from a plugin's blueprint record_once callback
    during plugin initialization.
    
    Args:
        plugin_id: str - unique plugin identifier (e.g., "weather", "calendar")
        anytime_actions: dict or None
            {
                "action_name": {
                    "label": "User-visible action label",
                    "callback": callable(refs) -> None
                },
                ...
            }
        display_actions: list or None
            [
                callable(refs) -> None,  # Display Action 1
                callable(refs) -> None,  # Display Action 2
                ...
            ]
    
    Example:
        @my_bp.record_once
        def _register_actions(state):
            from plugins.hardwarebuttons import action_registry
            
            def reload_data(refs):
                # Reload plugin data...
                pass
            
            def next_item(refs):
                # Navigate to next item when this plugin is displayed
                pass
            
            action_registry.register_actions(
                plugin_id="my_plugin",
                anytime_actions={
                    "reload": {
                        "label": "Reload My Plugin Data",
                        "callback": reload_data
                    }
                },
                display_actions=[next_item]
            )
    """
    if not plugin_id or not isinstance(plugin_id, str):
        logger.warning("register_actions: invalid plugin_id (must be non-empty string): %s", plugin_id)
        return
    
    with _registry_lock:
        # Register anytime actions
        if anytime_actions:
            if not isinstance(anytime_actions, dict):
                logger.warning("register_actions: anytime_actions must be a dict for plugin %s", plugin_id)
            else:
                for action_name, action_config in anytime_actions.items():
                    if not isinstance(action_config, dict):
                        logger.warning("register_actions: anytime_actions[%s] must be a dict for plugin %s", action_name, plugin_id)
                        continue
                    
                    label = action_config.get("label")
                    callback = action_config.get("callback")
                    
                    if not label or not isinstance(label, str):
                        logger.warning("register_actions: anytime action %s.%s missing valid label", plugin_id, action_name)
                        continue
                    
                    if not callable(callback):
                        logger.warning("register_actions: anytime action %s.%s callback is not callable", plugin_id, action_name)
                        continue
                    
                    action_id = f"{plugin_id}_{action_name}"
                    _action_registry["anytime"][action_id] = {
                        "label": label,
                        "plugin_id": plugin_id,
                        "callback": callback,
                    }
                    logger.info("Registered anytime action: %s (label: %s)", action_id, label)
        
        # Register display actions
        if display_actions:
            if not isinstance(display_actions, list):
                logger.warning("register_actions: display_actions must be a list for plugin %s", plugin_id)
            else:
                # Validate all are callables
                valid_actions = []
                for i, action in enumerate(display_actions):
                    if not callable(action):
                        logger.warning("register_actions: display_actions[%d] is not callable for plugin %s", i, plugin_id)
                        continue
                    valid_actions.append(action)
                
                if len(valid_actions) > MAX_DISPLAY_ACTIONS:
                    logger.warning(
                        "register_actions: plugin %s registered %d display actions, limiting to %d",
                        plugin_id, len(valid_actions), MAX_DISPLAY_ACTIONS
                    )
                    valid_actions = valid_actions[:MAX_DISPLAY_ACTIONS]
                
                if valid_actions:
                    _action_registry["display"][plugin_id] = valid_actions
                    logger.info("Registered %d display action(s) for plugin %s", len(valid_actions), plugin_id)


def get_all_anytime_actions():
    """Get all registered anytime actions for dropdown population.
    
    Returns:
        List of dicts: [{"id": str, "label": str, "group": str, "plugin_id": str}, ...]
        Sorted by label for consistent UI ordering.
    """
    with _registry_lock:
        actions = []
        for action_id, action_info in _action_registry["anytime"].items():
            actions.append({
                "id": action_id,
                "label": action_info["label"],
                "group": "Other Plugins",
                "plugin_id": action_info["plugin_id"],
            })
        # Sort by label for consistent ordering
        actions.sort(key=lambda a: a["label"].lower())
        return actions


def get_max_display_action_count():
    """Get the maximum number of display actions registered by any plugin.
    
    This determines how many "Display Action N" entries to show in the binding dropdown.
    
    Returns:
        int: Maximum display action count (0 if no plugins registered display actions)
    """
    with _registry_lock:
        if not _action_registry["display"]:
            return 0
        return max(len(actions) for actions in _action_registry["display"].values())


def get_display_action(plugin_id, action_index):
    """Get a specific display action callback for a plugin.
    
    Args:
        plugin_id: str - plugin identifier
        action_index: int - 0-based index into the plugin's display actions array
    
    Returns:
        callable or None: The action callback if it exists, None otherwise
    """
    with _registry_lock:
        actions = _action_registry["display"].get(plugin_id)
        if not actions or action_index < 0 or action_index >= len(actions):
            return None
        return actions[action_index]


def execute_plugin_action(action_id, refs):
    """Execute a registered anytime action by its ID.
    
    Args:
        action_id: str - full action ID (e.g., "weather_reload")
        refs: dict - context refs (device_config, refresh_task, app, etc.)
    
    Raises:
        ValueError: If action_id is not registered
        Exception: Re-raises any exception from the callback after logging
    """
    with _registry_lock:
        action_info = _action_registry["anytime"].get(action_id)
    
    if not action_info:
        raise ValueError(f"Action {action_id} is not registered")
    
    callback = action_info["callback"]
    plugin_id = action_info["plugin_id"]
    
    logger.info("Executing anytime action: %s (plugin: %s)", action_id, plugin_id)
    try:
        callback(refs)
        logger.debug("Anytime action %s completed successfully", action_id)
    except Exception as e:
        logger.exception("Anytime action %s raised exception: %s", action_id, e)
        raise


def execute_display_action(action_index, refs):
    """Execute a display action for the currently displayed plugin.
    
    Resolves the current plugin from refresh_info, looks up its display actions,
    and executes the action at the specified index if it exists.
    
    Args:
        action_index: int - 0-based index (0 = "Display Action 1", 1 = "Display Action 2", etc.)
        refs: dict - context refs with device_config, refresh_task, app, etc.
    
    Returns:
        bool: True if action was executed, False if no action available
    """
    device_config = refs.get("device_config")
    if not device_config:
        logger.warning("execute_display_action: no device_config in refs")
        return False
    
    # Get current plugin from refresh_info
    refresh_info = device_config.get_refresh_info()
    if not refresh_info:
        logger.warning("execute_display_action: no refresh_info available (nothing displayed yet?)")
        return False
    
    current_plugin_id = getattr(refresh_info, "plugin_id", None)
    if not current_plugin_id:
        logger.warning("execute_display_action: no plugin_id in refresh_info")
        return False
    
    # Look up display action for current plugin
    with _registry_lock:
        actions = _action_registry["display"].get(current_plugin_id)
    
    if not actions:
        logger.debug(
            "execute_display_action: plugin %s has no display actions registered (action_index=%d)",
            current_plugin_id, action_index
        )
        return False
    
    if action_index < 0 or action_index >= len(actions):
        logger.debug(
            "execute_display_action: plugin %s only has %d display action(s), cannot execute index %d",
            current_plugin_id, len(actions), action_index
        )
        return False
    
    callback = actions[action_index]
    
    # Resolve current plugin instance if available
    current_instance = None
    if refresh_info.refresh_type == "Playlist":
        playlist_name = getattr(refresh_info, "playlist", None)
        instance_name = getattr(refresh_info, "plugin_instance", None)
        if playlist_name and instance_name:
            playlist_manager = device_config.get_playlist_manager()
            playlist = playlist_manager.get_playlist(playlist_name)
            if playlist:
                current_instance = playlist.find_plugin(current_plugin_id, instance_name)
    
    # Add current_plugin_instance to refs for display actions
    refs_with_instance = dict(refs)
    refs_with_instance["current_plugin_instance"] = current_instance
    
    logger.info(
        "Executing display action %d for plugin %s (instance: %s)",
        action_index, current_plugin_id, instance_name if current_instance else "N/A"
    )
    
    try:
        callback(refs_with_instance)
        logger.debug("Display action %d for plugin %s completed successfully", action_index, current_plugin_id)
        return True
    except Exception as e:
        logger.exception(
            "Display action %d for plugin %s raised exception: %s",
            action_index, current_plugin_id, e
        )
        raise


def get_registry_stats():
    """Get statistics about registered actions (for debugging/logging).
    
    Returns:
        dict: {"anytime_count": int, "plugins_with_display": int, "max_display": int}
    """
    with _registry_lock:
        return {
            "anytime_count": len(_action_registry["anytime"]),
            "plugins_with_display": len(_action_registry["display"]),
            "max_display": get_max_display_action_count(),
        }
