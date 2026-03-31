import argparse
import re
from pathlib import Path

IMAGE_MAP = {
    "api.yaml": "multi-agent-sdlc-api",
    "orchestrator.yaml": "multi-agent-sdlc-orchestrator",
    "coding.yaml": "multi-agent-sdlc-coding",
    "testing.yaml": "multi-agent-sdlc-testing",
    "review.yaml": "multi-agent-sdlc-review",
    "docs.yaml": "multi-agent-sdlc-docs",
    "gitops.yaml": "multi-agent-sdlc-gitops",
}

IMAGE_LINE = re.compile(r"^(\s*image:\s*)(\S+)(\s*)$")


def update_manifest(path: Path, image_ref: str) -> bool:
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    lines = path.read_text().splitlines()
    changed = False
    image_lines_seen = 0
    updated: list[str] = []

    for line in lines:
        match = IMAGE_LINE.match(line)
        if match:
            image_lines_seen += 1
            prefix, current, suffix = match.groups()
            if current != image_ref:
                line = f"{prefix}{image_ref}{suffix}"
                changed = True
        updated.append(line)

    if image_lines_seen != 1:
        raise RuntimeError(f"Expected exactly one image line in {path}, found {image_lines_seen}")

    if changed:
        path.write_text("\n".join(updated) + "\n")

    return changed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update multi-agent image tags in devops manifests"
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Path to checked-out devops-k8s-platform repo",
    )
    parser.add_argument("--dockerhub-username", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()

    base = Path(args.repo) / "kubernetes" / "apps" / "multi-agent"
    any_changed = False
    for filename, image_name in IMAGE_MAP.items():
        manifest = base / filename
        image_ref = f"{args.dockerhub_username}/{image_name}:{args.tag}"
        changed = update_manifest(manifest, image_ref)
        any_changed = any_changed or changed

    if any_changed:
        print("updated=true")
    else:
        print("updated=false")


if __name__ == "__main__":
    main()
