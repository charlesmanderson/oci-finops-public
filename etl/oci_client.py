"""OCI SDK wrapper for Object Storage — lists and downloads FOCUS report files."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import oci

from etl.config import OciTenancyConfig

logger = logging.getLogger(__name__)


@dataclass
class ReportFile:
    name: str
    size: int
    time_created: str | None = None


class OciObjectStorageClient:
    """Wraps the OCI Object Storage SDK for FOCUS report access."""

    def __init__(self, config: OciTenancyConfig):
        self.config = config
        self._client = self._build_client()

    def _build_client(self) -> oci.object_storage.ObjectStorageClient:
        """Build an OCI client using config file (when available) or Instance Principal."""
        config_path = Path(self.config.config_file).expanduser()
        if config_path.is_file():
            logger.info("Using config file authentication: %s [%s]", config_path, self.config.config_profile)
            oci_config = oci.config.from_file(str(config_path), self.config.config_profile)
            return oci.object_storage.ObjectStorageClient(oci_config)
        try:
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            logger.info("Using Instance Principal authentication")
            return oci.object_storage.ObjectStorageClient(config={}, signer=signer)
        except Exception:
            raise RuntimeError(
                f"No OCI authentication available: config file {config_path} not found "
                "and Instance Principal unavailable"
            )

    def list_focus_reports(self, year: str | None = None, month: str | None = None) -> list[ReportFile]:
        """List FOCUS report .csv.gz files under the expected path prefix."""
        prefix = "FOCUS Reports/"
        if year:
            prefix += f"{year}/"
            if month:
                prefix += f"{month.zfill(2)}/"

        logger.info("Listing objects with prefix: %s", prefix)
        files: list[ReportFile] = []
        next_start = None

        while True:
            kwargs = {
                "namespace_name": self.config.namespace,
                "bucket_name": self.config.bucket_name,
                "prefix": prefix,
                "fields": "name,size,timeCreated",
            }
            if next_start:
                kwargs["start"] = next_start

            response = self._client.list_objects(**kwargs)
            for obj in response.data.objects:
                if obj.name.endswith(".csv.gz"):
                    files.append(ReportFile(
                        name=obj.name,
                        size=obj.size,
                        time_created=str(obj.time_created) if obj.time_created else None,
                    ))
            next_start = response.data.next_start_with
            if not next_start:
                break

        logger.info("Found %d FOCUS report files", len(files))
        return files

    def download_file(self, object_name: str, dest_dir: Path) -> Path:
        """Download a single object to the local filesystem."""
        dest_path = dest_dir / Path(object_name).name
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Downloading %s → %s", object_name, dest_path)
        response = self._client.get_object(
            namespace_name=self.config.namespace,
            bucket_name=self.config.bucket_name,
            object_name=object_name,
        )

        with open(dest_path, "wb") as f:
            for chunk in response.data.raw.stream(1024 * 1024):
                f.write(chunk)

        logger.info("Downloaded %s (%d bytes)", dest_path.name, dest_path.stat().st_size)
        return dest_path
