"""Where uploaded files (scoresheet photos) live: a folder on disk, or a private S3 bucket.

CHESSCOACH_STORAGE=local  files under <data dir>/uploads (the default; fine for running locally)
CHESSCOACH_STORAGE=s3     objects in CHESSCOACH_S3_BUCKET, using the machine's AWS credentials (on EC2, its IAM role)
"""

from __future__ import annotations

from pathlib import Path


class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("bad storage key")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes | None:
        path = self._path(key)
        return path.read_bytes() if path.exists() else None

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    # Photos are written once and looked at now and then: Standard-IA costs about half of Standard to keep.
    STORAGE_CLASS = "STANDARD_IA"

    def __init__(self, bucket: str, region: str | None):
        import boto3

        self.bucket = bucket
        self.s3 = boto3.client("s3", region_name=region)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                           ServerSideEncryption="AES256", StorageClass=self.STORAGE_CLASS)

    def get(self, key: str) -> bytes | None:
        try:
            return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self.s3.exceptions.NoSuchKey:
            return None

    def delete(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.bucket, Key=key)


def make_storage(kind: str, data_dir: Path, bucket: str, region: str | None):
    if kind == "s3":
        if not bucket:
            raise RuntimeError("CHESSCOACH_STORAGE=s3 needs CHESSCOACH_S3_BUCKET.")
        return S3Storage(bucket, region)
    if kind != "local":
        raise RuntimeError(f"Unknown CHESSCOACH_STORAGE {kind!r}; use local or s3.")
    return LocalStorage(Path(data_dir) / "uploads")
