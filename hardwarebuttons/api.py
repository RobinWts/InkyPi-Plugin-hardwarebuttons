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


def _parse_timing(value, default_value, min_value, max_value):
    """Parse timing value and clamp to safe bounds."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default_value
    return max(min_value, min(max_value, parsed))


def _normalize_action(action_id, available_action_ids):
    """Validate and normalize an action id from UI payload."""
    action_id = (action_id or "").strip()
    if not action_id:
        return None
    if action_id == "external_script":
        return action_id
    if action_id in available_action_ids:
        return action_id
    raise ValueError(f"Unknown action_id: {action_id}")


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

    timings = {
        "short_press_ms": _parse_timing(
            timings.get("short_press_ms"),
            DEFAULT_TIMINGS["short_press_ms"],
            50,
            2000,
        ),
        "double_click_interval_ms": _parse_timing(
            timings.get("double_click_interval_ms"),
            DEFAULT_TIMINGS["double_click_interval_ms"],
            100,
            2000,
        ),
        "long_press_ms": _parse_timing(
            timings.get("long_press_ms"),
            DEFAULT_TIMINGS["long_press_ms"],
            200,
            5000,
        ),
    }

    # Validate buttons
    allowed_pins = set(range(2, 28))  # GPIO 2-27 typical for Pi
    validated_buttons = []
    validation_errors = []
    used_pins = set()
    available = {a["id"] for a in get_available_actions(device_config)}
    for i, btn in enumerate(buttons):
        if not isinstance(btn, dict):
            validation_errors.append(f"buttons[{i}] must be an object")
            continue
        pin = btn.get("gpio_pin")
        try:
            pin = int(pin)
        except (TypeError, ValueError):
            validation_errors.append(f"buttons[{i}].gpio_pin must be an integer")
            continue
        if pin not in allowed_pins:
            validation_errors.append(f"buttons[{i}].gpio_pin must be between 2 and 27")
            continue
        if pin in used_pins:
            validation_errors.append(f"Duplicate GPIO pin configured: {pin}")
            continue
        used_pins.add(pin)
        bid = btn.get("id") or f"btn_{i}"
        try:
            short_a = _normalize_action(btn.get("short_action"), available)
            double_a = _normalize_action(btn.get("double_action"), available)
            long_a = _normalize_action(btn.get("long_action"), available)
        except ValueError as e:
            validation_errors.append(f"buttons[{i}]: {e}")
            continue
        script_short = ((btn.get("script_path_short") or "").strip() or None) if short_a == "external_script" else None
        script_double = ((btn.get("script_path_double") or "").strip() or None) if double_a == "external_script" else None
        script_long = ((btn.get("script_path_long") or "").strip() or None) if long_a == "external_script" else None
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

    if validation_errors:
        logger.warning("save: validation failed: %s", validation_errors)
        return jsonify({"success": False, "error": "Validation failed", "details": validation_errors}), 400

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
