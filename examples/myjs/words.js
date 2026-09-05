// Text processing: fetch a book, count words, show the top 15.
//   myjs examples/myjs/words.js

const STOP = new Set(("the of and to a in that is was he for it with as his on be at by "
  + "i this had not are but from or have an they which one you were her all she there would "
  + "their we him been has when who will no more if out so said what up its about into than them")
  .split(" "));

async function main() {
  // Frankenstein, from Project Gutenberg
  const res = await fetch("https://www.gutenberg.org/files/84/84-0.txt");
  const text = res.text();

  const counts = new Map();
  for (const w of text.toLowerCase().match(/[a-z']{3,}/g) || []) {
    if (STOP.has(w)) continue;
    counts.set(w, (counts.get(w) || 0) + 1);
  }

  const top = [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 15)
    .map(([word, n]) => ({ word, count: n }));

  console.log(`${counts.size.toLocaleString?.() ?? counts.size} distinct words. Top 15:`);
  console.table(top);
}

main().catch((e) => console.error(e.message));
