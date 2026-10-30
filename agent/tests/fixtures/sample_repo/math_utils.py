def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def divide(a: float, b: float) -> float:
    """Divide a by b."""
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return a / b
