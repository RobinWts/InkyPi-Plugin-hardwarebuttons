"""Built-in action definitions and executor for hardware button bindings."""

import os
import logging
import subprocess
import threading
import urllib.request

logger = logging.getLogger(__name__)

# Only one action runs at a time; further triggers are ignored until it returns or times out
_action_lock = threading.Lock()
# Max seconds to wait for an action; after this the gate is released so new triggers can run
ACTION_MAX_DURATION_SEC = 120

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
}


def execute_action(refs, action_id, context=None):
    """Execute a button action. Only one action runs at a time; other triggers are ignored until it returns or times out.

    refs = dict with device_config, refresh_task, app (optional), port (optional).
    context: optional dict with script_path for external_script, etc.
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
        _run_action(refs, action_id, context or {})
        logger.debug("execute_action: action %s finished", action_id)
    finally:
        _action_lock.release()
        logger.debug("execute_action: lock released")


def _run_action(refs, action_id, context):
    """Inner implementation; must be called with _action_lock held. Runs in a thread with timeout so the lock is
    released after ACTION_MAX_DURATION_SEC even if the action hangs."""
    logger.debug("_run_action: starting worker thread for %s (timeout=%ss)", action_id, ACTION_MAX_DURATION_SEC)
    result = [None]  # hold exception if any

    def do_work():
        try:
            _run_action_impl(refs, action_id, context)
        except Exception as e:
            result[0] = e
            logger.exception("Action %s failed", action_id)

    worker = threading.Thread(target=do_work, daemon=True)
    worker.start()
    worker.join(timeout=ACTION_MAX_DURATION_SEC)
    if worker.is_alive():
        logger.debug("_run_action: worker for %s did not finish within timeout", action_id)
        logger.warning(
            "Action %s did not complete within %s s, allowing next trigger (previous action may still run)",
            action_id, ACTION_MAX_DURATION_SEC
        )
    if result[0]:
        raise result[0]


def _run_action_impl(refs, action_id, context):
    """Core logic; no locking. Called from worker thread inside _run_action."""
    logger.debug("_run_action_impl: action_id=%s", action_id)
    device_config = refs.get("device_config")
    refresh_task = refs.get("refresh_task")
    app = refs.get("app")
    port = refs.get("port", 80)

    if action_id == "external_script":
        logger.debug("_run_action_impl: running external_script")
        _run_external_script(context)
        return
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

    # Plugin-registered action: execute via HTTP
    if action_id.startswith("plugin_"):
        logger.debug("_run_action_impl: plugin action -> HTTP to plugin URL")
        _execute_plugin_action(action_id, device_config, port)
        return

    logger.warning("Unknown action_id: %s", action_id)


def _run_external_script(context):
    script_path = (context.get("script_path") or "").strip()
    logger.debug("_run_external_script: script_path=%s", script_path or "(empty)")
    if not script_path:
        logger.warning("external_script: no script_path in context")
        return
    # Restrict to absolute path under /home or allowlist; avoid arbitrary paths
    if not os.path.isabs(script_path):
        logger.warning("external_script: path must be absolute")
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


def _system_shutdown(app, reboot=False):
    # Run from worker thread; no request context. Use same commands as core /shutdown route.
    _system_shutdown_fallback(reboot)


def _system_shutdown_fallback(reboot):
    if reboot:
        os.system("sudo reboot")
    else:
        os.system("sudo shutdown -h now")


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


def _execute_plugin_action(action_id, device_config, port):
    """Resolve plugin action to URL and POST to it."""
    from .discovery import get_available_actions
    actions_list = get_available_actions(device_config)
    act = next((a for a in actions_list if a.get("id") == action_id), None)
    if not act or not act.get("url"):
        logger.warning("Plugin action %s not found or has no url", action_id)
        return
    url = act["url"]
    if not url.startswith("http"):
        url = f"http://127.0.0.1:{port}{url}" if url.startswith("/") else f"http://127.0.0.1:{port}/{url}"
    method = act.get("method", "POST").upper()
    logger.debug("_execute_plugin_action: %s %s", method, url)
    try:
        req = urllib.request.Request(url, data=b"", method=method, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as e:
        logger.warning("Plugin action HTTP %s %s failed: %s", method, url, e)
