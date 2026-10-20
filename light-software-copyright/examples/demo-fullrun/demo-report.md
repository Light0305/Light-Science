# 演示报告：微统计算工具（无界面 → 设计说明书路径）

## 链路与终点

- 代码材料：3 页（全量 3 页），文档材料：设计说明书 2 页（DOCX：文档鉴别材料-设计说明书.docx）
- 终点状态：状态：packaged

## 关键输出

```
$ light-copyright declaration ../../../light-software-copyright/examples/demo-fullrun/case-pkg record --file ../../../light-software-copyright/examples/demo-fullrun/inputs/declaration-demo-note.txt --origin 演示占位（非官方文本，仅演示登记机制）
声明原文已登记：214 字，哈希 521056e1a5ed，来源 演示占位（非官方文本，仅演示登记机制）。下一步：用户本人逐字核对后 declaration verify。

$ light-copyright declaration ../../../light-software-copyright/examples/demo-fullrun/case-pkg verify --attest 演示回执：已逐字读过所登记文本（演示占位）
declaration 门通过：原文在案 + 逐字核对回执有效 + 留痕无矛盾。

$ light-copyright status ../../../light-software-copyright/examples/demo-fullrun/case-pkg
状态：confirmed
软件：微统计算工具 V1.0（headless）
规则快照：2026-10-21（动态字段递交当日复核，HC-7）

$ light-copyright check ../../../light-software-copyright/examples/demo-fullrun/case-pkg
警告（不拦）：主要功能 385 字：B 级信号区间为 500-1300 字（行业转述，非官方原文），递交当日以当期表单复核，本步不拦
发布门禁全过。下一步：package 产出资料包与递交清单。

$ light-copyright package ../../../light-software-copyright/examples/demo-fullrun/case-pkg
资料包已产出：../../../light-software-copyright/examples/demo-fullrun/case-pkg/资料包
  - 源程序鉴别材料.txt
  - 文档鉴别材料-设计说明书.docx
  - 文档鉴别材料-设计说明书.txt
  - 源程序鉴别材料.index.jsonl
  - 递交清单.md
  - 工具使用记录.jsonl
v1 到此为止：递交（官网填报/签章）由用户本人按递交清单完成。

$ light-copyright status ../../../light-software-copyright/examples/demo-fullrun/case-pkg
状态：packaged
软件：微统计算工具 V1.0（headless）
规则快照：2026-10-21（动态字段递交当日复核，HC-7）
```

## 演示口径说明

- 演示声明文件是明确标注的占位说明，只演示登记 + 核对回执机制；本包不保存任何官方声明措辞，真实递交须用户自备当期原文。
- 一段草稿经演示改写后旧确认失效、按新哈希重新确认，Q2 逐段确认链完整走过。

## 收尾（X-10 四行）

- 完成项：全链 init → packaged 走通，资料包与逐字段递交清单产出
- 跳过项：截图导入（无界面软件无截图面，Q6 预留位机制由测试覆盖）
- 未验项：真实登记系统递交不在 v1 范围（Q4）；DOCX 真分页未用办公套件实测（目录页码为文本模型回填，已在清单注口径）；check 输出含一条主要功能字数 B 级警告（385 字），属预期演示
- 风险：主要功能字数与声明原文均为动态口径，真实使用递交当日须按当期表单复核（HC-7）
