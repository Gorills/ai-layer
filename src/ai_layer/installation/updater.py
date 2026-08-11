from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_layer import __version__
from ai_layer.core.config import get_settings
from ai_layer.domain.errors import ErrorCategory, ErrorCode, StructuredError

MAX_MANIFEST_BYTES = 128 * 1024
MAX_RELEASE_BYTES = 512 * 1024 * 1024
CHANNEL_FILE = "update-channel.json"


class UpdateError(StructuredError, RuntimeError):
    """Stable update failure exposed consistently through CLI/API transports."""


def _update_error(
    code: ErrorCode,
    message: str,
    *,
    retryable: bool = False,
    required_action: str = "Inspect the signed update channel/release and retry only after correction.",
) -> UpdateError:
    return UpdateError(
        code=code,
        category=ErrorCategory.GOVERNANCE if code == ErrorCode.UPDATE_SIGNATURE_INVALID else ErrorCategory.EXTERNAL,
        message=message,
        retryable=retryable,
        required_action=required_action,
    )


@dataclass(frozen=True)
class UpdateChannel:
    manifest_url: str
    public_key: Path


@dataclass(frozen=True)
class UpdateRelease:
    version: str
    artifact_url: str
    artifact_sha256: str
    signature_url: str


def _safe_url(value: str, *, field: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"https", "file"}:
        raise _update_error(ErrorCode.UPDATE_CHANNEL_INVALID, f"{field} must use https:// or file://")
    if parsed.scheme == "https" and not parsed.hostname:
        raise _update_error(ErrorCode.UPDATE_CHANNEL_INVALID, f"{field} is missing a hostname")
    if parsed.username or parsed.password:
        raise _update_error(ErrorCode.UPDATE_CHANNEL_INVALID, f"{field} must not contain embedded credentials")
    return value


def _download(url: str, *, max_bytes: int) -> bytes:
    _safe_url(url, field="update URL")
    request = urllib.request.Request(url, headers={"User-Agent": f"ai-layer/{__version__}"})
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - scheme is allowlisted above.
        length = response.headers.get("Content-Length")
        if length and int(length) > max_bytes:
            raise _update_error(ErrorCode.UPDATE_ARTIFACT_INVALID, f"update resource exceeds {max_bytes} bytes")
        payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise _update_error(ErrorCode.UPDATE_ARTIFACT_INVALID, f"update resource exceeds {max_bytes} bytes")
    return payload


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = value.strip().split(".")
    if not parts or any(not part.isdigit() for part in parts):
        raise _update_error(ErrorCode.UPDATE_MANIFEST_INVALID, f"release version must be numeric dotted form, got {value!r}")
    return tuple(int(part) for part in parts)


def load_channel(*, manifest_url: str | None = None, public_key: str | Path | None = None) -> UpdateChannel:
    settings = get_settings()
    configured: dict[str, Any] = {}
    channel_path = settings.home / CHANNEL_FILE
    if channel_path.is_file():
        try:
            loaded = json.loads(channel_path.read_text(encoding="utf-8"))
            configured = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            raise _update_error(ErrorCode.UPDATE_CHANNEL_INVALID, f"invalid update channel configuration: {channel_path}: {exc}") from exc
    url = str(manifest_url or os.getenv("AI_LAYER_UPDATE_MANIFEST_URL") or configured.get("manifest_url") or "").strip()
    key_value = public_key or os.getenv("AI_LAYER_UPDATE_PUBLIC_KEY") or configured.get("public_key")
    if not url or not key_value:
        raise _update_error(
            ErrorCode.UPDATE_CHANNEL_INVALID,
            f"Signed update channel is not configured in {channel_path}.",
            required_action="Configure manifest_url + public_key once, or pass --manifest-url/--public-key.",
        )
    key = Path(str(key_value)).expanduser().resolve()
    if not key.is_file() or key.is_symlink():
        raise _update_error(ErrorCode.UPDATE_CHANNEL_INVALID, f"update public key is missing or unsafe: {key}")
    return UpdateChannel(_safe_url(url, field="manifest_url"), key)


