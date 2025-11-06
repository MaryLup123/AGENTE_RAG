import re
from rag import rag_answer
from tools import tool_calculator
from vectorstore import add_memory

MATH_PATTERN = re.compile(r"^\s*calc:\s*(.+)$", re.IGNORECASE)

def agent_query(user_input: str, user_id: int = None) -> str:
    if user_id:
        add_memory(user_id, f"user: {user_input}")
    m = MATH_PATTERN.match(user_input)
    if m:
        expr = m.group(1)
        ans = f"🧮 Resultado: {tool_calculator(expr)}"
    else:
        ans = rag_answer(user_input, user_id=user_id, k_docs=5)
    if user_id:
        add_memory(user_id, f"assistant: {ans[:500]}")
    return ans
