from reminis import compute, Proc

# On the first run, each function will print some output, showing that it was computed during that run
# On subsequent runs, if the arguments did not change, nothing will print, since none of the functions are executed.
# Instead, the output of the last processor (the second add) is simply loaded from file and returned.

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
    Proc(square),
    Proc(mul, dependencies=["adder", "square"]),
    Proc(add, dependencies=[-1, "square"])
])

print(result) # 392