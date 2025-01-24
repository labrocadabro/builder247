"""
Configuration management for tools.
"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class ToolConfig:
    """Configuration for tool behavior."""

    allowed_paths: List[Path]
    allowed_env_vars: List[str]
    restricted_commands: List[str]
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    command_timeout: int = 30  # seconds
    create_dirs: bool = True
    default_encoding: str = "utf-8"
    log_level: str = "INFO"
    retry_attempts: int = 3
    retry_delay: float = 1.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolConfig":
        """Create config from dictionary.

        Args:
            data: Dictionary containing configuration values

        Returns:
            ToolConfig instance
        """
        # Convert path strings to Path objects
        if "allowed_paths" in data:
            data["allowed_paths"] = [Path(p) for p in data["allowed_paths"]]
        return cls(**data)

    @classmethod
    def from_json(cls, path: Path) -> "ToolConfig":
        """Load config from JSON file.

        Args:
            path: Path to JSON config file

        Returns:
            ToolConfig instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            json.JSONDecodeError: If config file is invalid JSON
        """
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def default(cls) -> "ToolConfig":
        """Create default configuration.

        Returns:
            ToolConfig with default values
        """
        return cls(
            allowed_paths=[Path.cwd(), Path("/tmp")],
            allowed_env_vars=["PATH", "HOME", "USER"],
            restricted_commands=["rm -rf", "sudo", ">", "dd"],
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary.

        Returns:
            Dictionary representation of config
        """
        data = asdict(self)
        # Convert Path objects to strings
        data["allowed_paths"] = [str(p) for p in self.allowed_paths]
        return data

    def to_json(self, path: Path) -> None:
        """Save config to JSON file.

        Args:
            path: Path to save JSON config
        """
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


class ConfigManager:
    """Manages tool configuration."""

    def __init__(self, config: Optional[ToolConfig] = None):
        """Initialize config manager.

        Args:
            config: Optional initial configuration
        """
        self.config = config or ToolConfig.default()
        self._watchers: List[callable] = []

    def load(self, path: Path) -> None:
        """Load configuration from file.

        Args:
            path: Path to config file
        """
        self.update(ToolConfig.from_json(path))

    def save(self, path: Path) -> None:
        """Save current configuration to file.

        Args:
            path: Path to save config
        """
        self.config.to_json(path)

    def update(self, config: ToolConfig) -> None:
        """Update configuration.

        Args:
            config: New configuration
        """
        self.config = config
        self._notify_watchers()

    def watch(self, callback: callable) -> None:
        """Register a callback for config changes.

        Args:
            callback: Function to call when config changes
        """
        self._watchers.append(callback)

    def _notify_watchers(self) -> None:
        """Notify all watchers of config change."""
        for callback in self._watchers:
            callback(self.config)


class EnvironmentConfig:
    """Configuration from environment variables."""

    ENV_PREFIX = "TOOL_"

    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """Get configuration from environment variables.

        Returns:
            Dictionary of config values from environment
        """
        import os

        config = {}
        for key, value in os.environ.items():
            if key.startswith(cls.ENV_PREFIX):
                config_key = key[len(cls.ENV_PREFIX) :].lower()

                # Handle list values
                if value.startswith("[") and value.endswith("]"):
                    value = [v.strip() for v in value[1:-1].split(",")]

                # Handle boolean values
                elif value.lower() in ("true", "false"):
                    value = value.lower() == "true"

                # Handle integer values
                elif value.isdigit():
                    value = int(value)

                # Handle float values
                elif value.replace(".", "").isdigit():
                    value = float(value)

                config[config_key] = value

        return config
