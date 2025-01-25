"""Environment variable utilities."""

from typing import Set
import os

# Internal constant for storing protected variables
DOCKERFILE_VARS_FILE = os.getenv("DOCKERFILE_VARS_FILE", "/.dockerfile_vars")


def record_dockerfile_vars(env_vars: Set[str], vars_file: str | None = None) -> None:
    """Record protected environment variables from Dockerfile.

    Args:
        env_vars: Set of environment variable names to protect
        vars_file: Optional path to vars file, defaults to DOCKERFILE_VARS_FILE
    """
    path = vars_file or DOCKERFILE_VARS_FILE
    with open(path, "w") as f:
        for var in sorted(env_vars):
            f.write(f"{var}\n")


def load_dockerfile_vars(vars_file: str | None = None) -> Set[str]:
    """Load protected environment variables from Dockerfile.

    Args:
        vars_file: Optional path to vars file, defaults to DOCKERFILE_VARS_FILE

    Returns:
        Set of protected environment variable names
    """
    try:
        path = vars_file or DOCKERFILE_VARS_FILE
        with open(path) as f:
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        return set()
