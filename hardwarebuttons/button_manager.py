"""GPIO button manager: sets up gpiozero buttons and runs short/double/long press state machine."""

import logging
import threading
import time

from . import actions

logger = logging.getLogger(__name__)

_refs = None
_thread = None
_buttons = []  # list of (Button, bindings_dict) for cleanup
_lock = threading.Lock()
_reload_event = threading.Event()
_active_generation = 0
_timers = set()

# Optional gpiozero; missing on non-Pi / dev
try:
    from gpiozero import Button
    GPIOZERO_AVAILABLE = True
except ImportError:
    Button = None
    GPIOZERO_AVAILABLE = False


def start_if_needed(refs):
    """Start the button manager thread if we have refs and GPIO; store refs for worker."""
    global _refs, _thread
    logger.debug("start_if_needed called (thread_alive=%s)", _thread.is_alive() if _thread and _thread.is_alive() else False)
    with _lock:
        _refs = refs
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_run, daemon=True)
            _thread.start()
            logger.info("Hardware buttons manager thread started")
            logger.debug("start_if_needed: started new manager thread")
        else:
            logger.debug("start_if_needed: reusing existing thread")


def request_reload():
    """Ask the manager to reload config and re-setup buttons on next loop."""
    logger.debug("request_reload called -> set reload flag")
    _reload_event.set()


def _run():
    """Background loop: setup buttons from config, then wait for reload or exit."""
    logger.debug("_run: button manager loop started")
    while True:
        with _lock:
            refs = _refs
        if not refs:
            logger.debug("_run: no refs yet -> sleep 2s")
            time.sleep(2)
            continue
        device_config = refs.get("device_config")
        if not device_config:
            logger.debug("_run: no device_config -> sleep 2s")
            time.sleep(2)
            continue
        cfg = device_config.get_config("hardwarebuttons", default={}) or {}
        timings = cfg.get("timings") or {}
        short_ms = int(timings.get("short_press_ms", 500))
        double_ms = int(timings.get("double_click_interval_ms", 500))
        long_ms = int(timings.get("long_press_ms", 1000))
        buttons_cfg = cfg.get("buttons") or []
        logger.debug("_run: loaded config: %d buttons, timings short=%s double=%s long=%s ms", len(buttons_cfg), short_ms, double_ms, long_ms)

        _close_buttons()
        global _active_generation
        with _lock:
            _active_generation += 1
        _reload_event.clear()

        if not GPIOZERO_AVAILABLE or not Button:
            logger.debug("gpiozero not available, hardware buttons disabled")
            while not _reload_event.wait(timeout=1):
                pass
            continue

        for bindings in buttons_cfg:
            pin = bindings.get("gpio_pin")
            if pin is None:
                continue
            try:
                btn = Button(pin, hold_time=long_ms / 1000.0)
                _setup_button(btn, bindings, refs, short_ms, double_ms, _active_generation)
                _buttons.append((btn, bindings))
                logger.debug("_run: setup button GPIO %s (id=%s)", pin, bindings.get("id"))
            except Exception as e:
                logger.warning("Could not setup button on GPIO %s: %s", pin, e)

        logger.debug("_run: %d buttons active, waiting for reload or trigger", len(_buttons))
        while not _reload_event.wait(timeout=0.5):
            pass
        logger.info("Hardware buttons reload requested")


def _close_buttons():
    global _buttons
    with _lock:
        timers = list(_timers)
        _timers.clear()
    for timer in timers:
        try:
            timer.cancel()
        except Exception:
            pass
    if _buttons:
        logger.debug("_close_buttons: closing %d button(s)", len(_buttons))
    for btn, _ in _buttons:
        try:
            btn.close()
        except Exception:
            pass
    _buttons = []


def _register_timer(timer):
    with _lock:
        _timers.add(timer)


def _discard_timer(timer):
    with _lock:
        _timers.discard(timer)


def _is_generation_active(generation):
    with _lock:
        return generation == _active_generation and not _reload_event.is_set()


def _setup_button(btn, bindings, refs, short_ms, double_ms, generation):
    """Attach callbacks for short, double, long to a gpiozero Button."""
    pending_short_timer = [None]  # use list so closure can mutate
    long_fired = [False]
    press_started_monotonic = [None]

    def run_action(action_id, script_path=None, url=None):
        if not _is_generation_active(generation):
            logger.debug("run_action: stale callback ignored for GPIO %s", bindings.get("gpio_pin"))
            return
        logger.debug("run_action: action_id=%s (from GPIO %s)", action_id, bindings.get("gpio_pin"))
        ctx = {}
        if script_path:
            ctx["script_path"] = script_path
        if url:
            ctx["url"] = url
        try:
            actions.execute_action(refs, action_id, ctx if ctx else None)
        except Exception as e:
            logger.warning("Button action %s failed: %s", action_id, e)

    def on_pressed():
        press_started_monotonic[0] = time.monotonic()

    def on_held():
        logger.debug("on_held: long press detected on GPIO %s -> firing long_action", bindings.get("gpio_pin"))
        long_fired[0] = True
        if pending_short_timer[0]:
            pending_short_timer[0].cancel()
            _discard_timer(pending_short_timer[0])
            pending_short_timer[0] = None
        action = bindings.get("long_action")
        if action:
            run_action(action, bindings.get("script_path_long"), bindings.get("url_long"))

    def on_released():
        if long_fired[0]:
            long_fired[0] = False
            press_started_monotonic[0] = None
            return
        if press_started_monotonic[0] is None:
            press_ms = 0
        else:
            press_ms = int((time.monotonic() - press_started_monotonic[0]) * 1000)
        press_started_monotonic[0] = None
        if pending_short_timer[0]:
            if press_ms > short_ms:
                logger.debug(
                    "on_released: second press too long (%sms > %sms) on GPIO %s -> keep pending short",
                    press_ms,
                    short_ms,
                    bindings.get("gpio_pin"),
                )
                return
            pending_short_timer[0].cancel()
            _discard_timer(pending_short_timer[0])
            pending_short_timer[0] = None
            # Second release within double window -> double click
            logger.debug("on_released: second press in window on GPIO %s -> firing double_action", bindings.get("gpio_pin"))
            action = bindings.get("double_action")
            if action:
                run_action(action, bindings.get("script_path_double"), bindings.get("url_double"))
            return
        if press_ms > short_ms:
            logger.debug(
                "on_released: press longer than short threshold (%sms > %sms) on GPIO %s -> no short/double action",
                press_ms,
                short_ms,
                bindings.get("gpio_pin"),
            )
            return
        # First release: start double-click window
        def fire_short():
            if pending_short_timer[0]:
                _discard_timer(pending_short_timer[0])
            pending_short_timer[0] = None
            if not _is_generation_active(generation):
                logger.debug("fire_short: stale timer ignored for GPIO %s", bindings.get("gpio_pin"))
                return
            logger.debug("fire_short: single short press on GPIO %s -> firing short_action", bindings.get("gpio_pin"))
            action = bindings.get("short_action")
            if action:
                run_action(action, bindings.get("script_path_short"), bindings.get("url_short"))

        t = threading.Timer(double_ms / 1000.0, fire_short)
        pending_short_timer[0] = t
        _register_timer(t)
        t.start()

    btn.when_pressed = on_pressed
    btn.when_held = on_held
    btn.when_released = on_released
