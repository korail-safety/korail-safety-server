"""파일 저장소(AWS S3). 파일을 다루는 코드는 모두 이 모듈의 함수만 쓴다.

DB에는 S3 키(버킷 안의 경로, 예: reports/{videoId}/{파일id}.pdf)만 저장하고,
브라우저에는 presigned URL(일정 시간만 유효한 임시 주소)을 내려준다.
"""

from functools import lru_cache
from urllib.parse import quote

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from app.core.config import settings


@lru_cache
def _client() -> BaseClient:
    options = {
        "region_name": settings.aws_region,
        # presigned URL을 리전 주소로 만들도록 (서명 v4)
        "config": Config(signature_version="s3v4"),
    }
    # 키가 있으면 그 키로, 없으면 boto3 기본 방식(EC2 IAM 역할 등)으로 인증
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        options["aws_access_key_id"] = settings.aws_access_key_id
        options["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.client("s3", **options)


def upload_bytes(key: str, data: bytes, content_type: str) -> None:
    _client().put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type)


def read_bytes(key: str) -> bytes:
    """파일 내용을 통째로 읽는다 (예: 분석할 때 보고서 PDF)"""
    response = _client().get_object(Bucket=settings.s3_bucket, Key=key)
    return response["Body"].read()


def delete(key: str) -> None:
    _client().delete_object(Bucket=settings.s3_bucket, Key=key)


def delete_prefix(prefix: str) -> None:
    """prefix로 시작하는 파일을 모두 지운다 (예: 영상 하나에 딸린 파일 전체)"""
    paginator = _client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=prefix):
        objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
        if objects:
            _client().delete_objects(Bucket=settings.s3_bucket, Delete={"Objects": objects})


def presigned_url(key: str, download_filename: str | None = None) -> str:
    """브라우저용 임시 주소. download_filename을 주면 열 때 그 이름으로 다운로드된다."""
    params = {"Bucket": settings.s3_bucket, "Key": key}
    if download_filename:
        # 한글 파일명도 깨지지 않게 RFC 5987 형식으로
        params["ResponseContentDisposition"] = (
            f"attachment; filename*=UTF-8''{quote(download_filename)}"
        )
    return _client().generate_presigned_url(
        "get_object", Params=params, ExpiresIn=settings.presigned_url_expire_seconds
    )
