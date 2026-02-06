from typing import Annotated, List
import json
from fastapi import (
    FastAPI,
    Depends,
    Form,
    Request,
    File,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from user.token import set_token, test_token
from user.add_user import signup as signup_fun
from user.changePass import change_pass
from search.search import search as search_fun
from search.search_map import search_cwws
from search.search_reading import search_reading
from utils.jwt_op import jwt_decode
from database.uplaod import up_load
from response.excptions import ERR_403
from database.upopt import opt
from database.datalist import datalist
from user.users import user_opt
from user.ivcode import iv_opt
from tools.biblecollection import biblecollection
from ai_search import ai_router
import asyncio
from pathlib import Path as pt
from es_config import es


app = FastAPI()

# CORS：携带 cookie 时不能使用 allow_origins=["*"]，必须写具体来源
_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def checkAdmin(text):
    try:
        res = jwt_decode(text)
        if res["role"] != "t0":
            raise ERR_403
    except:
        raise ERR_403


@app.get("/")
async def root():
    return {"message": "Hello World"}


# Session cookie 名称，与 test_token 中读取的 cookie 一致
SESSION_COOKIE_NAME = "session"
# Cookie 最大存活（秒），与“记住我”最长 30 天一致；实际过期以 JWT exp 为准
SESSION_COOKIE_MAX_AGE = 30 * 24 * 3600


@app.post("/token")
def login(
    remember: Annotated[str, Form()], form_data: OAuth2PasswordRequestForm = Depends()
):
    try:
        token_body = set_token(form_data.username, form_data.password, remember)
    except Exception as e:
        from fastapi import HTTPException
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    # 同时返回 JSON 和 Set-Cookie，前端可用 Authorization 或 cookie 任一方式带 token
    response = JSONResponse(
        content={
            "access_token": token_body.access_token,
            "token_type": token_body.token_type,
        }
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token_body.access_token,
        path="/",
        max_age=SESSION_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/testToken")
def test_token_fun(userinfo: dict = Depends(test_token)):
    if userinfo:
        return {"status": "OK", "userinfo": userinfo}
    return {"status": "NG"}


@app.post("/signup")
def signup(username: str = Form(), password: str = Form(), ivcode: str = Form()):
    try:
        return signup_fun(username, password, ivcode)
    except:
        pass


@app.post("/changePass", dependencies=[Depends(test_token)])
def chanPass(username: str = Form(), old_pass: str = Form(), new_pass: str = Form()):
    try:
        return change_pass(username, old_pass, new_pass)
    except:
        pass


@app.post("/search", dependencies=[Depends(test_token)])
def search(input: str = Form(), args: str = Form()):
    try:
        result = search_fun(input, args)
        if result is None:
            result = {"total": 0, "msg": []}
        return result
    except Exception:
        return {"total": 0, "msg": []}


@app.post("/cws", dependencies=[Depends(test_token)])
def get_map(input: str = Form(), fwds: str = Form(), index: str = Form()):
    try:
        return search_cwws(input, fwds, index)
    except:
        pass


@app.post("/reading", dependencies=[Depends(test_token)])
def get_map(refid: str = Form()):
    try:
        return search_reading(refid)
    except:
        pass


@app.post("/getvers", dependencies=[Depends(test_token)])
def get_vers(input: str = Form()):
    try:
        return biblecollection(input)
    except:
        return JSONResponse(content={"error": "404 Not Found"}, status_code=404)


@app.post("/datalist")
async def datalist_fun(r: Request, index: str = Form(), opt: str = Form()):
    session = r.cookies.get("session")
    try:
        await checkAdmin(session)
        return datalist(index, opt)
    except:
        return JSONResponse(content={"error": "403 Forbidden"}, status_code=403)


clients: List[WebSocket] = []


@app.websocket("/ws/progress")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)
    try:
        while True:
            # 处理 WebSocket 的其他操作，比如接收消息
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        clients.remove(websocket)


@app.post("/process")
async def start_process(r: Request, filename: str = Form(), action: str = Form()):
    session = r.cookies.get("session")
    try:
        await checkAdmin(session)
        jddir = (pt(__file__).parent / "database" / "upload").rglob("*.json")
        jds = {}
        for item in jddir:
            jds[item.name] = item
        sn = 0
        old = 0
        pgs = 0
        if filename in jds:
            jd = json.loads(jds[filename].read_text("utf"))
            jdlen = len(jd)
            for i in jd:
                sn += 1
                pgs = int((sn / jdlen) * 100)
                if pgs != old:
                    old = pgs
                    progress = {"progress": pgs}
                    await send_progress_to_clients(progress)
                    await asyncio.sleep(0.1)
                indexs = i.pop("index")
                if "refid" in i:
                    idx = i["refid"]
                else:
                    idx = i["id"]
                for index in indexs:
                    es.index(index=index, id=idx, body=i)
        return {"tip": f"{filename}: 导入完成！"}
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=403)


async def send_progress_to_clients(progress: dict):
    disconnected_clients = []
    for client in clients:
        try:
            # 检查客户端连接状态
            if client.application_state == client.application_state.CONNECTED:
                await client.send_json(progress)
            else:
                disconnected_clients.append(client)
        except Exception:
            disconnected_clients.append(client)
    # 移除已断开的客户端
    for client in disconnected_clients:
        if client in clients:
            clients.remove(client)


@app.post("/upopt")
async def upopt_fun(r: Request, filename: str = Form(), action: str = Form()):
    session = r.cookies.get("session")
    try:
        await checkAdmin(session)
        return opt(filename, action)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=403)


@app.post("/iv_opts")
async def iv_opts_fun(
    r: Request, iv: str = Form(), action: str = Form(), role: str = Form()
):
    session = r.cookies.get("session")
    try:
        await checkAdmin(session)
        return iv_opt(iv, role, action)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=403)


@app.post("/usr_opts")
async def usr_opts(
    r: Request, username: str = Form(), action: str = Form(), role: str = Form()
):
    session = r.cookies.get("session")
    try:
        await checkAdmin(session)
        return user_opt(username, action, role)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=403)


@app.post("/upload")
async def upload_file_fun(r: Request, file: UploadFile = File(...)):
    session = r.cookies.get("session")
    await checkAdmin(session)
    try:
        contents = await file.read()
        filename = file.filename
        up_load(filename, contents)
        return JSONResponse(
            content={"filename": filename, "size": len(contents)}, status_code=200
        )
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


# AI 搜索路由（Claude 问答 / RAG）
app.include_router(ai_router)
