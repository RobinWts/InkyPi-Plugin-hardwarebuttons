"""Discover available button actions for the hardwarebuttons plugin.

Builds a list of all available actions including:
- Built-in Core/System actions
- Plugin-registered anytime actions
- Generic display actions (based on max registered by any plugin)
"""

import logging
from . import action_registry

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
    {"id": "call_url", "label": "Call URL", "group": "System"},
]
# No-action option for dropdowns
NO_ACTION_ID = ""


def get_available_actions(device_config):
    """Build list of actions for dropdowns.

    Includes:
    - Built-in Core/System actions (refresh, shutdown, etc.)
    - Plugin-registered anytime actions (e.g., "Reload Weather Data")
    - Generic "Display Action N" entries based on max registered by any plugin

    Action groups in the UI:
    - "Core": InkyPi core actions (refresh, playlist navigation)
    - "System": System actions (shutdown, reboot, scripts, URLs)
    - "Current Plugin": Display actions (context-dependent, work when that plugin is shown)
    - "Other Plugins": Anytime actions from other plugins (work anytime)

    Args:
        device_config: Config instance (unused; kept for backward compatibility with callers).

    Returns:
        List of dicts: id, label, group ("Core" | "System" | "Current Plugin" | "Other Plugins").
    """
    logger.debug("get_available_actions called")
    out = []
    
    # No-action first
    out.append({"id": NO_ACTION_ID, "label": "(No action)", "group": "Core"})

    # Built-in Core/System actions
    for a in BUILTIN_ACTIONS:
        out.append(dict(a))
    logger.debug("get_available_actions: added %d built-in actions", len(BUILTIN_ACTIONS))
    
    # Plugin-registered anytime actions
    plugin_anytime_actions = action_registry.get_all_anytime_actions()
    out.extend(plugin_anytime_actions)
    logger.debug("get_available_actions: added %d plugin anytime actions", len(plugin_anytime_actions))
    
    # Generic display actions (based on max registered)
    max_display = action_registry.get_max_display_action_count()
    for i in range(max_display):
        out.append({
            "id": f"display_action_{i}",
            "label": f"Display Action {i + 1}",
            "group": "Current Plugin",
        })
    logger.debug("get_available_actions: added %d generic display actions", max_display)
    
    logger.debug("get_available_actions: total %d actions", len(out))
    return out
