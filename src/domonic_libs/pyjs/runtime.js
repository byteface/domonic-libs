// pyjs runtime -- the Python semantics `dlx pyjs` output leans on.
// Prepended (minified) to a transpiled module unless --no-runtime.
var __py = (function () {
  var slice = Array.prototype.slice;

  function truthy(x) {
    if (x === null || x === undefined || x === false) return false;
    if (x === 0 || x === "") return false;
    if (Array.isArray(x)) return x.length !== 0;
    if (x instanceof Map || x instanceof Set) return x.size !== 0;
    if (typeof x === "object") return Object.keys(x).length !== 0;
    return !!x;
  }

  function range(a, b, step) {
    if (b === undefined) { b = a; a = 0; }
    step = step === undefined ? 1 : step;
    var out = [];
    if (step > 0) for (var i = a; i < b; i += step) out.push(i);
    else for (var i = a; i > b; i += step) out.push(i);
    return out;
  }

  function len(x) {
    if (x === null || x === undefined) throw new TypeError("object has no len()");
    if (typeof x === "string" || Array.isArray(x)) return x.length;
    if (x instanceof Map || x instanceof Set) return x.size;
    if (typeof x.length === "number") return x.length;
    return Object.keys(x).length;
  }

  function str(x) {
    if (x === null || x === undefined) return "None";
    if (x === true) return "True";
    if (x === false) return "False";
    if (Array.isArray(x)) return "[" + x.map(repr).join(", ") + "]";
    if (x instanceof Map)
      return "{" + Array.from(x.entries()).map(function (e) { return repr(e[0]) + ": " + repr(e[1]); }).join(", ") + "}";
    if (x instanceof Set)
      return "{" + Array.from(x.values()).map(repr).join(", ") + "}";
    if (x instanceof Error) return String(x);
    var proto = Object.getPrototypeOf(x);
    if (typeof x === "object" && (proto === null || proto === Object.prototype))
      return "{" + Object.keys(x).map(function (k) { return _key(k) + ": " + repr(x[k]); }).join(", ") + "}";
    return String(x);
  }
  function repr(x) {
    if (typeof x === "string") return "'" + x.replace(/\\/g, "\\\\").replace(/'/g, "\\'") + "'";
    return str(x);
  }
  // a dict key: JS objects stringify every key, so an all-digits key came
  // from a Python number and prints back without quotes.
  function _key(k) { return /^-?\d+$/.test(k) ? k : repr(k); }

  function print() {
    console.log(Array.prototype.slice.call(arguments).map(str).join(" "));
  }

  function iter(x) {
    if (Array.isArray(x) || typeof x === "string") return x;
    if (x instanceof Map) return Array.from(x.keys());
    if (x instanceof Set) return Array.from(x.values());
    if (x && typeof x.next === "function") {   // a generator / iterator -- drain it
      var out = [], step;
      while (!(step = x.next()).done) out.push(step.value);
      return out;
    }
    if (x && typeof x[Symbol.iterator] === "function") return Array.from(x);
    if (x && typeof x === "object") return Object.keys(x);
    return x;
  }
  function list(x) { return x === undefined ? [] : Array.from(iter(x)); }
  function tuple(x) { return list(x); }

  function enumerate(x, start) {
    start = start || 0;
    return list(x).map(function (v, i) { return [i + start, v]; });
  }
  function zip() {
    var cols = Array.prototype.slice.call(arguments).map(list);
    var n = Math.min.apply(null, cols.map(function (c) { return c.length; }));
    var out = [];
    for (var i = 0; i < n; i++) out.push(cols.map(function (c) { return c[i]; }));
    return out;
  }
  function sorted(x, opts) {
    opts = opts || {};
    var a = list(x).slice();
    var key = opts.key || function (v) { return v; };
    a.sort(function (p, q) { var kp = key(p), kq = key(q); return kp < kq ? -1 : kp > kq ? 1 : 0; });
    if (opts.reverse) a.reverse();
    return a;
  }
  function sum(x, start) { return list(x).reduce(function (a, b) { return a + b; }, start || 0); }
  function min_() { return _mm(arguments, function (a, b) { return a < b; }); }
  function max_() { return _mm(arguments, function (a, b) { return a > b; }); }
  function _mm(args, better) {
    var seq = args.length === 1 ? list(args[0]) : Array.from(args);
    return seq.reduce(function (a, b) { return better(b, a) ? b : a; });
  }
  function abs_(x) { return Math.abs(x); }
  function round_(x, n) { var f = Math.pow(10, n || 0); return Math.round(x * f) / f; }

  function contains(needle, hay) {
    if (typeof hay === "string") return hay.indexOf(needle) !== -1;
    if (Array.isArray(hay)) return hay.some(function (x) { return eq(x, needle); });
    if (hay instanceof Map || hay instanceof Set) return hay.has(needle);
    if (hay && typeof hay === "object") return Object.prototype.hasOwnProperty.call(hay, needle);
    return false;
  }

  function getitem(obj, key) {
    if ((Array.isArray(obj) || typeof obj === "string") && key < 0) key += obj.length;
    if (obj instanceof Map) return obj.get(key);
    var v = obj[key];
    if (v === undefined && !(key in Object(obj))) throw new Error("KeyError: " + str(key));
    return v;
  }
  function setitem(obj, key, val) {
    if (Array.isArray(obj) && key < 0) key += obj.length;
    if (obj instanceof Map) { obj.set(key, val); return val; }
    obj[key] = val; return val;
  }
  function slice_(obj, lo, hi, step) {
    var a = typeof obj === "string" ? obj : list(obj);
    var n = a.length;
    lo = lo == null ? (step < 0 ? n - 1 : 0) : lo < 0 ? lo + n : lo;
    hi = hi == null ? (step < 0 ? -1 : n) : hi < 0 ? hi + n : hi;
    step = step || 1;
    var out = [];
    if (step > 0) for (var i = lo; i < hi; i += step) out.push(a[i]);
    else for (var i = lo; i > hi; i += step) out.push(a[i]);
    return typeof obj === "string" ? out.join("") : out;
  }

  function floordiv(a, b) { return Math.floor(a / b); }
  function mul(a, b) {   // Python `*`: sequence repetition when one side is a seq
    var seq = Array.isArray(a) || typeof a === "string" ? a : b;
    var n = seq === a ? b : a;
    if (Array.isArray(seq)) {
      var out = [];
      for (var i = 0; i < n; i++) for (var k = 0; k < seq.length; k++) out.push(seq[k]);
      return out;
    }
    if (typeof seq === "string") { var s = ""; for (var j = 0; j < n; j++) s += seq; return s; }
    return a * b;
  }
  function mod(a, b) {   // Python %: result takes the sign of the divisor
    var r = a % b;
    return r !== 0 && (r < 0) !== (b < 0) ? r + b : r;
  }

  // -- Python comparison: element-wise on lists/tuples/dicts ---------------
  function _isplain(x) {
    if (!x || typeof x !== "object" || Array.isArray(x)) return false;
    var p = Object.getPrototypeOf(x);
    return p === Object.prototype || p === null;
  }
  function _cmp(a, b) {
    if (Array.isArray(a) && Array.isArray(b)) {
      var n = Math.min(a.length, b.length);
      for (var i = 0; i < n; i++) { var c = _cmp(a[i], b[i]); if (c) return c; }
      return a.length - b.length;
    }
    return a < b ? -1 : a > b ? 1 : 0;
  }
  function eq(a, b) {
    if (a === b) return true;
    if (Array.isArray(a) && Array.isArray(b)) {
      if (a.length !== b.length) return false;
      for (var i = 0; i < a.length; i++) if (!eq(a[i], b[i])) return false;
      return true;
    }
    if (a instanceof Map && b instanceof Map) {
      if (a.size !== b.size) return false;
      var it = a.entries(), s;
      while (!(s = it.next()).done) if (!b.has(s.value[0]) || !eq(s.value[1], b.get(s.value[0]))) return false;
      return true;
    }
    if (_isplain(a) && _isplain(b)) {
      var ka = Object.keys(a);
      if (ka.length !== Object.keys(b).length) return false;
      return ka.every(function (k) {
        return Object.prototype.hasOwnProperty.call(b, k) && eq(a[k], b[k]);
      });
    }
    return false;
  }
  function ne(a, b) { return !eq(a, b); }
  function lt(a, b) { return _cmp(a, b) < 0; }
  function le(a, b) { return _cmp(a, b) <= 0; }
  function gt(a, b) { return _cmp(a, b) > 0; }
  function ge(a, b) { return _cmp(a, b) >= 0; }

  // -- numeric builtins --------------------------------------------------
  function chr(n) { return String.fromCodePoint(n); }
  function ord(s) { return s.codePointAt(0); }
  function _based(n, base, tag) {
    return (n < 0 ? "-" + tag + (-n).toString(base) : tag + n.toString(base));
  }
  function hex(n) { return _based(Math.trunc(n), 16, "0x"); }
  function oct(n) { return _based(Math.trunc(n), 8, "0o"); }
  function bin(n) { return _based(Math.trunc(n), 2, "0b"); }
  function divmod(a, b) { return [floordiv(a, b), mod(a, b)]; }
  function reversed(x) { return list(x).slice().reverse(); }
  function minby(seq, keyfn, dflt) { return _mmby(seq, keyfn, dflt, -1); }
  function maxby(seq, keyfn, dflt) { return _mmby(seq, keyfn, dflt, 1); }
  function _mmby(seq, keyfn, dflt, dir) {
    var a = list(seq);
    if (!a.length) {
      if (dflt !== undefined) return dflt;
      throw new Error("ValueError: arg is an empty sequence");
    }
    keyfn = keyfn || function (x) { return x; };
    var best = a[0], bk = keyfn(a[0]);
    for (var i = 1; i < a.length; i++) {
      var k = keyfn(a[i]);
      if (_cmp(k, bk) * dir > 0) { best = a[i]; bk = k; }
    }
    return best;
  }

  // -- list / dict / set / str methods (polymorphic in the receiver) -----
  function _native(o, name, args) {   // fall through to a real method (DOM etc.)
    if (o != null && typeof o[name] === "function") return o[name].apply(o, args);
    throw new TypeError("object has no method '" + name + "'");
  }
  function extend(a, b) { list(b).forEach(function (x) { a.push(x); }); }
  function insert(a, i, x) { a.splice(i < 0 ? Math.max(0, a.length + i) : i, 0, x); }
  function sort(a, opts) {
    opts = opts || {};
    var key = opts.key || function (v) { return v; };
    a.sort(function (p, q) { return _cmp(key(p), key(q)); });
    if (opts.reverse) a.reverse();
  }
  function count(o, x) {
    if (typeof o === "string") {
      if (x === "") return o.length + 1;
      var n = 0, i = 0;
      while ((i = o.indexOf(x, i)) !== -1) { n++; i += x.length; }
      return n;
    }
    return list(o).filter(function (v) { return eq(v, x); }).length;
  }
  function index(o, x) {
    var i = typeof o === "string" ? o.indexOf(x)
                                  : list(o).findIndex(function (v) { return eq(v, x); });
    if (i === -1) throw new Error("ValueError: " + str(x) + " is not in " + (typeof o === "string" ? "string" : "list"));
    return i;
  }
  function remove(o, x) {
    if (Array.isArray(o)) { o.splice(index(o, x), 1); return; }
    if (o instanceof Set) { if (!o.delete(x)) throw new Error("KeyError: " + str(x)); return; }
    return _native(o, "remove", [x]);
  }
  function add(o, x) {
    if (o instanceof Set) { o.add(x); return; }
    return _native(o, "add", [x]);
  }
  function discard(o, x) { if (o instanceof Set) o.delete(x); else _native(o, "discard", [x]); }
  function pop(o, a, b) {
    if (Array.isArray(o)) {
      var i = a === undefined ? o.length - 1 : (a < 0 ? o.length + a : a);
      if (i < 0 || i >= o.length) throw new Error("IndexError: pop index out of range");
      return o.splice(i, 1)[0];
    }
    if (o instanceof Map) {
      if (o.has(a)) { var v = o.get(a); o.delete(a); return v; }
      if (b !== undefined) return b;
      throw new Error("KeyError: " + str(a));
    }
    if (o instanceof Set) return _native(o, "pop", []);
    if (_isplain(o)) {
      if (Object.prototype.hasOwnProperty.call(o, a)) { var w = o[a]; delete o[a]; return w; }
      if (b !== undefined) return b;
      throw new Error("KeyError: " + str(a));
    }
    return _native(o, "pop", [].slice.call(arguments, 1));
  }
  function popitem(o) {
    var ks = keys(o); if (!ks.length) throw new Error("KeyError: dictionary is empty");
    var k = ks[ks.length - 1], v = get(o, k); pop(o, k); return [k, v];
  }
  function setdefault(o, k, dflt) {
    dflt = dflt === undefined ? null : dflt;
    if (o instanceof Map) { if (!o.has(k)) o.set(k, dflt); return o.get(k); }
    if (!Object.prototype.hasOwnProperty.call(o, k)) o[k] = dflt;
    return o[k];
  }
  function update(o, other) {
    if (other == null) return;
    if (o instanceof Map) {
      items(other).forEach(function (e) { o.set(e[0], e[1]); });
    } else {
      items(other).forEach(function (e) { o[e[0]] = e[1]; });
    }
  }
  function copy(o) {
    if (Array.isArray(o)) return o.slice();
    if (o instanceof Map) return new Map(o);
    if (o instanceof Set) return new Set(o);
    if (_isplain(o)) { var d = {}; Object.keys(o).forEach(function (k) { d[k] = o[k]; }); return d; }
    return _native(o, "copy", []);
  }
  function clear(o) {
    if (Array.isArray(o)) { o.length = 0; return; }
    if (o instanceof Map || o instanceof Set) { o.clear(); return; }
    if (_isplain(o)) { Object.keys(o).forEach(function (k) { delete o[k]; }); return; }
    return _native(o, "clear", []);
  }
  function _asArr(x) { return x instanceof Set ? Array.from(x) : list(x); }
  function union(a, b) { return new Set(_asArr(a).concat(_asArr(b))); }
  function intersection(a, b) {
    var o = new Set(_asArr(b));
    return new Set(_asArr(a).filter(function (x) { return o.has(x); }));
  }
  function difference(a, b) {
    var o = new Set(_asArr(b));
    return new Set(_asArr(a).filter(function (x) { return !o.has(x); }));
  }
  function symmetric_difference(a, b) { return union(difference(a, b), difference(b, a)); }
  function issubset(a, b) {
    var o = new Set(_asArr(b));
    return _asArr(a).every(function (x) { return o.has(x); });
  }
  function issuperset(a, b) { return issubset(b, a); }

  // -- str methods ------------------------------------------------------
  var _WS = /\s+/;
  function split(s, sep, maxsplit) {
    if (sep === undefined || sep === null) return s.trim() === "" ? [] : s.trim().split(_WS);
    if (maxsplit === undefined || maxsplit < 0) return s.split(sep);
    var out = [], i = 0, n = 0;
    while (n < maxsplit) { var j = s.indexOf(sep, i); if (j === -1) break; out.push(s.slice(i, j)); i = j + sep.length; n++; }
    out.push(s.slice(i));
    return out;
  }
  function replace(s, a, b, n) {
    if (n === undefined || n < 0) return s.split(a).join(b);
    var out = "", i = 0;
    while (n-- > 0) { var j = s.indexOf(a, i); if (j === -1) break; out += s.slice(i, j) + b; i = j + a.length; }
    return out + s.slice(i);
  }
  function strip(s, chars, side) {   // side: -1 left, 0 both, 1 right
    var set = {}; for (var i = 0; i < chars.length; i++) set[chars[i]] = 1;
    var lo = 0, hi = s.length;
    if (side <= 0) while (lo < hi && set[s[lo]]) lo++;
    if (side >= 0) while (hi > lo && set[s[hi - 1]]) hi--;
    return s.slice(lo, hi);
  }
  function title(s) { return s.replace(/[A-Za-z]+/g, function (w) { return w[0].toUpperCase() + w.slice(1).toLowerCase(); }); }
  function capitalize(s) { return s ? s[0].toUpperCase() + s.slice(1).toLowerCase() : s; }
  function swapcase(s) {
    return s.replace(/[a-zA-Z]/g, function (c) { return c === c.toLowerCase() ? c.toUpperCase() : c.toLowerCase(); });
  }
  function zfill(s, w) {
    s = String(s);
    var neg = s[0] === "-" || s[0] === "+" ? s[0] : "";
    var body = neg ? s.slice(1) : s;
    return neg + _rep("0", w - s.length) + body;
  }
  function center(s, w, ch) {
    ch = ch || " ";
    var pad = w - s.length; if (pad <= 0) return s;
    var l = pad >> 1;
    return _rep(ch, l) + s + _rep(ch, pad - l);
  }
  function splitlines(s, keepends) {
    var parts = s.split(/(\r\n|\r|\n)/), out = [];
    for (var i = 0; i < parts.length; i += 2) {
      if (parts[i] === "" && i + 1 >= parts.length) break;
      out.push(keepends ? parts[i] + (parts[i + 1] || "") : parts[i]);
    }
    return out;
  }
  function removeprefix(s, p) { return s.slice(0, p.length) === p ? s.slice(p.length) : s; }
  function removesuffix(s, p) { return p && s.slice(-p.length) === p ? s.slice(0, -p.length) : s; }
  function _all(s, re) { return s.length > 0 && re.test(s); }
  function isdigit(s) { return _all(s, /^[0-9]+$/); }
  function isalpha(s) { return _all(s, /^[A-Za-z]+$/); }
  function isalnum(s) { return _all(s, /^[A-Za-z0-9]+$/); }
  function isspace(s) { return _all(s, /^\s+$/); }
  function isupper(s) { return /[A-Z]/.test(s) && s === s.toUpperCase(); }
  function islower(s) { return /[a-z]/.test(s) && s === s.toLowerCase(); }
  function _rep(ch, n) { var s = ""; while (n-- > 0) s += ch; return s; }

  // -- format() : the f-string ":spec" mini-language --------------------
  function format(val, spec) {
    spec = spec == null ? "" : String(spec);
    if (!spec) return str(val);
    var m = spec.match(/^(?:(.)?([<>^=]))?([+\- ])?(#)?(0)?(\d+)?(,|_)?(?:\.(\d+))?([bcdeEfFgGnosxX%])?$/);
    if (!m) return str(val);
    var zero = m[5], fill = m[1] || (zero ? "0" : " "), align = m[2] || (zero ? "=" : null);
    var sign = m[3] || "-", alt = m[4], width = m[6] ? +m[6] : 0;
    var grp = m[7], prec = m[8] ? +m[8] : null, type = m[9] || "";
    var isNum = typeof val === "number", body, radix = "";
    if (type === "%") { val = val * 100; }
    if (type === "f" || type === "F") {
      body = Math.abs(val).toFixed(prec == null ? 6 : prec);
    } else if (type === "%") {
      body = Math.abs(val).toFixed(prec == null ? 6 : prec) + "%";
    } else if (type === "e" || type === "E") {
      body = Math.abs(val).toExponential(prec == null ? 6 : prec)
        .replace(/e([+-])(\d)$/, "e$10$2");        // Python pads the exponent to 2
      if (type === "E") body = body.toUpperCase();
    } else if (type === "d" || type === "n") {
      body = String(Math.abs(Math.round(val)));
    } else if (type === "x" || type === "X" || type === "o" || type === "b") {
      body = Math.abs(Math.trunc(val)).toString({ x: 16, X: 16, o: 8, b: 2 }[type]);
      if (type === "X") body = body.toUpperCase();
      if (alt) radix = { x: "0x", X: "0X", o: "0o", b: "0b" }[type];
    } else if (type === "g" || type === "G") {
      body = String(prec == null ? Math.abs(val) : +Math.abs(val).toPrecision(prec));
    } else if (type === "c") {
      return String.fromCodePoint(val);
    } else if (type === "" && isNum) {
      body = String(Math.abs(val));
    } else {
      body = str(val);
      if (prec != null) body = body.slice(0, prec);
      isNum = false;
    }
    if (grp && isNum) {
      var pt = body.indexOf("."), gi = grp === "_" ? "_" : ",";
      var ip = pt < 0 ? body : body.slice(0, pt), fp = pt < 0 ? "" : body.slice(pt);
      body = ip.replace(/\B(?=(\d{3})+(?!\d))/g, gi) + fp;
    }
    var prefix = "";
    if (isNum) prefix = (val < 0 ? "-" : sign === "+" ? "+" : sign === " " ? " " : "") + radix;
    var pad = width - prefix.length - body.length;
    if (pad <= 0) return prefix + body;
    if (align === "=" || (align == null && zero && isNum)) return prefix + _rep(fill, pad) + body;
    if (align === ">" || (align == null && isNum)) return _rep(fill, pad) + prefix + body;
    if (align === "^") { var l = pad >> 1; return _rep(fill, l) + prefix + body + _rep(fill, pad - l); }
    return prefix + body + _rep(fill, pad);
  }

  // random.* -- Math.random() underneath, Python's signatures on top
  function randint(a, b) { return a + Math.floor(Math.random() * (b - a + 1)); }
  function uniform(a, b) { return a + Math.random() * (b - a); }
  function randrange(a, b, step) {
    if (b === undefined) { b = a; a = 0; }
    step = step || 1;
    return a + step * Math.floor(Math.random() * Math.ceil((b - a) / step));
  }
  function choice(seq) { seq = list(seq); return seq[Math.floor(Math.random() * seq.length)]; }
  function shuffle(a) {
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1)), t = a[i];
      a[i] = a[j]; a[j] = t;
    }
    return a;
  }
  function isinstance(x, cls) {
    if (Array.isArray(cls)) return cls.some(function (c) { return isinstance(x, c); });
    if (cls === Number || cls === __py.int || cls === __py.float) return typeof x === "number";
    if (cls === String || cls === __py.str) return typeof x === "string";
    if (cls === Boolean || cls === __py.bool) return typeof x === "boolean";
    if (cls === Array || cls === __py.list) return Array.isArray(x);
    if (cls === Object || cls === __py.dict) return x && typeof x === "object" && !Array.isArray(x);
    return x instanceof cls;
  }

  // dict/list method shims used when a `.method()` needs Python semantics
  function items(d) {
    if (d instanceof Map) return Array.from(d.entries());
    return Object.keys(d).map(function (k) { return [k, d[k]]; });
  }
  function keys(d) { return d instanceof Map ? Array.from(d.keys()) : Object.keys(d); }
  function values(d) { return d instanceof Map ? Array.from(d.values()) : Object.keys(d).map(function (k) { return d[k]; }); }
  function get(d, k, dflt) {
    var v = d instanceof Map ? d.get(k) : d[k];
    return v === undefined ? (dflt === undefined ? null : dflt) : v;
  }
  function fmt(spec) {
    var args = Array.prototype.slice.call(arguments, 1);
    var i = 0;
    return spec.replace(/\{\}/g, function () { return str(args[i++]); })
              .replace(/\{(\d+)\}/g, function (_, d) { return str(args[+d]); });
  }

  return {
    truthy: truthy, bool: truthy, range: range, len: len, str: str, repr: repr,
    print: print, iter: iter, list: list, tuple: tuple, enumerate: enumerate,
    zip: zip, sorted: sorted, sum: sum, min: min_, max: max_, abs: abs_,
    round: round_, contains: contains, getitem: getitem, setitem: setitem,
    slice: slice_, floordiv: floordiv, mod: mod, mul: mul, isinstance: isinstance,
    randint: randint, uniform: uniform, randrange: randrange,
    choice: choice, shuffle: shuffle,
    items: items, keys: keys, values: values, get: get, fmt: fmt, format: format,
    eq: eq, ne: ne, lt: lt, le: le, gt: gt, ge: ge,
    chr: chr, ord: ord, hex: hex, oct: oct, bin: bin, divmod: divmod,
    reversed: reversed, minby: minby, maxby: maxby,
    extend: extend, insert: insert, sort: sort, count: count, index: index,
    remove: remove, add: add, discard: discard, pop: pop, popitem: popitem,
    setdefault: setdefault, update: update, copy: copy, clear: clear,
    union: union, intersection: intersection, difference: difference,
    symmetric_difference: symmetric_difference, issubset: issubset, issuperset: issuperset,
    split: split, replace: replace, strip: strip, title: title,
    capitalize: capitalize, swapcase: swapcase, zfill: zfill, center: center,
    splitlines: splitlines, removeprefix: removeprefix, removesuffix: removesuffix,
    isdigit: isdigit, isalpha: isalpha, isalnum: isalnum, isspace: isspace,
    isupper: isupper, islower: islower,
    int: function (x) { return typeof x === "string" ? parseInt(x, 10) : Math.trunc(x); },
    float: function (x) { return parseFloat(x); },
    dict: Object, set: Set,
  };
})();
