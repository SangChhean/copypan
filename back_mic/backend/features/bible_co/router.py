import base64
import logging

from fastapi import APIRouter, Depends, Form
from fastapi.responses import JSONResponse

from user.token import test_token
from features.bible_co.biblecollection import biblecollection
from ai_search.ai_service import ai_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["bible_co"])


@router.post("/getvers", dependencies=[Depends(test_token)])
def get_vers(input: str = Form(), lang: str = Form(default="zh")):
    try:
        return biblecollection(input, lang)
    except Exception:
        return JSONResponse(content={"error": "404 Not Found"}, status_code=404)


@router.post("/getvers/format_download", dependencies=[Depends(test_token)])
def getvers_format_download(contents: str = Form(), filename: str = Form(default="英文经文汇集")):
    try:
        from ai_search.ai_service import format_english_bibco_docx
        contents = contents.replace("\r\n", "\n").replace("\r", "\n")
        result = format_english_bibco_docx(contents, filename)
        return result
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.post("/getvers/format_download_zh", dependencies=[Depends(test_token)])
def getvers_format_download_zh(
    contents: str = Form(),
    filename: str = Form(default="中文经文汇集"),
):
    try:
        contents = contents.replace("\r\n", "\n").replace("\r", "\n")
        _header_placeholder = "\u200b"
        padded = f"{_header_placeholder}\n{_header_placeholder}\n{_header_placeholder}\n{contents}"
        result = ai_service.format_feast_outline_docx(
            contents=[padded],
            outline_type="with_scripture",
        )
        if result.get("error") and not result.get("docx_bytes"):
            return JSONResponse(content={"error": result["error"]}, status_code=400)
        docx_bytes = result.get("docx_bytes")
        if not docx_bytes:
            return JSONResponse(
                content={"error": result.get("error") or "生成 DOCX 失败"},
                status_code=400,
            )
        out_name = filename if filename.endswith(".docx") else f"{filename}.docx"
        return {
            "docx_base64": base64.b64encode(docx_bytes).decode("utf-8"),
            "filename": out_name,
        }
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
