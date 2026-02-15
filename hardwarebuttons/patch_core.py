"""Core patching functionality for hardwarebuttons plugin (same patch as pluginmanager)."""

import os
import re
import logging

logger = logging.getLogger(__name__)


def _project_dir():
    """Project root (parent of src/)."""
    try:
        from config import Config
        return os.path.dirname(Config.BASE_DIR)
    except ImportError:
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def check_core_patched():
    """Check if core files have been patched with blueprint registration support.

    Returns:
        tuple: (is_patched: bool, missing_parts: list)
    """
    project_dir = _project_dir()
    missing = []

    registry_path = os.path.join(project_dir, "src", "plugins", "plugin_registry.py")
    if os.path.exists(registry_path):
        with open(registry_path, 'r') as f:
            content = f.read()
            if 'def register_plugin_blueprints(app):' not in content:
                missing.append("plugin_registry.py: missing register_plugin_blueprints() function")
    else:
        missing.append("plugin_registry.py: file not found")

    inkypi_path = os.path.join(project_dir, "src", "inkypi.py")
    if os.path.exists(inkypi_path):
        with open(inkypi_path, 'r') as f:
            content = f.read()
            if 'register_plugin_blueprints' not in content:
                missing.append("inkypi.py: missing register_plugin_blueprints import/call")
    else:
        missing.append("inkypi.py: file not found")

    return len(missing) == 0, missing


def patch_core_files():
    """Patch core files to add blueprint registration support.

    Returns:
        tuple: (success: bool, error_message: str)
    """
    project_dir = _project_dir()

    try:
        registry_path = os.path.join(project_dir, "src", "plugins", "plugin_registry.py")
        if not os.path.exists(registry_path):
            return False, f"File not found: {registry_path}"

        with open(registry_path, 'r') as f:
            registry_content = f.read()

        if 'def register_plugin_blueprints(app):' in registry_content:
            logger.info("plugin_registry.py already patched")
        else:
            patch_function = '''

def register_plugin_blueprints(app):
    """Register blueprints from plugins that expose them via get_blueprint() method.

    This is a generic mechanism that allows any plugin to register Flask blueprints
    by implementing a get_blueprint() class method that returns a Blueprint instance.

    Args:
        app: Flask application instance to register blueprints with
    """
    for plugin_id, plugin_instance in PLUGIN_CLASSES.items():
        try:
            if hasattr(plugin_instance, 'get_blueprint'):
                bp = plugin_instance.get_blueprint()
                if bp:
                    app.register_blueprint(bp)
                    logger.info(f"Registered blueprint for plugin '{plugin_id}'")
        except Exception as e:
            logger.warning(f"Failed to register blueprint for plugin '{plugin_id}': {e}")
'''
            registry_content += patch_function
            with open(registry_path, 'w') as f:
                f.write(registry_content)
            logger.info("Patched plugin_registry.py")

        inkypi_path = os.path.join(project_dir, "src", "inkypi.py")
        if not os.path.exists(inkypi_path):
            return False, f"File not found: {inkypi_path}"

        with open(inkypi_path, 'r') as f:
            inkypi_content = f.read()

        if 'register_plugin_blueprints(app)' in inkypi_content:
            logger.info("inkypi.py already patched")
        else:
            if 'register_plugin_blueprints' not in inkypi_content:
                import_line = 'from plugins.plugin_registry import load_plugins, get_plugin_instance, register_plugin_blueprints'
                pattern = r'from plugins\.plugin_registry import [^\n]+'
                if re.search(pattern, inkypi_content):
                    inkypi_content = re.sub(pattern, import_line, inkypi_content)
                else:
                    lines = inkypi_content.split('\n')
                    insert_idx = None
                    for i, line in enumerate(lines):
                        if 'from plugins.plugin_registry import' in line:
                            insert_idx = i
                            break
                        elif i > 30 and 'from waitress import serve' in line:
                            insert_idx = i
                            break
                    if insert_idx is not None:
                        lines.insert(insert_idx, import_line)
                        inkypi_content = '\n'.join(lines)

            blueprint_section = '# Register Blueprints'
            if blueprint_section in inkypi_content:
                lines = inkypi_content.split('\n')
                insert_idx = None
                in_blueprint_section = False
                for i, line in enumerate(lines):
                    if '# Register Blueprints' in line:
                        in_blueprint_section = True
                    elif in_blueprint_section and (line.strip().startswith('#') or 'register_heif_opener' in line or 'if __name__' in line):
                        insert_idx = i
                        break
                if insert_idx:
                    call_line = '\n# Register blueprints from plugins (generic mechanism - any plugin can expose blueprints)\nregister_plugin_blueprints(app)'
                    lines.insert(insert_idx, call_line)
                    inkypi_content = '\n'.join(lines)
            with open(inkypi_path, 'w') as f:
                f.write(inkypi_content)
            logger.info("Patched inkypi.py")

        return True, None
    except Exception as e:
        logger.exception("Failed to patch core files")
        return False, str(e)
