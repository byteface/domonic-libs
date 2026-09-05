test(function () {
  var list = [{ title: "Old Man's War" }, { title: "The Lock Artist" }, { title: "HTML5" }];
  var fuse = new Fuse(list, { keys: ["title"] });
  var results = fuse.search("lock artist");
  assert_true(results.length > 0, "finds a fuzzy match");
  assert_equals(results[0].item.title, "The Lock Artist", "best match is the right item");
}, "Fuse fuzzy search");
