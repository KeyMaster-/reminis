from reminis import compute, Proc
def add(a, b):
    print('add')
    return a + b

def square(a):
    print('square')
    return a ** 2

def mul(a, b):
    print('mul')
    return a * b

result = compute([
    Proc(add, [2,5], "adder"),
    Proc(square, []),
    Proc(mul, dependencies=["adder", "square"]),
    Proc(add, dependencies=[-1, "square"])
])

print(result)