from fastapi import HTTPException

ERR_401 = HTTPException(
    status_code=401,
    detail="Incorrect username or password",
    headers={"WWW-Authenticate": "Bearer"},
)

ERR_403 = HTTPException(
    status_code=403,
    detail="Not enough permissions",
    headers={"WWW-Authenticate": "Bearer"},
)
