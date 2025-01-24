"""Unit tests for plugin system."""

import json
import os
import tempfile
import pytest
from pathlib import Path

from src.tools.plugins import (
    PluginInfo,
    PluginRegistry,
    PluginLoader,
    PluginTemplate,
)
from src.tools.interfaces import ToolResponse, ToolResponseStatus


@pytest.fixture
def plugin_dir():
    """Create a temporary plugin directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = os.path.join(tmpdir, "plugins")
        os.makedirs(plugin_dir)
        yield plugin_dir


@pytest.fixture
def plugin_registry(plugin_dir):
    """Create a plugin registry with temporary directory."""
    return PluginRegistry(plugin_dir)


@pytest.fixture
def sample_plugin_info():
    """Create sample plugin info."""
    return PluginInfo(
        name="test_plugin",
        version="1.0.0",
        description="Test plugin",
        author="Test Author",
        tools=["test_tool"],
        dependencies=["requests>=2.0.0"],
    )


def create_plugin_file(plugin_dir, name, content):
    """Helper to create a plugin file."""
    plugin_path = os.path.join(plugin_dir, name)
    with open(plugin_path, "w") as f:
        f.write(content)
    return plugin_path


def test_plugin_info_init(sample_plugin_info):
    """Test PluginInfo initialization."""
    assert sample_plugin_info.name == "test_plugin"
    assert sample_plugin_info.version == "1.0.0"
    assert sample_plugin_info.description == "Test plugin"
    assert sample_plugin_info.author == "Test Author"
    assert sample_plugin_info.tools == ["test_tool"]
    assert sample_plugin_info.dependencies == ["requests>=2.0.0"]


def test_plugin_info_to_dict(sample_plugin_info):
    """Test converting PluginInfo to dictionary."""
    info_dict = sample_plugin_info.to_dict()
    assert isinstance(info_dict, dict)
    assert info_dict["name"] == "test_plugin"
    assert info_dict["version"] == "1.0.0"
    assert info_dict["tools"] == ["test_tool"]


def test_plugin_info_from_dict():
    """Test plugin info creation with comprehensive validation."""
    # Test complete plugin info
    complete_info = {
        "name": "test_plugin",
        "version": "1.0.0",
        "description": "Test plugin",
        "author": "Test Author",
        "dependencies": ["dep1", "dep2"],
        "module_path": "/path/to/plugin.py",
    }
    plugin = PluginInfo.from_dict(complete_info)
    assert plugin.name == complete_info["name"]
    assert plugin.version == complete_info["version"]
    assert plugin.description == complete_info["description"]
    assert plugin.author == complete_info["author"]
    assert plugin.dependencies == complete_info["dependencies"]
    assert plugin.module_path == Path(complete_info["module_path"])

    # Test minimal required info
    minimal_info = {
        "name": "minimal_plugin",
        "version": "1.0.0",
    }
    plugin = PluginInfo.from_dict(minimal_info)
    assert plugin.name == minimal_info["name"]
    assert plugin.version == minimal_info["version"]
    assert plugin.description == ""
    assert plugin.author == ""
    assert plugin.dependencies == []
    assert plugin.module_path is None

    # Test invalid info
    invalid_cases = [
        {},  # Empty dict
        {"name": "test"},  # Missing version
        {"version": "1.0.0"},  # Missing name
        {"name": "", "version": "1.0.0"},  # Empty name
        {"name": "test", "version": ""},  # Empty version
        {
            "name": "test",
            "version": "1.0.0",
            "dependencies": "not_a_list",
        },  # Invalid dependencies
    ]

    for invalid_info in invalid_cases:
        with pytest.raises(ValueError):
            PluginInfo.from_dict(invalid_info)


def test_plugin_registry_discover_plugins(plugin_registry, plugin_dir):
    """Test discovering plugins in directory."""
    # Create plugin files
    create_plugin_file(
        plugin_dir,
        "plugin1.json",
        json.dumps(
            {
                "name": "plugin1",
                "version": "1.0.0",
                "description": "Plugin 1",
                "author": "Test Author",
                "tools": ["tool1"],
                "dependencies": [],
            }
        ),
    )
    create_plugin_file(
        plugin_dir,
        "plugin2.json",
        json.dumps(
            {
                "name": "plugin2",
                "version": "1.0.0",
                "description": "Plugin 2",
                "author": "Test Author",
                "tools": ["tool2"],
                "dependencies": [],
            }
        ),
    )

    plugins = plugin_registry.discover_plugins()
    assert len(plugins) == 2
    assert any(p.name == "plugin1" for p in plugins)
    assert any(p.name == "plugin2" for p in plugins)


def test_plugin_registry_discover_invalid_plugin(plugin_registry, plugin_dir):
    """Test discovering invalid plugin file."""
    create_plugin_file(plugin_dir, "invalid.json", "invalid json")

    with pytest.raises(json.JSONDecodeError):
        plugin_registry.discover_plugins()


def test_plugin_registry_register_plugin(plugin_registry, sample_plugin_info):
    """Test registering a plugin."""
    plugin_registry.register_plugin(sample_plugin_info)
    assert sample_plugin_info.name in plugin_registry.plugins


def test_plugin_registry_unregister_plugin(plugin_registry, sample_plugin_info):
    """Test unregistering a plugin."""
    plugin_registry.register_plugin(sample_plugin_info)
    plugin_registry.unregister_plugin(sample_plugin_info.name)
    assert sample_plugin_info.name not in plugin_registry.plugins


def test_plugin_registry_get_plugin(plugin_registry, sample_plugin_info):
    """Test getting a registered plugin."""
    plugin_registry.register_plugin(sample_plugin_info)
    plugin = plugin_registry.get_plugin(sample_plugin_info.name)
    assert plugin.name == sample_plugin_info.name


def test_plugin_registry_get_nonexistent_plugin(plugin_registry):
    """Test getting a non-existent plugin."""
    with pytest.raises(KeyError):
        plugin_registry.get_plugin("nonexistent")


def test_plugin_registry_register(plugin_registry):
    """Test plugin registration with duplicate and validation checks."""
    plugin1 = PluginInfo(
        name="plugin1",
        version="1.0.0",
        description="Test plugin 1",
        module_path="/path/to/plugin1.py",
    )

    plugin2 = PluginInfo(
        name="plugin2",
        version="1.0.0",
        description="Test plugin 2",
        module_path="/path/to/plugin2.py",
    )

    # Test successful registration
    plugin_registry.register_plugin(plugin1)
    assert plugin1.name in plugin_registry.get_plugins()

    # Test duplicate registration
    with pytest.raises(ValueError, match="Plugin already registered"):
        plugin_registry.register_plugin(plugin1)

    # Test registering multiple plugins
    plugin_registry.register_plugin(plugin2)
    plugins = plugin_registry.get_plugins()
    assert len(plugins) == 2
    assert plugin1.name in plugins
    assert plugin2.name in plugins

    # Test registering invalid plugin
    with pytest.raises(TypeError):
        plugin_registry.register_plugin(None)

    with pytest.raises(TypeError):
        plugin_registry.register_plugin("not_a_plugin_info")


def test_plugin_loader_load_plugin(plugin_dir):
    """Test loading a plugin module."""
    # Create a simple plugin module
    plugin_code = """
