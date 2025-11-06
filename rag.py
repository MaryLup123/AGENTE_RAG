from settings import LLM_BACKEND, LLM_MODEL, OPENAI_MODEL
from vectorstore import search_docs, search_memory

def llm_generate(prompt: str, retries: int = 4, delay: int = 2) -> str:
    if LLM_BACKEND == "ollama":
        import ollama, time
        import httpx
        last = None
        for i in range(retries):
            try:
                r = ollama.chat(model=LLM_MODEL, messages=[{"role":"user","content":prompt}])
                return r["message"]["content"]
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                last = e
                time.sleep(delay * (i+1))
        raise RuntimeError(f"Ollama no responde: {last}")
    else:
        from openai import OpenAI
        import os
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        r = client.chat.completions.create(model=OPENAI_MODEL, messages=[{"role":"user","content":prompt}], temperature=0.2)
        return r.choices[0].message.content

RAG_SYSTEM = """Eres un asistente experto. Responde SÓLO con base en el CONTEXTO si es relevante.
- Si no está en el contexto, dilo con claridad.
- Cita fuentes como [#i] para documentos.
- Usa [M] para recuerdos relevantes del usuario.
- Sé claro y conciso.
"""

def build_context(query: str, user_id: int, k_docs=5, k_mem=3):
    docs = search_docs(query, k=k_docs)
    mems = search_memory(user_id, query, k=k_mem) if user_id else []
    ctx = ""
    for i, d in enumerate(docs, 1):
        src = d.get("meta",{}).get("source","desconocido")
        ctx += f"\n[#{i}] Fuente: {src}\n{d['text']}\n"
    if mems:
        ctx += "\n[M] Recuerdos del usuario:\n"
        for m in mems:
            ctx += f"- {m['text']}\n"
    return ctx.strip()

def rag_answer(query: str, user_id: int = None, k_docs: int = 5) -> str:
    ctx = build_context(query, user_id=user_id, k_docs=k_docs, k_mem=3)
    prompt = f"""{RAG_SYSTEM}
PREGUNTA: {query}
CONTEXTO:
{ctx or '(sin resultados relevantes)'} 
Instrucciones:
1) Si hay respuesta en el contexto, respóndela y cita las [#].
2) Si no, di que no está y sugiere pasos siguientes.
"""
    return llm_generate(prompt)
