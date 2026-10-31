from pathlib import Path

# Supervisor supplies config.yaml's version as BUILD_VERSION during the build.
_version_file = Path(__file__).with_name("app-version")
APP_VERSION = _version_file.read_text().strip() if _version_file.exists() else "1.1.2"
