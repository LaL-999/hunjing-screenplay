"""剧本导出 API — PR#17。

提供 3 种行业级格式导出:
  GET /screenplays/{id}/export.fountain   ← 行业标准,Final Draft 等可导入
  GET /screenplays/{id}/export.txt        ← 中文友好纯文本
  GET /screenplays/{id}/export.yaml       ← 原始结构化数据

所有 endpoint 返回 attachment 让浏览器自动下载。
"""
from __future__ import annotations

from urllib.parse import quote

import yaml as yamllib
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app.services import screenplay_store
from app.services.screenplay_exporter import (
    export_to_fountain,
    export_to_txt,
    make_export_filename,
)

router = APIRouter(tags=["export"])


def _load_parsed_screenplay(screenplay_id: str) -> tuple[dict, dict]:
    """拉记录 + 解析 yaml,返 (parsed_dict, raw_record)。"""
    record = screenplay_store.get_screenplay_by_id(screenplay_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SCREENPLAY_NOT_FOUND", "message": "剧本不存在"},
        )
    try:
        parsed = yamllib.safe_load(record["yaml_text"])
    except yamllib.YAMLError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "YAML_PARSE_FAILED", "message": str(e)},
        )
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INVALID_SCREENPLAY", "message": "yaml 非 dict"},
        )
    return parsed, record


def _make_download_response(content: str, filename: str, mime: str) -> Response:
    """构造 attachment 下载响应。

    HTTP header 不能含非 ASCII 字符,所以:
      - filename       使用 ASCII 兜底名(防御性,旧浏览器降级用)
      - filename*=UTF-8'' 使用 RFC 5987 URL-encoded 形式,现代浏览器优先用这个
    """
    # ASCII 兜底:去掉所有非 ASCII 字符,得到一个合法的 fallback 文件名
    ascii_fallback = "".join(c if ord(c) < 128 else "_" for c in filename)
    # 至少保留扩展名能识别
    if not ascii_fallback.strip("_"):
        # 全部被替换了 → 拼最低限度名字
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "txt"
        ascii_fallback = f"screenplay.{ext}"
    filename_quoted = quote(filename)
    disposition = (
        f"attachment; filename=\"{ascii_fallback}\"; "
        f"filename*=UTF-8''{filename_quoted}"
    )
    return Response(
        content=content,
        media_type=mime,
        headers={
            "Content-Disposition": disposition,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/screenplays/{screenplay_id}/export.fountain")
def export_fountain(screenplay_id: str) -> Response:
    """导出 Fountain 格式 — 行业标准,Final Draft / WriterDuet 等可直接导入。"""
    parsed, _ = _load_parsed_screenplay(screenplay_id)
    content = export_to_fountain(parsed)
    filename = make_export_filename(parsed, "fountain")
    return _make_download_response(content, filename, "text/plain; charset=utf-8")


@router.get("/screenplays/{screenplay_id}/export.txt")
def export_txt(screenplay_id: str) -> Response:
    """导出 TXT 格式 — 中文友好纯文本,适合微信发送 / 打印。"""
    parsed, _ = _load_parsed_screenplay(screenplay_id)
    content = export_to_txt(parsed)
    filename = make_export_filename(parsed, "txt")
    return _make_download_response(content, filename, "text/plain; charset=utf-8")


@router.get("/screenplays/{screenplay_id}/export.yaml")
def export_yaml(screenplay_id: str) -> Response:
    """导出 YAML 格式 — 原始结构化数据,给工具链 / 二次开发用。"""
    _, record = _load_parsed_screenplay(screenplay_id)
    yaml_text = record["yaml_text"]
    # 文件名用 meta.title
    parsed, _ = _load_parsed_screenplay(screenplay_id)
    filename = make_export_filename(parsed, "yaml")
    return _make_download_response(yaml_text, filename, "application/x-yaml; charset=utf-8")
