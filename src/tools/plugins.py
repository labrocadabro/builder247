"""Plugin system for tool extensions."""

import inspect
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Type


@dataclass
class PluginInfo:
    """Plugin metadata."""

    name: str
    version: str
    description: str
    author: str
    tools: List[str]
    dependencies: List[str] = field(default_factory=list)
    module_path: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "tools": self.tools,
            "dependencies": self.dependencies,
            "module_path": self.module_path,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "PluginInfo":
        """Create from dictionary.

        Args:
            data: Dictionary containing plugin info

        Returns:
            PluginInfo instance
        """
        return cls(
            name=data["name"],
            version=data["version"],
            description=data["description"],
            author=data["author"],
            tools=data["tools"],
            dependencies=data.get("dependencies", []),
            module_path=data.get("module_path"),
        )


class PluginRegistry:
    """Registry for plugins."""

    def __init__(self, plugin_dir: Optional[str] = None):
        """Initialize plugin registry.

        Args:
            plugin_dir: Directory containing plugins
        """
        self.plugin_dir = Path(plugin_dir) if plugin_dir else None
        self.plugins: Dict[str, PluginInfo] = {}

    def register_plugin(self, plugin: PluginInfo) -> None:
        """Register a plugin.

        Args:
            plugin: Plugin to register

        Raises:
            ValueError: If plugin already registered
        """
        if plugin.name in self.plugins:
            raise ValueError(f"Plugin {plugin.name} already registered")
        self.plugins[plugin.name] = plugin

    def unregister_plugin(self, name: str) -> None:
        """Unregister a plugin.

        Args:
            name: Name of plugin to unregister

        Raises:
            KeyError: If plugin not found
        """
        if name not in self.plugins:
            raise KeyError(f"Plugin {name} not found")
        del self.plugins[name]

    def get_plugin(self, name: str) -> PluginInfo:
        """Get plugin by name.

        Args:
            name: Name of plugin

        Returns:
            Plugin info

        Raises:
            KeyError: If plugin not found
        """
        if name not in self.plugins:
            raise KeyError(f"Plugin {name} not found")
        return self.plugins[name]

    def discover_plugins(self) -> List[PluginInfo]:
        """Discover plugins in plugin directory.

        Returns:
            List of discovered plugins

        Raises:
            FileNotFoundError: If plugin directory not found
            ValueError: If plugin info is invalid
        """
        if not self.plugin_dir:
            return []

        if not self.plugin_dir.exists():
            raise FileNotFoundError(f"Plugin directory not found: {self.plugin_dir}")

        plugins = []
        for file in self.plugin_dir.glob("*.json"):
            try:
                with open(file) as f:
                    data = json.load(f)
                data["module_path"] = str(file.with_suffix(".py"))
                plugin = PluginInfo.from_dict(data)
                plugins.append(plugin)
            except (json.JSONDecodeError, KeyError) as e:
                raise ValueError(f"Invalid plugin info in {file}: {e}")

        return plugins


class PluginLoader:
    """Loader for plugin modules."""

    def load_plugin(self, module_path: str) -> Type:
        """Load plugin module.

        Args:
            module_path: Path to plugin module

        Returns:
            Plugin class

        Raises:
            ImportError: If module cannot be imported
            ValueError: If module does not contain a plugin class
        """
        import importlib.util

        if not os.path.exists(module_path):
            raise ImportError(f"Plugin module not found: {module_path}")

        try:
            spec = importlib.util.spec_from_file_location("plugin", module_path)
            if not spec or not spec.loader:
                raise ImportError(f"Could not load plugin module: {module_path}")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find plugin class in module
            for attr in dir(module):
                obj = getattr(module, attr)
                if isinstance(obj, type) and hasattr(obj, "get_tools"):
                    return obj

            raise ValueError(f"No plugin class found in {module_path}")
        except Exception as e:
            raise ImportError(f"Failed to load plugin module: {e}")


class PluginTemplate:
    """Base class for plugin implementations."""

    PLUGIN_INFO = {
        "name": "",
        "version": "0.0.0",
        "description": "",
        "author": "",
    }

    @classmethod
    def register(cls, registry: PluginRegistry) -> None:
        """Register plugin with registry.

        Args:
            registry: Plugin registry instance
        """
        # Get all public methods as tools
        for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if not name.startswith("_"):
                tool_name = f"{cls.PLUGIN_INFO['name']}.{name}"
                registry.register_tool(tool_name, method)
