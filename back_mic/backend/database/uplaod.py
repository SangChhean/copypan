from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from pathlib import Path as pt
from datetime import datetime


app = FastAPI()
basedir = pt(__file__).parent
uploadir = basedir / "upload"


def del_other_day():
    for d in uploadir.iterdir():
        if d.is_dir():
            if d.name != datetime.now().strftime("%Y%m%d"):
                for f in d.iterdir():
                    f.unlink()
                d.rmdir()


def up_load(filename, contents):
    today = datetime.now().strftime("%Y%m%d")
    del_other_day()
    updir = uploadir / today
    updir.mkdir(parents=True, exist_ok=True)
    sdir = updir / filename
    sdir.write_bytes(contents)
