import json
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

from ui.character_overlay import LayerConfig


@dataclass
class VTuberConfig:
    """Configuration for VTuber overlay settings."""
    background_path: str = ""
    layers: list[dict] = None
    scream_threshold: float = 0.85
    red_smoothness_ms: int = 100
    sensitivity: int = 8
    resolution: int = 0  # index in resolution list
    camera_index: int = 0
    microphone_index: int = 0

    def __post_init__(self):
        if self.layers is None:
            self.layers = []

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "VTuberConfig":
        """Create from dictionary."""
        return VTuberConfig(
            background_path=data.get("background_path", ""),
            layers=data.get("layers", []),
            scream_threshold=data.get("scream_threshold", 0.85),
            red_smoothness_ms=data.get("red_smoothness_ms", 100),
            sensitivity=data.get("sensitivity", 8),
            resolution=data.get("resolution", 0),
            camera_index=data.get("camera_index", 0),
            microphone_index=data.get("microphone_index", 0),
        )

    def to_layer_configs(self) -> list[LayerConfig]:
        """Convert layer dicts to LayerConfig objects."""
        configs = []
        for layer_data in self.layers:
            config = LayerConfig(
                path=layer_data.get("path", ""),
                min_vol=layer_data.get("min_vol", 0.0),
                max_vol=layer_data.get("max_vol", 1.0),
                name=layer_data.get("name", ""),
            )
            configs.append(config)
        return configs

    @staticmethod
    def from_layer_configs(layers: list[LayerConfig]) -> list[dict]:
        """Convert LayerConfig objects to dicts."""
        return [
            {
                "path": layer.path,
                "min_vol": layer.min_vol,
                "max_vol": layer.max_vol,
                "name": layer.name,
            }
            for layer in layers
        ]


class ConfigManager:
    """Manages loading and saving of VTuber configurations."""

    CONFIG_DIR = Path.home() / ".vtuber_tool"
    DEFAULT_CONFIG_FILE = CONFIG_DIR / "default.json"
    RECENT_CONFIG_FILE = CONFIG_DIR / "recent.json"

    def __init__(self):
        self.CONFIG_DIR.mkdir(exist_ok=True)

    def save_config(self, config: VTuberConfig, file_path: Optional[Path] = None) -> bool:
        """Save configuration to file. If no path, saves to recent config."""
        try:
            target_path = file_path or self.RECENT_CONFIG_FILE
            target_path = Path(target_path)
            target_path.parent.mkdir(exist_ok=True)

            with open(target_path, "w") as f:
                json.dump(config.to_dict(), f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def load_config(self, file_path: Optional[Path] = None) -> Optional[VTuberConfig]:
        """Load configuration from file. If no path, loads from recent config."""
        try:
            target_path = file_path or self.RECENT_CONFIG_FILE
            target_path = Path(target_path)

            if not target_path.exists():
                return None

            with open(target_path, "r") as f:
                data = json.load(f)
            return VTuberConfig.from_dict(data)
        except Exception as e:
            print(f"Error loading config: {e}")
            return None

    def get_default_config(self) -> VTuberConfig:
        """Get default configuration."""
        return VTuberConfig()

    def save_as_default(self, config: VTuberConfig) -> bool:
        """Save as default configuration."""
        return self.save_config(config, self.DEFAULT_CONFIG_FILE)

    def load_default(self) -> Optional[VTuberConfig]:
        """Load default configuration."""
        return self.load_config(self.DEFAULT_CONFIG_FILE)

    def has_recent_config(self) -> bool:
        """Check if recent config exists."""
        return self.RECENT_CONFIG_FILE.exists()