def _parse_release(manifest_bytes: bytes) -> UpdateRelease:
    try:
        payload = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _update_error(ErrorCode.UPDATE_MANIFEST_INVALID, f"signed update manifest is invalid JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise _update_error(ErrorCode.UPDATE_MANIFEST_INVALID, "signed update manifest schema must be 1")
    version = str(payload.get("version") or "").strip()
    artifact_url = _safe_url(str(payload.get("artifact_url") or "").strip(), field="artifact_url")
    signature_url = _safe_url(str(payload.get("signature_url") or "").strip(), field="signature_url")
    digest = str(payload.get("artifact_sha256") or "").strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise _update_error(ErrorCode.UPDATE_MANIFEST_INVALID, "artifact_sha256 must be a lowercase SHA-256 hex digest")
    _version_tuple(version)
    return UpdateRelease(version, artifact_url, digest, signature_url)


def _verify_manifest_signature(manifest_bytes: bytes, signature: bytes, public_key: Path) -> None:
    openssl = shutil.which("openssl")
    if not openssl:
        raise _update_error(ErrorCode.UPDATE_SIGNATURE_INVALID, "openssl is required to verify signed update manifests")
    with tempfile.TemporaryDirectory(prefix="ai-layer-update-signature-") as temp:
        temp_dir = Path(temp)
        manifest_path = temp_dir / "manifest.json"
        signature_path = temp_dir / "manifest.sig"
        manifest_path.write_bytes(manifest_bytes)
        signature_path.write_bytes(signature)
        result = subprocess.run(
            [openssl, "dgst", "-sha256", "-verify", str(public_key), "-signature", str(signature_path), str(manifest_path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "signature verification failed").strip()[:500]
        raise _update_error(ErrorCode.UPDATE_SIGNATURE_INVALID, detail)


def _safe_extract(archive: Path, destination: Path) -> Path:
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        roots: set[str] = set()
        for item in members:
            candidate = Path(item.filename)
            if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
                raise _update_error(ErrorCode.UPDATE_ARTIFACT_INVALID, f"unsafe release archive member: {item.filename}")
            roots.add(candidate.parts[0])
            if item.is_dir():
                continue
            target = (destination / candidate).resolve()
            if destination.resolve() not in target.parents:
                raise _update_error(ErrorCode.UPDATE_ARTIFACT_INVALID, f"release archive escapes extraction root: {item.filename}")
            mode = (item.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise _update_error(ErrorCode.UPDATE_ARTIFACT_INVALID, f"release archive symlinks are forbidden: {item.filename}")
        if len(roots) != 1:
            raise _update_error(ErrorCode.UPDATE_ARTIFACT_INVALID, "release archive must contain exactly one top-level directory")
        bundle.extractall(destination)
    root = destination / next(iter(roots))
    if not (root / "install.sh").is_file() or not (root / "scripts" / "release_gate.py").is_file():
        raise _update_error(ErrorCode.UPDATE_ARTIFACT_INVALID, "release archive is missing installer/release gate")
    return root


def check_update(*, manifest_url: str | None = None, public_key: str | Path | None = None) -> dict[str, Any]:
    channel = load_channel(manifest_url=manifest_url, public_key=public_key)
    manifest_bytes = _download(channel.manifest_url, max_bytes=MAX_MANIFEST_BYTES)
    release = _parse_release(manifest_bytes)
    signature = _download(release.signature_url, max_bytes=64 * 1024)
    _verify_manifest_signature(manifest_bytes, signature, channel.public_key)
    newer = _version_tuple(release.version) > _version_tuple(__version__)
    return {
        "ok": True,
        "current_version": __version__,
        "available_version": release.version,
        "update_available": newer,
        "manifest_url": channel.manifest_url,
        "signature": "verified",
        "release": release,
    }


def install_update(
    *,
    manifest_url: str | None = None,
    public_key: str | Path | None = None,
    check_only: bool = False,
) -> dict[str, Any]:
    checked = check_update(manifest_url=manifest_url, public_key=public_key)
    release: UpdateRelease = checked.pop("release")
    if check_only or not checked["update_available"]:
        return checked
    artifact_bytes = _download(release.artifact_url, max_bytes=MAX_RELEASE_BYTES)
    actual_digest = _sha256_bytes(artifact_bytes)
    if actual_digest != release.artifact_sha256:
        raise _update_error(
            ErrorCode.UPDATE_CHECKSUM_MISMATCH,
            f"Artifact checksum mismatch: expected {release.artifact_sha256}, got {actual_digest}",
        )
    with tempfile.TemporaryDirectory(prefix="ai-layer-update-") as temp:
        temp_dir = Path(temp)
        archive = temp_dir / "release.zip"
        archive.write_bytes(artifact_bytes)
        source_root = _safe_extract(archive, temp_dir / "unpacked")
        preflight = subprocess.run(
            [os.sys.executable, str(source_root / "scripts" / "release_gate.py"), "--json"],
            cwd=source_root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if preflight.returncode != 0:
            detail = (preflight.stdout or preflight.stderr or "release preflight failed").strip()[-2000:]
            raise _update_error(ErrorCode.UPDATE_PREFLIGHT_FAILED, detail)
        installer = source_root / "install.sh"
        installer.chmod(installer.stat().st_mode | 0o100)
        installed = subprocess.run(
            [str(installer)],
            cwd=source_root,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
        if installed.returncode != 0:
            detail = (installed.stdout + "\n" + installed.stderr).strip()[-4000:]
            raise _update_error(ErrorCode.UPDATE_INSTALL_FAILED, detail)
    return {
        **checked,
        "ok": True,
        "updated": True,
        "installed_version": release.version,
        "artifact_sha256": actual_digest,
        "installer": "completed",
        "post_install_contract": "installer performs migration, atomic runtime switch, service restart, health and project reconciliation",
    }
