import jwt

KEY = "kjaisodognalksheighasdjgojasodigaosdg"
ALGORITHMS = "HS256"


def jwt_encode(text: dict):
    return jwt.encode(text, KEY, ALGORITHMS)


def jwt_decode(text: str):
    return jwt.decode(text, KEY, ALGORITHMS)
