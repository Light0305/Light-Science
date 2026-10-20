"""纠错层纯函数测试：表格网格自洽 + 公式可编译性代理。"""

from light_literature.checks import check_formula_compilable, check_table_grid

GOOD_TABLE = """
<table>
  <tr><th>A</th><th>B</th><th>C</th></tr>
  <tr><td rowspan="2">x</td><td>1</td><td>2</td></tr>
  <tr><td>3</td><td>4</td></tr>
  <tr><td colspan="2">y</td><td>5</td></tr>
</table>
"""

BAD_TABLE = """
<table>
  <tr><td>A</td><td>B</td></tr>
  <tr><td>1</td><td>2</td><td>3</td></tr>
</table>
"""


def test_table_grid_ok_with_spans():
    r = check_table_grid(GOOD_TABLE)
    assert r["ok"], r
    assert r["rows"] == 4
    assert r["cols_per_row"] == [3, 3, 3, 3]


def test_table_grid_detects_ragged_rows():
    r = check_table_grid(BAD_TABLE)
    assert not r["ok"]
    assert r["cols_per_row"] == [2, 3]


def test_table_grid_empty_is_not_ok():
    r = check_table_grid("<p>no table here</p>")
    assert not r["ok"]


def test_formula_compilable_ok():
    r = check_formula_compilable(r"\frac{a}{b} + \sqrt{x^2 + y^2}")
    assert r["ok"] is True, r


def test_formula_compilable_bad():
    r = check_formula_compilable(r"\frac{1}{")
    assert r["ok"] is False
    assert r["error"]


def test_formula_compilable_empty():
    r = check_formula_compilable("   ")
    assert r["ok"] is False
