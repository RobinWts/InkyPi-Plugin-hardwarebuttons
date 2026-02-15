"""Hardware Buttons plugin - configures hardware button bindings (UI/settings only)."""

from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
import logging
import os
import subprocess

logger = logging.getLogger(__name__)

DEFAULT_TIMINGS = {
    "short_press_ms": 500,
    "double_click_interval_ms": 500,
    "long_press_ms": 1000,
}


class HardwareButtons(BasePlugin):
    """Plugin for configuring hardware button actions (UI/settings only)."""

    @classmethod
    def get_blueprint(cls):
        """Return the Flask blueprint for this plugin's API routes."""
        logger.debug("get_blueprint() called -> returning hardwarebuttons_bp")
        from . import api
        return api.hardwarebuttons_bp

    def generate_settings_template(self):
        """Add patch-check, autopatch, timings, buttons, and available_actions."""
        logger.debug("generate_settings_template() called (building settings page data)")
        template_params = super().generate_settings_template()
        try:
            from flask import current_app

            # Check if core files need patching first
            core_needs_patch = False
            core_patch_missing = []
            try:
                from .patch_core import check_core_patched
                is_patched, missing = check_core_patched()
                core_needs_patch = not is_patched
                core_patch_missing = missing
                logger.debug("patch check: is_patched=%s, missing=%s", is_patched, missing)
            except Exception as e:
                logger.warning(f"Could not check patch status: {e}")

            template_params['core_needs_patch'] = core_needs_patch
            template_params['core_patch_missing'] = core_patch_missing

            if core_needs_patch:
                logger.debug("core needs patch -> skipping config load, starting autopatch if script present")
                patch_script = os.path.join(os.path.dirname(__file__), "patch-core.sh")
                if os.path.isfile(patch_script):
                    try:
                        subprocess.Popen(
                            ["bash", patch_script],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        template_params['auto_patch_started'] = True
                    except Exception as e:
                        logger.warning(f"Could not start auto core patch: {e}")
                        template_params['auto_patch_started'] = False
                else:
                    logger.warning("patch-core.sh not found for hardwarebuttons")
                    template_params['auto_patch_started'] = False
                template_params['timings'] = DEFAULT_TIMINGS
                template_params['buttons'] = []
                template_params['available_actions'] = []
            else:
                template_params['auto_patch_started'] = False
                device_config = current_app.config.get("DEVICE_CONFIG")
                if device_config:
                    hw_cfg = device_config.get_config("hardwarebuttons", default={}) or {}
                    template_params['timings'] = {**DEFAULT_TIMINGS, **(hw_cfg.get("timings") or {})}
                    template_params['buttons'] = hw_cfg.get("buttons") or []
                    from .discovery import get_available_actions
                    template_params['available_actions'] = get_available_actions(device_config)
                    logger.debug("loaded config: %d buttons, %d available_actions", len(template_params['buttons']), len(template_params['available_actions']))
                else:
                    logger.debug("no DEVICE_CONFIG in app -> using defaults, empty buttons/actions")
                    template_params['timings'] = DEFAULT_TIMINGS
                    template_params['buttons'] = []
                    template_params['available_actions'] = []
        except (RuntimeError, ImportError):
            logger.debug("generate_settings_template: outside request context or import error -> using defaults")
            template_params['core_needs_patch'] = template_params.get('core_needs_patch', False)
            template_params['core_patch_missing'] = template_params.get('core_patch_missing', [])
            template_params['auto_patch_started'] = False
            template_params['timings'] = DEFAULT_TIMINGS
            template_params['buttons'] = []
            template_params['available_actions'] = []
        return template_params

    def generate_image(self, settings, device_config):
        """Return a placeholder image - this plugin is UI-only."""
        logger.debug("generate_image() called (UI-only plugin -> placeholder)")
        width, height = device_config.get_resolution()
        img = Image.new('RGB', (width, height), color='white')
        return img
