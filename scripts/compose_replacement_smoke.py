from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request


def _run(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def _compose(project_name: str, *args: str) -> str:
    return _run("docker", "compose", "--project-name", project_name, *args)


def _container_ip(container_id: str) -> str:
    payload = json.loads(_run("docker", "inspect", container_id))[0]
    networks = payload["NetworkSettings"]["Networks"]
    addresses = [str(item.get("IPAddress") or "") for item in networks.values()]
    return next((address for address in addresses if address), "")


def _health_status(container_id: str) -> str:
    payload = json.loads(_run("docker", "inspect", container_id))[0]
    return str(payload["State"].get("Health", {}).get("Status") or "")


def _wait_until(predicate, *, timeout: float, description: str) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except Exception as exc:  # transient replacement state
            last_error = exc
        time.sleep(0.5)
    detail = f": {last_error}" if last_error is not None else ""
    raise RuntimeError(f"Timed out waiting for {description}{detail}")


def _http_ok(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(
            f"{base_url.rstrip('/')}/healthz",
            timeout=3,
        ) as response:
            return response.status == 200
    except Exception:
        return False


def run(*, project_name: str, app_image: str, base_url: str) -> dict[str, str]:
    original_app_id = _compose(project_name, "ps", "--quiet", "echobot")
    original_ingress_id = _compose(project_name, "ps", "--quiet", "ingress")
    if not original_app_id or not original_ingress_id:
        raise RuntimeError("Compose app and ingress must be running before replacement")
    if not _http_ok(base_url):
        raise RuntimeError("Ingress was not serving before app replacement")

    old_app_ip = _container_ip(original_app_id)
    if not old_app_ip:
        raise RuntimeError("Original app container did not have a network address")

    filler_name = f"{project_name}-ip-filler"
    network_name = f"{project_name}_default"
    try:
        _compose(project_name, "stop", "echobot")
        _compose(project_name, "rm", "--force", "echobot")
        _run(
            "docker",
            "run",
            "--detach",
            "--name",
            filler_name,
            "--network",
            network_name,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            app_image,
            "python",
            "-c",
            "import time; time.sleep(120)",
        )
        _compose(project_name, "up", "--detach", "--no-build", "--no-deps", "echobot")
        replacement_app_id = _compose(project_name, "ps", "--quiet", "echobot")
        _wait_until(
            lambda: _health_status(replacement_app_id) == "healthy",
            timeout=90,
            description="replacement app health",
        )

        new_app_ip = _container_ip(replacement_app_id)
        if not new_app_ip:
            raise RuntimeError("Replacement app container did not have a network address")
        if old_app_ip == new_app_ip:
            raise RuntimeError("Replacement smoke did not force a new app IP address")

        _wait_until(
            lambda: _http_ok(base_url),
            timeout=30,
            description="ingress recovery through Docker DNS",
        )
        current_ingress_id = _compose(project_name, "ps", "--quiet", "ingress")
        if original_ingress_id != current_ingress_id:
            raise RuntimeError("Ingress restarted during app replacement smoke")

        return {
            "old_app_ip": old_app_ip,
            "new_app_ip": new_app_ip,
            "ingress_container_id": current_ingress_id,
            "health": "200",
        }
    finally:
        subprocess.run(
            ["docker", "rm", "--force", filler_name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify ingress survives an app container IP replacement.",
    )
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--app-image", required=True)
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                project_name=args.project_name,
                app_image=args.app_image,
                base_url=args.base_url,
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
