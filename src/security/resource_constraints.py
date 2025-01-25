"""Resource limit utilities."""

from typing import Dict
import resource

# Internal constant for storing resource limits
DOCKERFILE_LIMITS_FILE = "/.dockerfile_limits"

# Map of limit names to resource module constants
RESOURCE_LIMITS = {
    "memory": resource.RLIMIT_AS,
    "cpu_time": resource.RLIMIT_CPU,
    "file_size": resource.RLIMIT_FSIZE,
    "processes": resource.RLIMIT_NPROC,
    "open_files": resource.RLIMIT_NOFILE,
}


def record_dockerfile_limits(limits: Dict[str, int]) -> None:
    """Record resource limits from Dockerfile.

    Args:
        limits: Dict mapping limit names to values in bytes/seconds
    """
    with open(DOCKERFILE_LIMITS_FILE, "w") as f:
        for name, value in sorted(limits.items()):
            if name in RESOURCE_LIMITS:
                f.write(f"{name}={value}\n")


def load_dockerfile_limits() -> Dict[str, int]:
    """Load resource limits from Dockerfile.

    Returns:
        Dict mapping limit names to values in bytes/seconds
    """
    try:
        limits = {}
        with open(DOCKERFILE_LIMITS_FILE) as f:
            for line in f:
                if "=" in line:
                    name, value = line.strip().split("=", 1)
                    try:
                        if name in RESOURCE_LIMITS:
                            limits[name] = int(value)
                    except ValueError:
                        pass
        return limits
    except FileNotFoundError:
        return {}


def apply_resource_limits(limits: Dict[str, int]) -> None:
    """Apply resource limits to current process.

    Args:
        limits: Dict mapping limit names to values in bytes/seconds
    """
    for name, value in limits.items():
        if name in RESOURCE_LIMITS:
            try:
                # Get current limits
                current = resource.getrlimit(RESOURCE_LIMITS[name])
                # Don't exceed hard limit
                new_limit = min(value, current[1])
                resource.setrlimit(RESOURCE_LIMITS[name], (new_limit, current[1]))
            except Exception as e:
                print(f"Warning: Failed to set {name} limit: {str(e)}")
