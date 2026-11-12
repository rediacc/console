"""The Elite renet template's web service keeps the same environment as private/elite's compose, minus the networking keys."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
ELITE = ROOT / "private/elite/docker-compose.yml"
TEMPLATE = ROOT / "packages/cli/templates/elite/docker-compose.yml"

# Elite names the host through SYSTEM_DOMAIN; the template names it ELITE_DOMAIN and lets Traefik terminate TLS.
ELITE_ONLY = {"SYSTEM_DOMAIN"}
TEMPLATE_ONLY = {
    "ENABLE_HTTPS",
    "UPSTREAM_URL",
    "UPSTREAM_API_KEY",
    # The template runs the on-prem server itself (rdc server install), so it seeds the root user and the on-prem keys; elite is the hosted image and takes them elsewhere.
    "ROOT_EMAIL",
    "ON_PREMISE_MODE",
    "ON_PREMISE_PRIVATE_KEY",
    "ON_PREMISE_PUBLIC_KEY",
}


def _web_env_keys(text: str) -> set[str]:
    env = yaml.safe_load(text)["services"]["web"]["environment"]
    if isinstance(env, dict):
        return set(env)
    return {item.split("=", 1)[0] for item in env}


def _diff(elite_text: str, template_text: str) -> tuple[set[str], set[str]]:
    elite = _web_env_keys(elite_text) - ELITE_ONLY
    template = _web_env_keys(template_text) - TEMPLATE_ONLY
    return elite - template, template - elite


def test_template_web_env_matches_elite():
    missing, extra = _diff(ELITE.read_text(), TEMPLATE.read_text())
    assert missing == set(), f"Elite has web variables the template lacks: {sorted(missing)}"
    assert extra == set(), f"template-only web variables: {sorted(extra)}"


def _non_server_images(text: str) -> dict[str, str]:
    services = yaml.safe_load(text)["services"]
    return {name: svc["image"] for name, svc in services.items() if name != "web"}


def _unpinned(images: dict[str, str]) -> dict[str, str]:
    return {name: image for name, image in images.items() if "@sha256:" not in image}


def test_non_server_images_are_digest_pinned():
    assert _unpinned(_non_server_images(TEMPLATE.read_text())) == {}


def test_control_unpinned_image_is_detected():
    text = TEMPLATE.read_text()
    text = re.sub(r"(image: rustfs/rustfs)@sha256:[0-9a-f]+", r"\1:latest", text, count=1)
    assert "rustfs" in _unpinned(_non_server_images(text))


def test_control_new_elite_variable_is_detected():
    elite = ELITE.read_text().replace(
        "      - SMTP_HOST=", "      - NEW_ELITE_VARIABLE=1\n      - SMTP_HOST=", 1
    )
    missing, _ = _diff(elite, TEMPLATE.read_text())
    assert missing == {"NEW_ELITE_VARIABLE"}
