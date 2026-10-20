# 判定复核包 — analysis-pkg

- 生成日期：2026-10-20
- 执行包：video-threshold-predict_synth01-b2
- Design content_hash：`1ed8de06e50e72257c1f57de3b3ce74fb39247e16cfe6de36280653a44d3475f`
- 判定参数：γ=0.75、Type M 阈值=2.0
- 分析执行者：light-analysis-phase1-demo（家族 claude）

## 判定口径宪法（复核者须知，判据不重开）

- 判定口径只认 Design 冻结登记行：方向、γ=登记值、SESOI 登记快照值；
  分析期新立的标准一律无效。
- positive 双门：规格集联合推断（中位效应同向 + 方向份额 ≥0.5 +
  Stouffer 合并 p 达族 α）与 Type S/M 校准（D 只许冻结 SESOI，
  Type M ≤ 登记阈值）缺一不可。
- null 只许由 TOST 挣来（bounds = 登记 SESOI，90% CI 全落界内）；
  「不显著」不等于 null；判不了落 undetermined 是一等终态。
- 作废 run 支撑行与 fundamental 失败行只许 untested（未检验 ≠ 不成立）。
- 强度 4 档由合成式机械给出（证据上限 × 稳健档 × Type S/M），
  复核只判合成是否合式、边界落字是否属实，不改判据、不改档位定义。
- 复核结论形态：逐边界行 agree / disagree + 一句理由；有 disagree 的
  回填不被接受——须先改判（supersedes 新行）后重新复核。


## 全部判定摘要

| 登记行 | 判定 | 象限 | 强度 | 方向份额 | Type M |
|---|---|---|---|---|---|
| R-FIX | undetermined | undetermined |  | 1.0 | 4.345393817510087 |
| R-ORA | undetermined | undetermined |  | 1.0 | 3.341473398012883 |
| R-PRED | undetermined | undetermined |  | 1.0 | 3.3421693419529457 |
| R-NEG | untested |  |  |  |  |
| R-LONG | undetermined | undetermined |  | 1.0 | 3.3421693419529457 |

## 边界情形行（共 4 行，逐行全字段）

### R-FIX

入选理由：judge 落 undetermined：门缺口属实性待核

```json
{
  "registry_line_id": "R-FIX",
  "claim_ref": null,
  "row_ref": "R-FIX#v1",
  "supersedes": null,
  "verdict": "undetermined",
  "quadrant": "undetermined",
  "basis_spec_id": "S001",
  "criteria_ref": "登记行冻结判据 direction=higher，SESOI 指针 evaluation.sesoi",
  "direction": "higher",
  "effect_size": {
    "type": "mean_diff",
    "value": 0.0
  },
  "interval": {
    "kind": "ci",
    "level": 0.95,
    "lo": -8.055765676500275,
    "hi": 8.055765676500275
  },
  "p_ab": 0.5,
  "p_ab_gamma": 0.75,
  "n_effective": 6,
  "n_registered": 6,
  "type_sm": {
    "assumed_D": {
      "value": 2.0,
      "basis": "sesoi_frozen",
      "source_ref": "evaluation.sesoi"
    },
    "power": 0.08572857520832083,
    "type_s": 0.06979057907696283,
    "type_m": 4.345393817510087
  },
  "tost": {
    "bounds": {
      "lo": -2.0,
      "hi": 2.0,
      "source": "design_sesoi"
    },
    "p_tost": 0.2961460394815605,
    "ci90": {
      "lo": -6.552895969712681,
      "hi": 6.552895969712681
    },
    "ci90_in_bounds": false,
    "result": "fail"
  },
  "diagnostics": null,
  "bayes": false,
  "correction": {
    "family_id": "claim:all",
    "method": "fdr_bh",
    "p_raw": 1.0,
    "p_adj": 1.0
  },
  "strength_grade": null,
  "strength_cap_reason": null,
  "note": "主规格校正后 p=1 未达族 α=0.05；分布判据未达门：判定方向概率 P=0.500 < γ=0.75；TOST 未过：等价未挣得，不许落 null",
  "decided_by": "light-analysis-phase1-demo",
  "decided_at": "2026-10-20",
  "joint": {
    "median_effect": 0.0,
    "direction_share": 1.0,
    "stouffer_p": 1.0,
    "specs_used": [
      "S001",
      "S002",
      "S003",
      "S004"
    ]
  },
  "calc_provenance": {
    "method": "welch_effect_and_ci",
    "inputs_hash": "a39837e66ed294d8edd58e30900ecca3a74c20998c72617b2c500bf012823710",
    "params": {
      "level": 0.95
    }
  },
  "distribution_ref": {
    "source": "judge-data",
    "data_file": "judge-data.json",
    "reference_label": "固定阈值臂执行期分布（R-FIX-a1 段级均值）；处理臂为同一基线臂的冷启动重跑分布（R-FIX-a2，coldstart 产物）——本行判的是基线复现等价性",
    "run_refs": [
      "R-FIX-a2",
      "R-FIX-a1"
    ]
  }
}
```

