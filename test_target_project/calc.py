# calc.py

def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    # Multiply two numbers and return the result
    return a * b

def divide(a, b):
    if b == 0:
        raise ValueError("Division by zero is not allowed.")
    return a / b