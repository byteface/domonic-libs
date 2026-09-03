import re

from domonic_libs.qs import formats, parse, stringify


def test_basic_parse():
    assert parse("a=c") == {"a": "c"}


def test_nested_parse():
    assert parse("foo[bar]=baz") == {"foo": {"bar": "baz"}}


def test_array_parse():
    assert parse("a[1]=c&a[0]=b") == {"a": ["b", "c"]}


def test_compacts_sparse_arrays_by_default():
    assert parse("a[1]=b&a[3]=c") == {"a": ["b", "c"]}


def test_dot_parse():
    assert parse("a.b=c", {"allowDots": True}) == {"a": {"b": "c"}}


def test_duplicates():
    assert parse("foo=bar&foo=baz") == {"foo": ["bar", "baz"]}
    assert parse("foo=bar&foo=baz", {"duplicates": "first"}) == {"foo": "bar"}
    assert parse("foo=bar&foo=baz", {"duplicates": "last"}) == {"foo": "baz"}


def test_ignore_query_prefix():
    assert parse("?a=b", {"ignoreQueryPrefix": True}) == {"a": "b"}


def test_basic_stringify():
    assert stringify({"a": "b"}) == "a=b"


def test_nested_stringify():
    assert stringify({"a": {"b": "c"}}) == "a%5Bb%5D=c"


def test_array_stringify_formats():
    assert stringify({"a": ["b", "c"]}) == "a%5B0%5D=b&a%5B1%5D=c"
    assert stringify({"a": ["b", "c"]}, {"arrayFormat": "brackets"}) == "a%5B%5D=b&a%5B%5D=c"
    assert stringify({"a": ["b", "c"]}, {"arrayFormat": "repeat"}) == "a=b&a=c"
    assert stringify({"a": ["b", "c"]}, {"arrayFormat": "comma"}) == "a=b%2Cc"


def test_rfc1738():
    assert stringify({"a": "hello world"}, {"format": formats.RFC1738}) == "a=hello+world"


def test_null_handling():
    assert stringify({"a": None}) == "a="
    assert stringify({"a": None}, {"strictNullHandling": True}) == "a"
    assert stringify({"a": None}, {"skipNulls": True}) == ""


def test_boolean_values_match_js_strings():
    assert stringify({"a": True, "b": False}) == "a=true&b=false"


def test_charset_sentinel():
    assert stringify({"a": "b"}, {"charsetSentinel": True}).startswith("utf8=%E2%9C%93&")


def test_cycle_detection():
    value = {}
    value["self"] = value
    try:
        stringify(value)
    except ValueError as exc:
        assert "Cyclic object value" in str(exc)
    else:
        raise AssertionError("expected cycle failure")


def test_regex_delimiter():
    assert parse("a=b;c=d", {"delimiter": re.compile(r"[&;]")}) == {"a": "b", "c": "d"}


def test_parse_selected_upstream_cases():
    assert parse("0=foo") == {"0": "foo"}
    assert parse("foo=c++") == {"foo": "c  "}
    assert parse("a[>=]=23") == {"a": {">=": "23"}}
    assert parse("a[<=>]==23") == {"a": {"<=>": "=23"}}
    assert parse("foo", {"strictNullHandling": True}) == {"foo": None}
    assert parse("foo[]&bar=baz", {"allowEmptyArrays": True}) == {"foo": [], "bar": "baz"}
    assert parse("foo[]&bar=baz", {"allowEmptyArrays": False}) == {"foo": [""], "bar": "baz"}


def test_parse_depth_selected_upstream_cases():
    assert parse("a[b][c]=d", {"depth": 1}) == {"a": {"b": {"[c]": "d"}}}
    assert parse("a[0]=b&a[1]=c", {"depth": 0}) == {"a[0]": "b", "a[1]": "c"}
    assert parse("a.b=c", {"depth": 0, "allowDots": True}) == {"a[b]": "c"}
    assert parse("toString=foo", {"depth": 0}) == {}
    assert parse("toString=foo", {"depth": 0, "allowPrototypes": True}) == {"toString": "foo"}