### R-ORA

入选理由：judge 落 undetermined：门缺口属实性待核

```json
{
  "registry_line_id": "R-ORA",
  "claim_ref": null,
  "row_ref": "R-ORA#v1",
  "supersedes": null,
  "verdict": "undetermined",
  "quadrant": "undetermined",
  "basis_spec_id": "S001",
  "criteria_ref": "登记行冻结判据 direction=higher，SESOI 指针 evaluation.sesoi",
  "direction": "higher",
  "effect_size": {
    "type": "mean_diff",
    "value": 5.249333333333325
  },
  "interval": {
    "kind": "ci",
    "level": 0.95,
    "lo": -1.3441246209703666,
    "hi": 11.842791287637016
  },
  "p_ab": 0.7777777777777778,
  "p_ab_gamma": 0.75,
  "n_effective": 6,
  "n_registered": 6,
  "type_sm": {
    "assumed_D": {
      "value": 2.0,
      "basis": "sesoi_frozen",
      "source_ref": "evaluation.sesoi"
    },
    "power": 0.11278357326337113,
    "type_s": 0.03175797426913029,
    "type_m": 3.341473398012883
  },
  "tost": {
    "bounds": {
      "lo": -2.0,
      "hi": 2.0,
      "source": "design_sesoi"
    },
    "p_tost": 0.8611050078769977,
    "ci90": {
      "lo": -0.010993990222780248,
      "hi": 10.50966065688943
    },
    "ci90_in_bounds": false,
    "result": "fail"
  },
  "diagnostics": null,
  "bayes": false,
  "correction": {
    "family_id": "claim:all",
    "method": "fdr_bh",
    "p_raw": 0.10057444646739233,
    "p_adj": 0.1377835800186936
  },
  "strength_grade": null,
  "strength_cap_reason": null,
  "note": "主规格校正后 p=0.1378 未达族 α=0.05；TOST 未过：等价未挣得，不许落 null",
  "decided_by": "light-analysis-phase1-demo",
  "decided_at": "2026-10-20",
  "joint": {
    "median_effect": 4.574666666666651,
    "direction_share": 1.0,
    "stouffer_p": 0.001181302547676788,
    "specs_used": [
      "S001",
      "S002",
      "S003",
      "S004"
    ]
  },
  "calc_provenance": {
    "method": "welch_effect_and_ci",
    "inputs_hash": "8c63357571c558e729f46c321fd26788ccf53aef6ad1a6ed3abd25ce0fecf32d",
    "params": {
      "level": 0.95
    }
  },
  "distribution_ref": {
    "source": "judge-data",
    "data_file": "judge-data.json",
    "reference_label": "固定阈值臂（R-FIX-a1 段级均值，基线对照）",
    "run_refs": [
      "R-ORA-a1",
      "R-FIX-a1"
    ]
  }
}
```

### R-PRED

入选理由：judge 落 undetermined：门缺口属实性待核

