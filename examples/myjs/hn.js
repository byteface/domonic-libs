// Hacker News front page, in your terminal.
//   myjs examples/myjs/hn.js
//
// Live API + async/await + Promise.all for the concurrent story fetches.

const API = "https://hacker-news.firebaseio.com/v0";
const TOP_N = 10;

async function main() {
  const ids = (await (await fetch(`${API}/topstories.json`)).json()).slice(0, TOP_N);

  const stories = await Promise.all(
    ids.map(async (id) => (await (await fetch(`${API}/item/${id}.json`)).json()))
  );

  stories.forEach((s, i) => {
    const rank = String(i + 1).padStart(2);
    const host = s.url ? new URL(s.url).hostname.replace(/^www\./, "") : "news.ycombinator.com";
    console.log(`${rank}. ${s.title}`);
    console.log(`    ${s.score} points · ${s.descendants ?? 0} comments · ${host}`);
  });
}

main().catch((e) => console.error("failed:", e.message));
