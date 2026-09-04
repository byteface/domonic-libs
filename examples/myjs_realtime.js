// Real WebSockets, hand-rolled (RFC 6455), no dependencies.
//   myjs examples/myjs_realtime.js

const ws = new WebSocket("wss://ws.postman-echo.com/raw");

let sent = 0;
const messages = ["hello", "from", "myjs", "over", "a", "real", "socket"];

ws.onopen = () => {
  console.log("connected");
  const tick = setInterval(() => {
    if (sent >= messages.length) {
      clearInterval(tick);
      ws.close();
      return;
    }
    ws.send(messages[sent++]);
  }, 150);
};

ws.onmessage = (e) => console.log("  echo:", e.data);
ws.onclose = () => console.log("closed after", sent, "messages");
ws.onerror = (e) => console.log("error:", e.message);