```json
{
  "registry_line_id": "R-PRED",
  "claim_ref": null,
  "row_ref": "R-PRED#v1",
  "supersedes": null,
  "verdict": "undetermined",
  "quadrant": "undetermined",
  "basis_spec_id": "S001",
  "criteria_ref": "登记行冻结判据 direction=higher，SESOI 指针 evaluation.sesoi",
  "direction": "higher",
  "effect_size": {
    "type": "mean_diff",
    "value": 5.197833333333335
  },
  "interval": {
    "kind": "ci",
    "level": 0.95,
    "lo": -1.3960097094820032,
    "hi": 11.791676376148674
  },
  "p_ab": 0.7777777777777778,
  "p_ab_gamma": 0.75,
  "n_effective": 6,
  "n_registered": 6,
  "type_sm": {
    "assumed_D": {
      "value": 2.0,
      "basis": "sesoi_frozen",
      "source_ref": "evaluation.sesoi"
    },
    "power": 0.11275517736657004,
    "type_s": 0.03178130282060294,
    "type_m": 3.3421693419529457
  },
  "tost": {
    "bounds": {
      "lo": -2.0,
      "hi": 2.0,
      "source": "design_sesoi"
    },
    "p_tost": 0.8575717586284212,
    "ci90": {
      "lo": -0.06302304180700347,
      "hi": 10.458689708473674
    },
    "ci90_in_bounds": false,
    "result": "fail"
  },
  "diagnostics": null,
  "bayes": false,
  "correction": {
    "family_id": "claim:all",
    "method": "fdr_bh",
    "p_raw": 0.10333768501402019,
    "p_adj": 0.1377835800186936
  },
  "strength_grade": null,
  "strength_cap_reason": null,
  "note": "主规格校正后 p=0.1378 未达族 α=0.05；TOST 未过：等价未挣得，不许落 null",
  "decided_by": "light-analysis-phase1-demo",
  "decided_at": "2026-10-20",
  "joint": {
    "median_effect": 4.574916666666667,
    "direction_share": 1.0,
    "stouffer_p": 0.001237187836119702,
    "specs_used": [
      "S001",
      "S002",
      "S003",
      "S004"
    ]
  },
  "calc_provenance": {
    "method": "welch_effect_and_ci",
    "inputs_hash": "62ccc7ade1af50db20fd4e4f949b60f91db8c5e5f59cacbe6acf6ae6de69a059",
    "params": {
      "level": 0.95
    }
  },
  "distribution_ref": {
    "source": "judge-data",
    "data_file": "judge-data.json",
    "reference_label": "固定阈值臂（登记行 control_run=R-FIX，取 R-FIX-a1 段级均值）",
    "run_refs": [
      "R-PRED-a2",
      "R-FIX-a1"
    ]
  }
}
```

### R-LONG

入选理由：judge 落 undetermined：门缺口属实性待核

```json
{
  "registry_line_id": "R-LONG",
  "claim_ref": null,
  "row_ref": "R-LONG#v1",
  "supersedes": null,
  "verdict": "undetermined",
  "quadrant": "undetermined",
  "basis_spec_id": "S001",
  "criteria_ref": "登记行冻结判据 direction=higher，SESOI 指针 evaluation.sesoi",
  "direction": "higher",
  "effect_size": {
    "type": "mean_diff",
    "value": 5.197833333333335
  },
  "interval": {
    "kind": "ci",
    "level": 0.95,
    "lo": -1.3960097094820032,
    "hi": 11.791676376148674
  },
  "p_ab": 0.7777777777777778,
  "p_ab_gamma": 0.75,
  "n_effective": 6,
  "n_registered": 6,
  "type_sm": {
    "assumed_D": {
      "value": 2.0,
      "basis": "sesoi_frozen",
      "source_ref": "evaluation.sesoi"
    },
    "power": 0.11275517736657004,
    "type_s": 0.03178130282060294,
    "type_m": 3.3421693419529457
  },
  "tost": {
    "bounds": {
      "lo": -2.0,
      "hi": 2.0,
      "source": "design_sesoi"
    },
    "p_tost": 0.8575717586284212,
    "ci90": {
      "lo": -0.06302304180700347,
      "hi": 10.458689708473674
    },
    "ci90_in_bounds": false,
    "result": "fail"
  },
  "diagnostics": null,
  "bayes": false,
  "correction": {
    "family_id": "claim:all",
    "method": "fdr_bh",
    "p_raw": 0.10333768501402019,
    "p_adj": 0.1377835800186936
  },
  "strength_grade": null,
  "strength_cap_reason": null,
  "note": "主规格校正后 p=0.1378 未达族 α=0.05；TOST 未过：等价未挣得，不许落 null",
  "decided_by": "light-analysis-phase1-demo",
  "decided_at": "2026-10-20",
  "joint": {
    "median_effect": 4.574916666666667,
    "direction_share": 1.0,
    "stouffer_p": 0.001237187836119702,
    "specs_used": [
      "S001",
      "S002",
      "S003",
      "S004"
    ]
  },
  "calc_provenance": {
    "method": "welch_effect_and_ci",
    "inputs_hash": "62ccc7ade1af50db20fd4e4f949b60f91db8c5e5f59cacbe6acf6ae6de69a059",
    "params": {
      "level": 0.95
    }
  },
  "distribution_ref": {
    "source": "judge-data",
    "data_file": "judge-data.json",
    "reference_label": "固定阈值臂（登记行 control_run=R-FIX，取 R-FIX-a1 段级均值）",
    "run_refs": [
      "R-LONG-a2",
      "R-FIX-a1"
    ]
  }
}
```

## 回填形态（review import --from-json 的 JSON schema）

```json
{
  "reviewer": "<复核者名>",
  "family": "<模型家族，须与分析执行者不同族>",
  "decisions": [
    {
      "registry_line_id": "<边界行 id>",
      "agree": true,
      "comment": "<一句理由>"
    }
  ],
  "notes": "<可选总评>"
}
```
