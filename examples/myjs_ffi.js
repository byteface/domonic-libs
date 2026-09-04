// Run me with:  myjs examples/myjs_ffi.js
//
// JavaScript reaching straight into native C libraries through myjs's `ffi`
// global (Python ctypes under the hood -- no node-gyp, no C compiler).

const libc = ffi.loadLibrary("c");

// int abs(int)
libc.abs.argtypes = [ffi.types.int];
libc.abs.restype = ffi.types.int;
console.log("C  abs(-42)   =", libc.abs(-42));

// double sqrt(double), from libm
const libm = ffi.loadLibrary("m");
libm.sqrt.argtypes = [ffi.types.double];
libm.sqrt.restype = ffi.types.double;
console.log("C  sqrt(2)    =", libm.sqrt(2));

// mutate a C string buffer in place
const buf = ffi.createStringBuffer(64);
libc.strcpy.argtypes = [ffi.types.pointer, ffi.types.string];
libc.strcpy(buf, "written into C memory");
console.log("C  buffer     =", buf.value);

// wrap a JS function as a C callback pointer (CFUNCTYPE) -- pass this to any
// C API that takes a function pointer (qsort, signal, event hooks, ...)
const onTick = ffi.callback(ffi.types.int, [ffi.types.int], (n) => n * n);
console.log("C callback    =", typeof onTick);

// the DOM is here too -- myjs runs on domonic
const li = document.createElement("li");
li.textContent = "built from JS, on a real Python DOM tree";
document.body.appendChild(li);
console.log("DOM        =", String(document.body));

console.log("host       =", os.type(), os.arch(), "| python", os.python);
