// The raw uname(2) syscall via ffi -- no os module, no platform module, just
// a byte buffer handed straight to libc and read back field by field.
//   myjs examples/myjs/syscall.js

const libc = ffi.loadLibrary("c");
const FIELD = 256;                          // struct utsname field width (BSD/Darwin, and Linux)
const buf = ffi.createStringBuffer(FIELD * 5);

const rc = libc.uname(buf);
if (rc !== 0) throw new Error(`uname() failed, errno ${ffi.errno()}`);

// struct utsname { char sysname[256], nodename[256], release[256], version[256], machine[256]; }
function field(index) {
  let s = "";
  const start = index * FIELD;
  for (let i = 0; i < FIELD; i++) {
    const byte = buf.raw[start + i];
    if (byte === 0) break;
    s += String.fromCharCode(byte);
  }
  return s;
}

console.log("Straight from the kernel, via a raw C struct -- not Python's platform module:\n");
console.log(`sysname   ${field(0)}`);
console.log(`nodename  ${field(1)}`);
console.log(`release   ${field(2)}`);
console.log(`version   ${field(3)}`);
console.log(`machine   ${field(4)}`);

// bonus: getpid(2) and getuid(2), also called directly, no os.getpid() wrapper
console.log(`\npid ${libc.getpid()}, uid ${libc.getuid()} -- via libc.getpid()/libc.getuid() directly`);
