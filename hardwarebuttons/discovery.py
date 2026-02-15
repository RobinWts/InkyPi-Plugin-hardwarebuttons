"""Discover built-in and plugin-registered button actions for the hardwarebuttons plugin."""

import logging
from plugins.plugin_registry import get_plugin_instance

logger = logging.getLogger(__name__)

# Built-in action IDs and labels (grouped as Core / System)
BUILTIN_ACTIONS = [
    {"id": "core_trigger_refresh", "label": "Trigger refresh (next in playlist)", "group": "Core"},
    {"id": "core_force_refresh", "label": "Force refresh (re-show current)", "group": "Core"},
    {"id": "core_next_playlist", "label": "Next playlist item", "group": "Core"},
    {"id": "core_prev_playlist", "label": "Previous playlist item", "group": "Core"},
    {"id": "system_shutdown", "label": "Shutdown", "group": "System"},
    {"id": "system_reboot", "label": "Reboot", "group": "System"},
    {"id": "system_restart_inkypi", "label": "Restart InkyPi service", "group": "System"},
    {"id": "external_script", "label": "Run external bash script", "group": "System"},
]
# No-action option for dropdowns
NO_ACTION_ID = ""


def get_available_actions(device_config):
    """Build list of all actions: built-in + plugin-registered, with Current vs Other grouping.

    Args:
        device_config: Config instance (from app or generate_settings_template context).

    Returns:
        List of dicts: id, label, group ("Core" | "System" | "Current plugin" | "Other plugins"),
        and for plugin actions: url, method, plugin_id.
    """
    out = []
    # No-action first
    out.append({"id": NO_ACTION_ID, "label": "(No action)", "group": "Core"})

    for a in BUILTIN_ACTIONS:
        out.append(dict(a))

    refresh_info = device_config.get_refresh_info() if device_config else None
    currently_displayed_plugin_id = getattr(refresh_info, "plugin_id", None) if refresh_info else None
    context = {"currently_displayed_plugin_id": currently_displayed_plugin_id}

    plugins = device_config.get_plugins() if device_config else []
    for plugin_config in plugins:
        plugin_id = plugin_config.get("id")
        if not plugin_id:
            continue
        try:
            plugin_class = get_plugin_instance(plugin_config)
        except Exception as e:
            logger.debug("Could not get plugin instance for %s: %s", plugin_id, e)
            continue
        if not hasattr(plugin_class, "get_button_actions"):
            continue
        try:
            actions = plugin_class.get_button_actions(context)
        except Exception as e:
            logger.warning("get_button_actions failed for plugin %s: %s", plugin_id, e)
            continue
        if not actions:
            continue
        group = "Current plugin" if plugin_id == currently_displayed_plugin_id else "Other plugins"
        display_name = plugin_config.get("display_name") or plugin_id
        group_label = f"{group}: {display_name}"
        for act in actions:
            if not isinstance(act, dict):
                continue
            action_id = act.get("id") or act.get("label")
            if not action_id:
                continue
            # Prefer plugin-scoped id to avoid clashes
            scoped_id = f"plugin_{plugin_id}_{action_id}" if not str(action_id).startswith("plugin_") else action_id
            out.append({
                "id": scoped_id,
                "label": act.get("label", str(action_id)),
                "group": group_label,
                "url": act.get("url"),
                "method": act.get("method", "POST"),
                "plugin_id": plugin_id,
            })
    return out
