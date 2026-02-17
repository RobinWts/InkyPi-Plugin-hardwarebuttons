"""Built-in action definitions and executor for hardware button bindings."""

import os
import logging
import subprocess
import threading
from . import action_registry

logger = logging.getLogger(__name__)

# Only one action runs at a time; further triggers are ignored until it returns.
_action_lock = threading.Lock()

# Action IDs that are built-in (not plugin-registered)
BUILTIN_ACTION_IDS = {
    "core_trigger_refresh",
    "core_force_refresh",
    "core_next_playlist",
    "core_prev_playlist",
    "system_shutdown",
    "system_reboot",
    "system_restart_inkypi",
    "external_script",
    "call_url",
}


def execute_action(refs, action_id, context=None):
    """Execute a button action. Only one action runs at a time; other triggers are ignored until it returns.

    refs = dict with device_config, refresh_task, app (optional).
    context: optional dict with script_path for external_script, url for call_url, etc.
    """
    logger.debug("execute_action called: action_id=%s", action_id)
    if not action_id or action_id == "none":
        logger.debug("execute_action: empty/none action_id -> no-op")
        return
    if not _action_lock.acquire(blocking=False):
        logger.debug("Action already in progress, ignoring trigger for %s", action_id)
        return
    try:
        logger.debug("execute_action: lock acquired, running action %s", action_id)
        _run_action_impl(refs, action_id, context or {})
        logger.debug("execute_action: action %s finished", action_id)
    finally:
        _action_lock.release()
        logger.debug("execute_action: lock released")


def _run_action_impl(refs, action_id, context):
    """Core logic; no locking. Called with _action_lock held by execute_action()."""
    logger.debug("_run_action_impl: action_id=%s", action_id)
    device_config = refs.get("device_config")
    refresh_task = refs.get("refresh_task")
    app = refs.get("app")

    # Handle actions with special context requirements first
    if action_id == "external_script":
        logger.debug("_run_action_impl: running external_script")
        _run_external_script(context)
        return
    if action_id == "call_url":
        logger.debug("_run_action_impl: running call_url")
        _call_url(context)
        return
    
    # Handle system actions
    if action_id == "system_shutdown":
        logger.debug("_run_action_impl: running system_shutdown")
        _system_shutdown(app, reboot=False)
        return
    if action_id == "system_reboot":
        logger.debug("_run_action_impl: running system_reboot")
        _system_shutdown(app, reboot=True)
        return
    if action_id == "system_restart_inkypi":
        logger.debug("_run_action_impl: running system_restart_inkypi")
        _restart_inkypi_service()
        return
    
    # ===== Plugin-Registered Actions =====
    # Plugins can register two types of actions via action_registry:
    # 1. Display actions: context-dependent, only work when that plugin is displayed
    # 2. Anytime actions: can be triggered anytime (e.g., "Reload Weather Data")
    
    # Check for display actions (display_action_0, display_action_1, etc.)
    # These are resolved to the currently displayed plugin's action array
    if action_id.startswith("display_action_"):
        try:
            action_index = int(action_id.split("_")[-1])
            logger.debug("_run_action_impl: display action index %d", action_index)
            action_registry.execute_display_action(action_index, refs)
            return
        except (ValueError, IndexError) as e:
            logger.warning("_run_action_impl: invalid display_action format: %s (%s)", action_id, e)
            return
        except Exception as e:
            logger.exception("_run_action_impl: display action %s failed: %s", action_id, e)
            return
    
    # Check for plugin-registered anytime actions (e.g., "weather_reload", "calendar_sync")
    if action_id not in BUILTIN_ACTION_IDS:
        # Could be a plugin action; try to execute it
        try:
            action_registry.execute_plugin_action(action_id, refs)
            return
        except ValueError:
            # Not a registered plugin action; fall through to core actions or unknown
            pass
        except Exception as e:
            logger.exception("_run_action_impl: plugin action %s failed: %s", action_id, e)
            return

    # Core playlist actions require refresh_task and device_config
    if not refresh_task or not device_config:
        logger.warning("Cannot run core action %s: missing refresh_task or device_config", action_id)
        return

    try:
        from refresh_task import PlaylistRefresh
        import pytz
        from datetime import datetime
    except ImportError:
        logger.exception("Import error in execute_action")
        return

    playlist_manager = device_config.get_playlist_manager()
    tz = pytz.timezone(device_config.get_config("timezone", default="UTC"))
    now = datetime.now(tz)

    if action_id in ("core_trigger_refresh", "core_next_playlist"):
        logger.debug("_run_action_impl: core next/trigger refresh -> get next playlist item")
        active_name = playlist_manager.active_playlist
        if not active_name:
            playlist = playlist_manager.determine_active_playlist(now)
        else:
            playlist = playlist_manager.get_playlist(active_name)
        if not playlist or not playlist.plugins:
            logger.info("No active playlist or no plugins for next/trigger refresh")
            return
        plugin_instance = playlist.get_next_plugin()
        logger.debug("_run_action_impl: manual_update PlaylistRefresh playlist=%s instance=%s", playlist.name, plugin_instance.name)
        refresh_task.manual_update(PlaylistRefresh(playlist, plugin_instance, force=True))
        return

    if action_id == "core_force_refresh":
        logger.debug("_run_action_impl: core_force_refresh -> re-show current")
        refresh_info = device_config.get_refresh_info()
        if not refresh_info or not getattr(refresh_info, "playlist", None) or not getattr(refresh_info, "plugin_instance", None):
            logger.info("Force refresh only supported when last refresh was from playlist")
            return
        playlist = playlist_manager.get_playlist(refresh_info.playlist)
        if not playlist:
            return
        instance = playlist.find_plugin(refresh_info.plugin_id, refresh_info.plugin_instance)
        if not instance:
            return
        logger.debug("_run_action_impl: manual_update PlaylistRefresh force current")
        refresh_task.manual_update(PlaylistRefresh(playlist, instance, force=True))
        return

    if action_id == "core_prev_playlist":
        logger.debug("_run_action_impl: core_prev_playlist -> previous item and write_config")
        active_name = playlist_manager.active_playlist
        if not active_name:
            playlist = playlist_manager.determine_active_playlist(now)
        else:
            playlist = playlist_manager.get_playlist(active_name)
        if not playlist or not playlist.plugins:
            return
        idx = playlist.current_plugin_index
        if idx is None:
            idx = 0
        prev_idx = (idx - 1) % len(playlist.plugins)
        playlist.current_plugin_index = prev_idx
        instance = playlist.plugins[prev_idx]
        refresh_task.manual_update(PlaylistRefresh(playlist, instance, force=True))
        device_config.write_config()
        return

    logger.warning("Unknown action_id: %s", action_id)


