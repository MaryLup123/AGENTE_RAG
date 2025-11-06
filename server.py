from fastapi import FastAPI, UploadFile, File, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from typing import List
import os, time
from settings import CORPUS_DIR
from vectorstore import build_index
from agent import agent_query
from db import Base, engine, get_db
from models import User
from sqlalchemy.orm import Session
from auth import hash_password, verify_password, create_access_token, decode_token

app = FastAPI(title="UMG RAG Agent", version="1.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/", response_class=HTMLResponse)
async def home():
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

class RateLimiter:
    def __init__(self, max_per_minute: int):
        self.max = max_per_minute
        self.buckets = {}
    def allow(self, key: str) -> bool:
        now = int(time.time()); window = now // 60
        count, win = self.buckets.get(key, (0, window))
        if win != window: count, win = 0, window
        if count >= self.max:
            self.buckets[key] = (count, win); return False
        self.buckets[key] = (count + 1, win); return True

login_limiter = RateLimiter(10); ask_limiter = RateLimiter(60); upload_limiter=RateLimiter(30); ingest_limiter=RateLimiter(10)

def limit_login(request: Request):
    ip = request.client.host if request.client else "unknown"
    if not login_limiter.allow(ip):
        raise HTTPException(status_code=429, detail="Rate limit de login alcanzado. Intenta más tarde.")

def get_current_user(request: Request) -> dict:
    # allow missing token to show friendly error
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token requerido")
    token = auth.split(" ",1)[1]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido")
    return payload

def limit_ask(user_id: int):
    if not ask_limiter.allow(f"user:{user_id}"):
        raise HTTPException(status_code=429, detail="Rate limit de /ask alcanzado. Intenta más tarde.")

def limit_upload(user_id: int):
    if not upload_limiter.allow(f"userup:{user_id}"):
        raise HTTPException(status_code=429, detail="Rate limit de /upload alcanzado. Intenta más tarde.")

def limit_ingest(user_id: int):
    if not ingest_limiter.allow(f"uij:{user_id}"):
        raise HTTPException(status_code=429, detail="Rate limit de /ingest alcanzado. Intenta más tarde.")

@app.post("/auth/signup")
def signup(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form.username.lower().strip(); pw = form.password
    if len(pw) < 12: raise HTTPException(status_code=400, detail="Usa una contraseña de al menos 12 caracteres.")
    if len(pw) > 128: raise HTTPException(status_code=400, detail="La contraseña no debe exceder 128 caracteres.")
    if db.query(User).filter(User.email == email).first(): raise HTTPException(status_code=400, detail="Usuario ya existe")
    user = User(email=email, password_hash=hash_password(pw)); db.add(user); db.commit()
    return {"ok": True, "msg": "Usuario creado"}

@app.post("/auth/login")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    limit_login(request); email = form.username.lower().strip(); pw = form.password
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(pw, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    token = create_access_token({"sub": user.email, "uid": user.id, "role": user.role})
    return {"access_token": token, "token_type": "bearer", "role": user.role}

@app.post("/api/upload")
async def upload_files(request: Request, files: List[UploadFile] = File(...)):
    payload = get_current_user(request)
    limit_upload(payload["uid"])
    os.makedirs(CORPUS_DIR, exist_ok=True)
    saved = []
    for file in files:
        dest = os.path.join(CORPUS_DIR, file.filename)
        with open(dest, "wb") as out: out.write(await file.read())
        saved.append(file.filename)
    return {"ok": True, "saved": saved}

@app.post("/api/ingest")
async def ingest(request: Request):
    payload = get_current_user(request); limit_ingest(payload["uid"])
    count = build_index()
    return {"ok": True, "chunks_indexed": count}

@app.post("/api/ask")
async def ask(request: Request, payload_in: dict):
    payload = get_current_user(request); limit_ask(payload["uid"])
    try:
        q = payload_in.get("query", "").strip()
        if not q: return JSONResponse({"ok": False, "error": "Query vacío"}, status_code=400)
        from agent import agent_query
        ans = agent_query(q, user_id=payload["uid"])
        return {"ok": True, "answer": ans}
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)
