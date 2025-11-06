import os, glob, uuid, logging
from typing import List, Dict
from tqdm import tqdm
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from settings import VECTOR_BACKEND, CHROMA_PATH, QDRANT_URL, QDRANT_COLLECTION_DOCS, QDRANT_COLLECTION_MEMORY, CORPUS_DIR, EMBEDDING_MODEL

logging.getLogger("chromadb").setLevel(logging.ERROR)

_EMB = None

def get_embedder():
    global _EMB
    if _EMB is None:
        _EMB = SentenceTransformer(EMBEDDING_MODEL)
    return _EMB

def load_documents():
    docs = []
    for path in glob.glob(os.path.join(CORPUS_DIR, '**/*'), recursive=True):
        if os.path.isdir(path): continue
        ext = os.path.splitext(path)[1].lower()
        txt = ""
        if ext in {'.txt','.md'}:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                txt = f.read()
        elif ext == '.pdf':
            try:
                reader = PdfReader(path)
                txt = '\n'.join([(p.extract_text() or '') for p in reader.pages])
            except Exception:
                continue
        if txt.strip():
            docs.append({'path': path, 'text': txt})
    return docs

def chunk_text(text, max_chars=3000, overlap=400):
    step = max_chars - overlap
    out, i = [], 0
    while i < len(text):
        ch = text[i:i+max_chars]
        if ch.strip(): out.append(ch)
        i += step
    return out

def _chroma_collection(name):
    import chromadb
    from chromadb.config import Settings
    client = chromadb.Client(Settings(is_persistent=True, persist_directory=CHROMA_PATH, anonymized_telemetry=False))
    names = [c.name for c in client.list_collections()]
    if name not in names:
        return client.create_collection(name=name, metadata={"hnsw:space":"cosine"})
    return client.get_collection(name)

def _qdrant_client():
    from qdrant_client import QdrantClient
    return QdrantClient(url=QDRANT_URL)

def _ensure_qdrant(name, dim):
    from qdrant_client.http.models import Distance, VectorParams
    c = _qdrant_client()
    cols = [x.name for x in c.get_collections().collections]
    if name not in cols:
        c.create_collection(collection_name=name, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))

def build_index():
    model = get_embedder()
    dim = model.get_sentence_embedding_dimension()
    if VECTOR_BACKEND == "qdrant":
        _ensure_qdrant(QDRANT_COLLECTION_DOCS, dim)
    else:
        _chroma_collection("docs")
    docs = load_documents()
    ids, texts, metas = [], [], []
    for d in tqdm(docs, desc="Indexando"):
        chunks = chunk_text(d['text'])
        for j, ch in enumerate(chunks):
            ids.append(f"{d['path']}::{j}")
            texts.append(ch)
            metas.append({"source": d['path'], "chunk": j})
    if not texts: return 0
    embeds = model.encode(texts, normalize_embeddings=True).tolist()
    if VECTOR_BACKEND == "qdrant":
        from qdrant_client.http.models import PointStruct
        c = _qdrant_client()
        pts = [PointStruct(id=uuid.uuid4().hex, vector=vec, payload={"id": idv, "text": doc, **meta})
               for idv, vec, meta, doc in zip(ids, embeds, metas, texts)]
        c.upsert(collection_name=QDRANT_COLLECTION_DOCS, points=pts)
    else:
        col = _chroma_collection("docs")
        col.add(ids=ids, documents=texts, embeddings=embeds, metadatas=metas)
    return len(texts)

def search_docs(query, k=5):
    m = get_embedder()
    qv = m.encode([query], normalize_embeddings=True).tolist()[0]
    if VECTOR_BACKEND == "qdrant":
        c = _qdrant_client()
        res = c.search(collection_name=QDRANT_COLLECTION_DOCS, query_vector=qv, limit=k)
        out = []
        for r in res:
            p = r.payload or {}
            out.append({"id": p.get("id", r.id), "text": p.get("text",""), "meta": {"source": p.get("source"), "chunk": p.get("chunk")}, "score": r.score})
        return out
    else:
        col = _chroma_collection("docs")
        try:
            total = col.count()
        except Exception:
            total = None
        nres = min(k, total) if total else k
        res = col.query(query_embeddings=[qv], n_results=nres, include=["documents","metadatas","distances"])
        out = []
        if res.get("ids"):
            for i in range(len(res["ids"][0])):
                out.append({"id": res["ids"][0][i], "text": res["documents"][0][i], "meta": res["metadatas"][0][i], "score": 1 - res["distances"][0][i]})
        return out

def _ensure_memory_ready():
    m = get_embedder()
    dim = m.get_sentence_embedding_dimension()
    if VECTOR_BACKEND == "qdrant":
        _ensure_qdrant(QDRANT_COLLECTION_MEMORY, dim)
    else:
        _chroma_collection("memory")

def add_memory(user_id: int, text: str):
    _ensure_memory_ready()
    m = get_embedder()
    v = m.encode([text], normalize_embeddings=True).tolist()[0]
    if VECTOR_BACKEND == "qdrant":
        from qdrant_client.http.models import PointStruct
        c = _qdrant_client()
        mid = uuid.uuid4().hex
        c.upsert(collection_name=QDRANT_COLLECTION_MEMORY, points=[PointStruct(id=mid, vector=v, payload={"user_id": user_id, "text": text})])
        return mid
    else:
        col = _chroma_collection("memory")
        mid = f"mem-{uuid.uuid4().hex}"
        col.add(ids=[mid], documents=[text], embeddings=[v], metadatas=[{"user_id": user_id}])
        return mid

def search_memory(user_id: int, query: str, k: int = 3):
    _ensure_memory_ready()
    m = get_embedder()
    qv = m.encode([query], normalize_embeddings=True).tolist()[0]
    if VECTOR_BACKEND == "qdrant":
        c = _qdrant_client()
        res = c.search(collection_name=QDRANT_COLLECTION_MEMORY, query_vector=qv, limit=k, query_filter={"must":[{"key":"user_id","match":{"value":user_id}}]})
        return [{"text": (r.payload or {}).get("text",""), "score": r.score} for r in res]
    else:
        col = _chroma_collection("memory")
        res = col.query(query_embeddings=[qv], n_results=k, include=["documents","metadatas","distances"], where={"user_id": user_id})
        out = []
        if res.get("ids"):
            for i in range(len(res["ids"][0])):
                out.append({"text": res["documents"][0][i], "score": 1 - res["distances"][0][i]})
        return out
