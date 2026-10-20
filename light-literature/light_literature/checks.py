"""可验证纠错层的两个纯函数检查（供视觉通道与 verify 调用）。

- check_table_grid：HTML 表格展开 rowspan/colspan 后校验每行列数一致。
- check_formula_compilable：用 matplotlib 的 mathtext 解析器试解析 LaTeX。
  注意：mathtext 只支持 LaTeX 的子集，这是「可编译性代理」而非 KaTeX 等价判定；
  代理判失败不等于公式错误，只能作为进人工复核清单的信号。
"""

from __future__ import annotations

from html.parser import HTMLParser


class _TableParser(HTMLParser):
    """把 HTML 表格解析成带 span 信息的行列结构。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict]] = []
        self._row: list[dict] | None = None
        self._cell: dict | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            def _span(name):
                try:
                    return max(1, int(attrs.get(name, 1)))
                except (TypeError, ValueError):
                    return 1
            self._cell = {"rowspan": _span("rowspan"),
                          "colspan": _span("colspan"), "text": ""}
            self._row.append(self._cell)

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"] += data

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def expand_grid(rows: list[list[dict]]) -> list[list[str]]:
    """把带 rowspan/colspan 的行结构展开成完整网格（单元格文本矩阵）。"""
    grid: list[list[str]] = []
    carry: dict[int, tuple[int, str]] = {}  # 列 -> (剩余行数, 文本)
    for row in rows:
        out: list[str] = []
        col = 0
        for cell in row:
            while col in carry and carry[col][0] > 0:
                out.append(carry[col][1])
                carry[col] = (carry[col][0] - 1, carry[col][1])
                col += 1
            text = cell["text"].strip()
            for k in range(cell["colspan"]):
                out.append(text if k == 0 else "")
                if cell["rowspan"] > 1:
                    carry[col] = (cell["rowspan"] - 1, text)
                col += 1
        while col in carry and carry[col][0] > 0:
            out.append(carry[col][1])
            carry[col] = (carry[col][0] - 1, carry[col][1])
            col += 1
        grid.append(out)
    return grid


def check_table_grid(html: str) -> dict:
    """校验 HTML 表格网格自洽：展开后每行列数必须一致。

    返回 {ok, rows, cols_per_row, errors}。空表/无表格视为不通过（ok=False）。
    """
    parser = _TableParser()
    parser.feed(html)
    if not parser.rows:
        return {"ok": False, "rows": 0, "cols_per_row": [],
                "errors": ["未解析到任何表格行"]}
    grid = expand_grid(parser.rows)
    cols = [len(r) for r in grid]
    errors = []
    if len(set(cols)) != 1:
        errors.append(f"各行展开列数不一致：{cols}")
    return {"ok": not errors, "rows": len(grid),
            "cols_per_row": cols, "errors": errors}


def check_formula_compilable(latex: str) -> dict:
    """公式可编译性检查（matplotlib mathtext 代理，非 KaTeX 等价）。

    返回 {ok, error, engine}。matplotlib 不可用时 ok=None 表示无法判定。
    """
    expr = (latex or "").strip()
    if not expr:
        return {"ok": False, "error": "空公式", "engine": "matplotlib-mathtext"}
    if expr.startswith("$$") and expr.endswith("$$"):
        expr = expr[2:-2]
    elif expr.startswith("$") and expr.endswith("$"):
        expr = expr[1:-1]
    try:
        from matplotlib.mathtext import MathTextParser
    except ImportError:
        return {"ok": None, "error": "matplotlib 未安装，无法判定",
                "engine": "matplotlib-mathtext"}
    try:
        MathTextParser("agg").parse(f"${expr}$")
        return {"ok": True, "error": None, "engine": "matplotlib-mathtext"}
    except Exception as exc:  # mathtext 抛 ValueError 等
        return {"ok": False, "error": str(exc)[:300],
                "engine": "matplotlib-mathtext"}
