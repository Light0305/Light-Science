# demo-fullrun：light-figure v1 端到端双线演示

**终点：图包走完 intake → contracted → produced → audited → delivered，`exports/delivery.yaml` 已生成、编号已冻结。**

身份如实说明：这是一条**合成演示链**——数据是 light-experiment
合成演示的三臂结果，期刊合同是按 Nature Figure Guide 现行硬数字
登记的演示合同，AI 政策快照是演示 fixture，图库/组件引用是演示
种子条目，参考图是本地程序绘制的替身（见 demo-report 的逐项披露）。
链上每一步都是真工具真跑：全程命令与输出在
`evidence/run-log.txt`，结构化结果在 `evidence/summary.json`。

## 内容

- `run_demo.py`：演示驱动（全程经 CLI 子进程执行；可重跑，会先
  清空 figure-pkg/、variants/、evidence/ 再重建）。
- `inputs/`：承接清单（Write 形态 figures_manifest）、期刊合同、
  AI 政策快照、三臂逐段 MOTA 源数据（转写自 light-experiment
  demo-synthetic 的三份 summary.json）、参考图替身原图、fig-2
  重绘 manifest 源文件。
- `figure-pkg/`：演示图包本体（终点 delivered）。fig-1 数据图
  （三臂 MOTA 双面板）、fig-2 方法图（火鸡检测流水线示意，
  文件级 .vsdx 重绘，`visio_verified: false`）。
- `variants/`：两个拦截变体（produced 段从主包分叉，**不进正式
  交付**）：`honesty-inverted/`（脚本登记反转轴并真反转绘图，
  被诚实门拦下）、`native-embed/`（整张参考图登记为残留整幅
  嵌入，被原生性门拦下）。
- `evidence/`：run-log.txt（全程命令日志）、summary.json。

## 重跑

在本包 .venv（已 `pip install -e .`）中：

```bash
python examples/demo-fullrun/run_demo.py
```

结论与逐门结果、双拦截细节、与 Write 的回填对账见 `demo-report.md`。
