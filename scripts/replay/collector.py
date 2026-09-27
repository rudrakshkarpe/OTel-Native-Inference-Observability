"""Start or stop only the isolated evidence replay Collector."""

import argparse
import json
import os
import subprocess
from pathlib import Path


def main(action):
    config_file = Path(".secrets/dash0.json")
    config = json.loads(config_file.read_text()) if config_file.exists() else {}
    env = os.environ.copy()
    for key, field in [
        ("DASH0_ENDPOINT", "grpc_endpoint"),
        ("DASH0_AUTH_TOKEN", "token"),
        ("DASH0_DATASET", "dataset"),
    ]:
        if key not in env and field in config:
            env[key] = config[field]
    env.setdefault("DASH0_DATASET", "default")
    if action == "down":
        env.setdefault("DASH0_ENDPOINT", "unused.invalid:4317")
        env.setdefault("DASH0_AUTH_TOKEN", "unused")
    command = ["docker", "compose", "-f", "docker-compose.replay.yml"]
    command += ["up", "-d"] if action == "up" else ["down"]
    subprocess.run(command, env=env, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["up", "down"])
    main(parser.parse_args().action)
