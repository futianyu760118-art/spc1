"""存量附件迁移：本地 uploads 目录 -> MinIO 桶（按原 key 保留路径结构）

用法（backend/ 目录下，需 .env 已配置 STORAGE_S3_*）：
    python migrate_uploads_to_minio.py --dry-run    # 预览
    python migrate_uploads_to_minio.py              # 执行（已存在跳过）
    python migrate_uploads_to_minio.py --overwrite  # 强制覆盖

迁移完成并验证后，将生产 .env 切 STORAGE_BACKEND=s3 重新部署。
"""
import argparse
import sys
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from app.core.config import get_settings

# 扩展名 -> Content-Type（与 Settings.STORAGE_ALLOWED_MIMES 对应；仅迁移推断用）
EXT_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".zip": "application/zip", ".rar": "application/x-rar-compressed",
    ".txt": "text/plain", ".csv": "text/csv",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="本地 uploads -> MinIO 迁移")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要上传的文件，不实际上传")
    parser.add_argument("--overwrite", action="store_true", help="已存在的对象也覆盖（默认跳过）")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.STORAGE_S3_ENDPOINT:
        sys.exit("STORAGE_S3_ENDPOINT 未配置，请先完善 .env")
    root = Path(settings.STORAGE_LOCAL_ROOT)
    if not root.is_dir():
        sys.exit(f"本地目录不存在: {root}")

    client = Minio(
        settings.STORAGE_S3_ENDPOINT,
        access_key=settings.STORAGE_S3_ACCESS_KEY,
        secret_key=settings.STORAGE_S3_SECRET_KEY,
        secure=bool(settings.STORAGE_S3_SECURE),
        region=settings.STORAGE_S3_REGION or None,
    )
    bucket = settings.STORAGE_S3_BUCKET or "spc-files"
    if not client.bucket_exists(bucket):
        sys.exit(f"桶不存在: {bucket}（请先以 S3 配置启动一次 backend 自动建桶）")

    total = uploaded = skipped = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        key = path.relative_to(root).as_posix()
        total += 1
        if not args.overwrite:
            try:
                client.stat_object(bucket, key)
                skipped += 1
                print(f"[跳过] {key}")
                continue
            except S3Error as exc:
                if exc.code != "NoSuchKey":
                    raise
        mime = EXT_MIME.get(path.suffix.lower(), "application/octet-stream")
        if args.dry_run:
            print(f"[预览] {key} ({mime})")
            continue
        client.fput_object(bucket, key, str(path), content_type=mime)
        uploaded += 1
        print(f"[上传] {key}")
    print(f"完成：共 {total} 个文件，上传 {uploaded}，跳过 {skipped}")


if __name__ == "__main__":
    main()