from src.tools.plugins import PluginTemplate

class TestPlugin(PluginTemplate):
    def get_tools(self):
        return {"test_tool": self.test_tool}

    def test_tool(self, **kwargs):
        return "test success"
"""
    create_plugin_file(plugin_dir, "test_plugin.py", plugin_code)

    loader = PluginLoader()
    plugin_module = loader.load_plugin(os.path.join(plugin_dir, "test_plugin.py"))
    assert hasattr(plugin_module, "TestPlugin")


def test_plugin_loader_load_invalid_plugin(plugin_dir):
    """Test loading invalid plugin module."""
    create_plugin_file(plugin_dir, "invalid_plugin.py", "invalid python code")

    loader = PluginLoader()
    with pytest.raises(SyntaxError):
        loader.load_plugin(os.path.join(plugin_dir, "invalid_plugin.py"))


def test_plugin_template_interface():
    """Test plugin template interface."""

    class TestPlugin(PluginTemplate):
        def get_tools(self):
            return {"test_tool": self.test_tool}

        def test_tool(self, **kwargs):
            return ToolResponse(status=ToolResponseStatus.SUCCESS, data="test success")

    plugin = TestPlugin()
    tools = plugin.get_tools()
    assert "test_tool" in tools

    result = tools["test_tool"]()
    assert isinstance(result, ToolResponse)
    assert result.status == ToolResponseStatus.SUCCESS
    assert result.data == "test success"


def test_plugin_loader_basic(plugin_dir):
    """Test basic plugin loading with interface validation."""
    # Create a valid plugin
    plugin_code = """
from src.tools.plugins import PluginTemplate

class TestPlugin(PluginTemplate):
    def get_tools(self):
        return {
            "test_tool": self.test_tool,
            "another_tool": self.another_tool
        }

    def test_tool(self, **kwargs):
        return "test success"

    def another_tool(self, param1: str, param2: int = 0):
        return f"param1={param1}, param2={param2}"
"""

    create_plugin_file(plugin_dir, "test_plugin.py", plugin_code)

    # Load and validate plugin
    loader = PluginLoader()
    plugin_class = loader.load_plugin(os.path.join(plugin_dir, "test_plugin.py"))

    # Verify plugin interface
    assert issubclass(plugin_class, PluginTemplate)

    # Instantiate and test plugin
    plugin = plugin_class()
    tools = plugin.get_tools()

    assert isinstance(tools, dict)
    assert len(tools) == 2
    assert "test_tool" in tools
    assert "another_tool" in tools
    assert callable(tools["test_tool"])
    assert callable(tools["another_tool"])

    # Test tool execution
    assert tools["test_tool"]() == "test success"
    assert tools["another_tool"]("test", 42) == "param1=test, param2=42"
