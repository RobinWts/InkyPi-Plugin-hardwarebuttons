"""API routes for hardwarebuttons plugin."""

import os
import logging
import subprocess

from flask import Blueprint, request, jsonify, current_app

from .discovery import get_available_actions
from . import actions
from . import button_manager

logger = logging.getLogger(__name__)

hardwarebuttons_bp = Blueprint("hardwarebuttons_api", __name__)

# Stored refs for use from GPIO worker thread (set at registration or on first request)
_core_refs = None

DEFAULT_TIMINGS = {
    "short_press_ms": 500,
    "double_click_interval_ms": 500,
    "long_press_ms": 1000,
}


@hardwarebuttons_bp.record_once
def _on_blueprint_registered(state):
    """Capture refs at startup when blueprint is registered so buttons work without opening settings."""
    global _core_refs
    app = state.app
    device_config = app.config.get("DEVICE_CONFIG")
    refresh_task = app.config.get("REFRESH_TASK")
    if device_config is None or refresh_task is None:
        logger.debug("_on_blueprint_registered: DEVICE_CONFIG or REFRESH_TASK missing, skipping")
        return
    _core_refs = {
        "device_config": device_config,
        "refresh_task": refresh_task,
        "app": app,
        "port": 80,
    }
    logger.debug("_on_blueprint_registered: captured refs at startup, starting button manager")
    button_manager.start_if_needed(_core_refs)


def _capture_refs():
    global _core_refs
    if _core_refs is not None:
        # Update port from request when available (e.g. dev mode uses 8080)
        if request:
            try:
                port = request.environ.get("SERVER_PORT", "80")
                _core_refs["port"] = int(port)
            except (TypeError, ValueError):
                pass
        logger.debug("_capture_refs(): using existing refs (port=%s)", _core_refs.get("port"))
        return _core_refs
    try:
        device_config = current_app.config.get("DEVICE_CONFIG")
        refresh_task = current_app.config.get("REFRESH_TASK")
        port = 80
        if request:
            port = request.environ.get("SERVER_PORT", "80")
        try:
            port = int(port)
        except (TypeError, ValueError):
            port = 80
        _core_refs = {
            "device_config": device_config,
            "refresh_task": refresh_task,
            "app": current_app._get_current_object(),
            "port": port,
        }
        logger.debug("_capture_refs(): first request -> stored refs (port=%s), starting button manager", port)
        button_manager.start_if_needed(_core_refs)
        return _core_refs
    except RuntimeError:
        logger.debug("_capture_refs(): no Flask app context (RuntimeError)")
        return None


@hardwarebuttons_bp.before_request
def _ensure_refs():
    try:
        _capture_refs()
    except Exception:
        pass