def test_parameter_limit_selected_upstream_cases():
    assert parse("a=1&b=2&c=3&d=4&e=5", {"parameterLimit": 3}) == {
        "a": "1", "b": "2", "c": "3"
    }
    try:
        parse(
            "a=1&b=2&c=3&d=4&e=5&f=6",
            {"parameterLimit": 3, "throwOnLimitExceeded": True},
        )
    except ValueError as exc:
        assert "Parameter limit exceeded" in str(exc)
    else:
        raise AssertionError("expected parameter limit failure")


def test_array_limit_selected_upstream_cases():
    assert parse("a[1001]=b", {"arrayLimit": 1000}) == {"a": {"1001": "b"}}
    assert parse("a[0]=x&a=y", {"arrayLimit": 1}) == {"a": {"0": "x", "1": "y"}}
    assert parse(
        "a=1,2,3&a=4,5,6", {"comma": True, "arrayLimit": 5}
    ) == {"a": {"0": "1", "1": "2", "2": "3", "3": "4", "4": "5", "5": "6"}}


def test_bracket_comma_groups_selected_upstream_cases():
    assert parse(
        "a[]=1,2,3&a[]=4,5,6",
        {"comma": True, "arrayLimit": 5, "throwOnLimitExceeded": True},
    ) == {"a": [["1", "2", "3"], ["4", "5", "6"]]}
    assert parse("a[]=1,2,3,4", {"comma": True, "arrayLimit": 3}) == {
        "a": [["1", "2", "3", "4"]]
    }


def test_stringify_selected_upstream_unicode_cases():
    assert stringify({"a": 1}) == "a=1"
    assert stringify({"a": "€"}) == "a=%E2%82%AC"
    assert stringify({"a": "א"}) == "a=%D7%90"
    assert stringify({"a": "𐐷"}) == "a=%F0%90%90%B7"


def test_stringify_dotted_keys_selected_upstream_cases():
    obj = {"name.obj": {"first": "John", "last": "Doe"}}
    assert stringify(obj, {"allowDots": False, "encodeDotInKeys": False}) == (
        "name.obj%5Bfirst%5D=John&name.obj%5Blast%5D=Doe"
    )
    assert stringify(obj, {"allowDots": True, "encodeDotInKeys": False}) == (
        "name.obj.first=John&name.obj.last=Doe"
    )
    assert stringify(obj, {"allowDots": False, "encodeDotInKeys": True}) == (
        "name%252Eobj%5Bfirst%5D=John&name%252Eobj%5Blast%5D=Doe"
    )
    assert stringify(obj, {"allowDots": True, "encodeDotInKeys": True}) == (
        "name%252Eobj.first=John&name%252Eobj.last=Doe"
    )


def test_stringify_encode_values_only_dot_case():
    assert stringify(
        {"name.obj": "John"},
        {"encodeDotInKeys": True, "allowDots": True, "encodeValuesOnly": True},
    ) == "name%2Eobj=John"


def test_stringify_allow_empty_arrays():
    assert stringify({"a": [], "b": "zz"}) == "b=zz"
    assert stringify({"a": [], "b": "zz"}, {"allowEmptyArrays": True}) == "a[]&b=zz"


def test_stringify_depth():
    assert stringify({"a": {"b": {"c": "d"}}}, {"depth": 2}) == "a%5Bb%5D%5Bc%5D=d"
    try:
        stringify({"a": {"b": {"c": {"d": "e"}}}}, {"depth": 2})
    except ValueError as exc:
        assert "Input depth exceeded depth option of 2" in str(exc)
    else:
        raise AssertionError("expected depth failure")


def test_stringify_sort_comparator():
    def sort(a, b):
        return (a > b) - (a < b)

    assert stringify({"a": "c", "z": "y", "b": "f"}, {"sort": sort}) == "a=c&b=f&z=y"
    assert stringify(
        {"a": "c", "z": {"j": "a", "i": "b"}, "b": "f"}, {"sort": sort}
    ) == "a=c&b=f&z%5Bi%5D=b&z%5Bj%5D=a"


def test_python_integer_mapping_keys_are_js_stringified():
    assert stringify({0: "a", 1: "b"}) == "0=a&1=b"


def test_add_query_prefix():
    assert stringify({"a": "b"}, {"addQueryPrefix": True}) == "?a=b"
