"""Calculator / Math Calculation tool.

Evaluates mathematical expressions, percentages, powers, roots, and standard
arithmetic securely using an AST parser (preventing arbitrary code execution).
"""

from __future__ import annotations

import ast
import logging
import math
import operator
import re
from tools.base import ParamSpec, Risk, Tool, ToolResult

logger = logging.getLogger(__name__)

SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

SAFE_FUNCS = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "abs": abs,
    "round": round,
    "ceil": math.ceil,
    "floor": math.floor,
    "factorial": math.factorial,
}

SAFE_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
}


def _eval_ast(node):
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body)
    elif isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise ValueError(f"Unsupported constant type: {type(node.value)}")
        return node.value
    elif isinstance(node, ast.Name):
        if node.id in SAFE_CONSTANTS:
            return SAFE_CONSTANTS[node.id]
        raise ValueError(f"Unknown symbol: {node.id}")
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in SAFE_OPS:
            raise ValueError(f"Unsupported operation: {op_type}")
        left = _eval_ast(node.left)
        right = _eval_ast(node.right)
        # Prevent huge exponentiation that could freeze CPU
        if op_type is ast.Pow and right > 1000:
            raise ValueError("Exponent too large")
        return SAFE_OPS[op_type](left, right)
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in SAFE_OPS:
            raise ValueError(f"Unsupported unary operator: {op_type}")
        return SAFE_OPS[op_type](_eval_ast(node.operand))
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in SAFE_FUNCS:
            raise ValueError("Unsupported function call")
        func = SAFE_FUNCS[node.func.id]
        args = [_eval_ast(arg) for arg in node.args]
        return func(*args)
    else:
        raise ValueError(f"Unsupported expression element: {type(node)}")


def normalize_expression(text: str) -> str:
    """Translate natural-language math queries into standard arithmetic expressions."""
    s = text.lower().strip()
    s = re.sub(r"^(?:calculate|compute|solve|eval|evaluate|what is|what\'s|how much is)\s+", "", s).strip()
    s = s.rstrip("=? .")

    # Percentage: '15% of 200' or '15 percent of 200'
    s = re.sub(r"(\d+(?:\.\d+)?)\s*(?:%|percent)\s+of\s+(\d+(?:\.\d+)?)", r"(\1 / 100) * \2", s)

    # Square roots
    s = re.sub(r"square root of\s+(\d+(?:\.\d+)?)", r"sqrt(\1)", s)
    s = re.sub(r"sqrt of\s+(\d+(?:\.\d+)?)", r"sqrt(\1)", s)

    # Common spoken phrases
    replacements = [
        (r"\bmultiplied by\b", "*"),
        (r"\btimes\b", "*"),
        (r"\binto\b", "*"),
        (r"\bdivided by\b", "/"),
        (r"\bover\b", "/"),
        (r"\bplus\b", "+"),
        (r"\bminus\b", "-"),
        (r"\bto the power of\b", "**"),
        (r"\bsquared\b", "** 2"),
        (r"\bcubed\b", "** 3"),
        (r"\^", "**"),
        (r"\bx\b", "*"),
    ]
    for pattern, rep in replacements:
        s = re.sub(pattern, rep, s)

    return s.strip()


class CalculatorTool(Tool):
    name = "calculator"
    description = "Perform mathematical calculations, arithmetic, percentages, powers, roots, and unit conversions."
    risk = Risk.LOW
    params = (
        ParamSpec("expression", "The mathematical expression or question (e.g. '25 * 40', '15% of 300', 'sqrt(144)')"),
    )

    def run(self, expression: str = "", **kwargs) -> ToolResult:
        raw_expr = (expression or "").strip()
        if not raw_expr:
            return ToolResult.failure("Please provide a mathematical expression to calculate.")

        cleaned = normalize_expression(raw_expr)
        if not cleaned:
            return ToolResult.failure("Could not parse the mathematical expression.")

        try:
            tree = ast.parse(cleaned, mode="eval")
            result = _eval_ast(tree)

            # Clean formatting
            if isinstance(result, float) and result.is_integer():
                result = int(result)

            if isinstance(result, float):
                # Format with up to 4 decimal places without trailing zeros
                formatted = f"{result:,.4f}".rstrip("0").rstrip(".")
            else:
                formatted = f"{result:,}"

            spoken = f"{raw_expr.rstrip('=? ')} = {formatted}"
            return ToolResult.success(spoken, expression=raw_expr, cleaned=cleaned, result=result, formatted=formatted)

        except ZeroDivisionError:
            return ToolResult.failure("Division by zero is undefined.")
        except Exception as e:
            logger.warning("Calculation error: %s", e)
            return ToolResult.failure(f"I couldn't calculate that: {e}")