@hardwarebuttons_bp.route("/hardwarebuttons-api/save", methods=["POST"])
def save():
    """Save timings and buttons config. Body: { timings: {}, buttons: [] }."""
    logger.debug("POST /hardwarebuttons-api/save called")
    refs = _capture_refs()
    if not refs:
        logger.debug("save: no refs -> 500")
        return jsonify({"success": False, "error": "Not in request context"}), 500
    device_config = refs["device_config"]
    data = request.get_json() or {}
    timings = data.get("timings") or {}
    buttons = data.get("buttons") or []

    # Merge timings with defaults
    timings = {
        "short_press_ms": int(timings.get("short_press_ms", DEFAULT_TIMINGS["short_press_ms"])),
        "double_click_interval_ms": int(timings.get("double_click_interval_ms", DEFAULT_TIMINGS["double_click_interval_ms"])),
        "long_press_ms": int(timings.get("long_press_ms", DEFAULT_TIMINGS["long_press_ms"])),
    }
    timings["short_press_ms"] = max(50, min(2000, timings["short_press_ms"]))
    timings["double_click_interval_ms"] = max(100, min(2000, timings["double_click_interval_ms"]))
    timings["long_press_ms"] = max(200, min(5000, timings["long_press_ms"]))

    # Validate buttons
    allowed_pins = set(range(2, 28))  # GPIO 2-27 typical for Pi
    validated_buttons = []
    available = {a["id"] for a in get_available_actions(device_config)}
    for i, btn in enumerate(buttons):
        if not isinstance(btn, dict):
            continue
        pin = btn.get("gpio_pin")
        try:
            pin = int(pin)
        except (TypeError, ValueError):
            continue
        if pin not in allowed_pins:
            continue
        bid = btn.get("id") or f"btn_{i}"
        short_a = (btn.get("short_action") or "").strip() or None
        double_a = (btn.get("double_action") or "").strip() or None
        long_a = (btn.get("long_action") or "").strip() or None
        for aid in (short_a, double_a, long_a):
            if aid and aid != "external_script" and aid not in available:
                logger.warning("Unknown action_id %s for button %s", aid, bid)
        script_short = (btn.get("script_path_short") or "").strip() or None
        script_double = (btn.get("script_path_double") or "").strip() or None
        script_long = (btn.get("script_path_long") or "").strip() or None
        validated_buttons.append({
            "id": bid,
            "gpio_pin": pin,
            "short_action": short_a,
            "double_action": double_a,
            "long_action": long_a,
            "script_path_short": script_short,
            "script_path_double": script_double,
            "script_path_long": script_long,
        })

    payload = {"timings": timings, "buttons": validated_buttons}
    device_config.update_value("hardwarebuttons", payload, write=True)
    logger.debug("save: wrote %d buttons, timings %s; requesting button manager reload", len(validated_buttons), timings)
    button_manager.request_reload()
    return jsonify({"success": True})


@hardwarebuttons_bp.route("/hardwarebuttons-api/available-actions", methods=["GET"])
def available_actions():
    """Return built-in + plugin-registered actions for dropdowns."""
    logger.debug("GET /hardwarebuttons-api/available-actions called")
    refs = _capture_refs()
    if not refs:
        return jsonify({"success": False, "actions": []}), 500
    actions_list = get_available_actions(refs["device_config"])
    logger.debug("available-actions: returning %d actions", len(actions_list))
    return jsonify({"success": True, "actions": actions_list})


@hardwarebuttons_bp.route("/hardwarebuttons-api/execute", methods=["POST"])
def execute():
    """Internal: execute an action (for testing or from worker). Body: { action_id, context?: {} }."""
    logger.debug("POST /hardwarebuttons-api/execute called")
    refs = _capture_refs()
    if not refs:
        return jsonify({"success": False, "error": "Not in request context"}), 500
    data = request.get_json() or {}
    action_id = (data.get("action_id") or "").strip()
    if not action_id:
        return jsonify({"success": False, "error": "action_id required"}), 400
    context = data.get("context") or {}
    logger.debug("execute: action_id=%s, context keys=%s", action_id, list(context.keys()))
    try:
        actions.execute_action(refs, action_id, context)
        logger.debug("execute: action %s completed", action_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.exception("execute_action failed")
        return jsonify({"success": False, "error": str(e)}), 500


@hardwarebuttons_bp.route("/hardwarebuttons-api/restart-service", methods=["POST"])
def restart_service():
    """Restart InkyPi service (used by system_restart_inkypi action)."""
    logger.debug("POST /hardwarebuttons-api/restart-service called")
    try:
        service_name = os.environ.get("APPNAME", "inkypi")
        logger.debug("restart-service: running systemctl restart %s.service", service_name)
        subprocess.run(
            ["sudo", "systemctl", "restart", f"{service_name}.service"],
            timeout=10,
            check=False,
        )
        return jsonify({"success": True})
    except Exception as e:
        logger.warning("Restart service failed: %s", e)
        return jsonify({"success": False, "error": str(e)}), 500


def get_core_refs():
    """Return stored core refs for use by button manager (may be None)."""
    return _core_refs
