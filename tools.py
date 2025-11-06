import math
def tool_calculator(expr: str) -> str:
    allowed = "0123456789+-*/(). "
    if any(ch not in allowed for ch in expr):
        return "Expresión no permitida."
    try:
        return str(eval(expr, {"__builtins__": {}}, {"math": math}))
    except Exception as e:
        return f"Error: {e}"
