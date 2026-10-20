# light-software-copyright

Light-Science 出口层扩展位技能：中国软件著作权登记材料（v1）。

把一个已定版软件变成一套可递交的登记材料包：登记事实单一源、源码冻结
快照、选材排除留痕、源程序鉴别材料确定性分页、文档鉴别材料逐段确认
（Q2 折中）、申请表字段派生、发布门禁、正式资料包 + 逐字段递交清单。

**边界（写死）**：只做中国软著；v1 止步于资料包与清单，不代填报官网、
不处理签章、不代签署；当期申请表 AI 使用声明原文未取得，本包不提供
任何声明措辞，只建「递交前逐字核对当期声明原文」硬门；页数随真实内容，
不凑页。

## 快速开始

```bash
cd <案件目录的父目录>
python -m light_copyright init 软件著作权申请资料
python -m light_copyright set-facts 软件著作权申请资料 --from facts.yaml
python -m light_copyright confirm-facts 软件著作权申请资料
python -m light_copyright freeze 软件著作权申请资料 --source <源码目录>
python -m light_copyright select 软件著作权申请资料
python -m light_copyright confirm-selection 软件著作权申请资料
python -m light_copyright render-code 软件著作权申请资料
python -m light_copyright draft-doc 软件著作权申请资料
# 逐段审阅 draft/segments/，可 revise-segment 改写，然后逐段：
python -m light_copyright confirm-segment 软件著作权申请资料 --seg SEG-01
python -m light_copyright render-doc 软件著作权申请资料
# 用户自备当期声明原文后：
python -m light_copyright declaration 软件著作权申请资料 record --file <原文> --origin <取得渠道>
python -m light_copyright declaration 软件著作权申请资料 verify
python -m light_copyright check 软件著作权申请资料
python -m light_copyright package 软件著作权申请资料
# 收到补正通知时：
python -m light_copyright correct 软件著作权申请资料 --notice-date YYYY-MM-DD --items "事项一；事项二"
```

## 演示

`examples/demo-fullrun/run_demo.py`：自造脱敏小软件「微统计算工具」
（无界面 → 设计说明书路径）全链走通至 packaged，含一段草稿改写后
重新确认与 declaration 门演示（占位文本明确标注非官方）。报告见
`examples/demo-fullrun/demo-report.md`。

## 评测

`eval/cases.yaml`：12 个已结案式封闭用例（场景 → 期望门行为），机械
可判者由 `tests/test_eval_cases.py` 承接。

## 已知局限

- 文档 DOCX 的目录页码按文本模型（30 行/页）回填，非办公套件真分页；
  真实递交前建议在 Word 中打开复核分页（清单已注口径）。
- 选材的第三方标识判定基于文件头 40 行启发式，归属争议走 appeal 留痕，
  不保证穷尽；敏感形态为正则口径，深度审计仍需人工抽查。
- 主要功能字数区间与上传格式为 B 级动态口径，递交当日须复核当期表单。
- 申请表声明原文（AI 使用）未取得：见 SKILL §5，本包只建门不造词。
