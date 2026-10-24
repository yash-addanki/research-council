"""Read secrets from the macOS Keychain (service 'research-council')."""

import subprocess


class MissingSecret(RuntimeError):
    pass


def get_secret(name: str) -> str:
    proc = subprocess.run(
        ["security", "find-generic-password", "-s", "research-council", "-a", name, "-w"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise MissingSecret(f"Keychain item research-council/{name} not found")
    return proc.stdout.strip()
