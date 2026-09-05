// SQL from JavaScript -- an in-memory SQLite database via the `py` bridge.
//   myjs examples/myjs/sqlite.js

const sqlite3 = py.import("sqlite3");
const db = sqlite3.connect(":memory:");

db.executescript(`
  CREATE TABLE commits (author TEXT, files INTEGER, added INTEGER);
  INSERT INTO commits VALUES
    ('ada',   3, 120), ('ada',   1, 14),
    ('grace', 7, 302), ('grace', 2, 40), ('grace', 5, 88),
    ('linus', 1, 6);
`);

function query(sql) {
  const cur = db.execute(sql);
  const cols = py.list(cur.description).map((c) => py.list(c)[0]);
  return py.list(cur.fetchall()).map((row) => {
    const r = {};
    py.list(row).forEach((v, i) => (r[cols[i]] = v));
    return r;
  });
}

console.log("commits per author:");
console.table(query(`
  SELECT author,
         COUNT(*)      AS commits,
         SUM(files)    AS files_touched,
         SUM(added)    AS lines_added
  FROM commits
  GROUP BY author
  ORDER BY lines_added DESC
`));

const [{ total }] = query("SELECT SUM(added) AS total FROM commits");
console.log(`\ntotal lines added: ${total}`);