def _run_external_script(context):
    script_path = (context.get("script_path") or "").strip()
    logger.debug("_run_external_script: script_path=%s", script_path or "(empty)")
    if not script_path:
        logger.warning("external_script: no script_path in context")
        return
    # Expand ~ to home directory before validation
    script_path = os.path.expanduser(script_path)
    script_path = os.path.realpath(script_path)
    logger.debug("_run_external_script: expanded path=%s", script_path)
    # Restrict scripts to the service account home directory.
    # This keeps execution predictable and avoids running arbitrary system paths.
    home_dir = os.path.realpath(os.path.expanduser("~"))
    home_prefix = os.path.join(home_dir, "")
    if not os.path.isabs(script_path):
        logger.warning("external_script: path must be absolute (after expanding ~): %s", script_path)
        return
    if not script_path.startswith(home_prefix):
        logger.warning("external_script: path must be under %s: %s", home_dir, script_path)
        return
    if not os.path.isfile(script_path):
        logger.warning("external_script: file not found: %s", script_path)
        return
    logger.debug("_run_external_script: executing bash %s (timeout=30s)", script_path)
    try:
        subprocess.run(
            ["bash", script_path],
            timeout=30,
            cwd=os.path.dirname(script_path),
            env=os.environ.copy(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("external_script: timeout running %s", script_path)
    except Exception as e:
        logger.warning("external_script: %s", e)


def _call_url(context):
    """Call a URL via curl when button is triggered."""
    url = (context.get("url") or "").strip()
    logger.debug("_call_url: url=%s", url or "(empty)")
    if not url:
        logger.warning("call_url: no url in context")
        return
    # Basic URL validation: must start with http:// or https://
    if not (url.startswith("http://") or url.startswith("https://")):
        logger.warning("call_url: url must start with http:// or https://: %s", url)
        return
    logger.info("call_url: calling URL %s", url)
    try:
        # Use curl with timeout and follow redirects
        result = subprocess.run(
            ["curl", "-s", "-f", "-L", "--max-time", "10", url],
            timeout=15,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            logger.debug("call_url: successfully called %s (status=%d)", url, result.returncode)
        else:
            logger.warning("call_url: curl returned non-zero exit code %d for %s", result.returncode, url)
            if result.stderr:
                logger.debug("call_url: curl stderr: %s", result.stderr[:200])
    except subprocess.TimeoutExpired:
        logger.warning("call_url: timeout calling %s", url)
    except FileNotFoundError:
        logger.warning("call_url: curl command not found, cannot call URL")
    except Exception as e:
        logger.warning("call_url: error calling %s: %s", url, e)


def _system_shutdown(app, reboot=False):
    # Run without request context. Use the same command family as the core /shutdown route.
    _system_shutdown_fallback(reboot)


def _system_shutdown_fallback(reboot):
    command = ["sudo", "reboot"] if reboot else ["sudo", "shutdown", "-h", "now"]
    try:
        subprocess.run(command, timeout=10, check=False)
    except Exception as e:
        logger.warning("System %s command failed: %s", "reboot" if reboot else "shutdown", e)


def _restart_inkypi_service():
    service_name = os.environ.get("APPNAME", "inkypi")
    try:
        subprocess.run(
            ["sudo", "systemctl", "restart", f"{service_name}.service"],
            timeout=10,
            check=False,
        )
    except Exception as e:
        logger.warning("Restart InkyPi service failed: %s", e)


    # Note: intentionally no "plugin_*" action execution. This plugin only supports the
    # built-in Core/System actions plus its own external_script and call_url actions.
