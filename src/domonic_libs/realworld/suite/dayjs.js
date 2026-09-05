test(function () {
  assert_equals(dayjs("2024-01-15").format("YYYY-MM-DD"), "2024-01-15", "round-trips an ISO date");
}, "dayjs format");

test(function () {
  var d = dayjs("2024-01-15").add(1, "month");
  assert_equals(d.format("YYYY-MM-DD"), "2024-02-15", "add(1, month)");
}, "dayjs arithmetic");

test(function () {
  assert_true(dayjs("2024-06-01").isBefore(dayjs("2024-06-02")), "isBefore");
}, "dayjs comparison");
