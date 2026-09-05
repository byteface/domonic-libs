// A plain JS module -- see from_python.py, which imports and calls this
// directly from a .py file, no CLI, no subprocess.
export function greet(name) {
  return `Hello, ${name}! (built by a real JS function, called from Python)`;
}

export function fibonacci(n) {
  let a = 0, b = 1;
  for (let i = 0; i < n; i++) [a, b] = [b, a + b];
  return a;
}

export const VERSION = "1.0";
