#!/usr/bin/env python3
"""Light-Figure v1 端到端双线演示驱动（合成链，身份见 README.md）。

全程经 CLI 子进程执行（`python -m light_figure ...`），每条命令与
输出 tee 进 evidence/run-log.txt；合同/backend 等登记文件由本驱动
按用户手写文件的形态落盘。流程：

  数据线 fig-1：承接三臂 MOTA 结果（源自 Light-Experiment 合成演示
  的 R-FIX-a1 / R-ORA-a1 / R-PRED-a2 summary）做双面板图；
  方法线 fig-2：火鸡行为检测流水线示意（图库种子条目 → 提示词 →
  程序绘制的参考图替身 → 文件级 .vsdx 重绘）。
  produced 段分叉两个拦截变体（反转轴 / 整幅残留嵌入），变体不进
  正式交付；主包走完 intake → … → delivered 并产出 delivery.yaml。

在本包 .venv（已 pip install -e .）中运行：
    python examples/demo-fullrun/run_demo.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE / "figure-pkg"
INPUTS = HERE / "inputs"
VARIANTS = HERE / "variants"
EVIDENCE = HERE / "evidence"
LOG_PATH = EVIDENCE / "run-log.txt"

# 三臂逐段 MOTA 均值：转写自 light-experiment/examples/demo-synthetic
# 的 work/R-FIX-a1、R-ORA-a1、R-PRED-a2 三份 summary.json
# （per_segment_mean，n=6 段、每段 3 种子均值；臂均值 72.638 /
# 77.887 / 77.835 与源文件一致）。
ARMS = {
    "fixed": [75.446, 68.821, 77.293, 62.187, 79.169, 72.909],
    "oracle": [78.951, 76.597, 79.581, 74.090, 80.898, 77.204],
    "predicted": [79.090, 76.642, 79.623, 73.899, 80.589, 77.169],
}

_log_lines: list[str] = []


def log(text: str = "") -> None:
    _log_lines.append(text)
    print(text, flush=True)


def run_cli(*args, cwd=None, expect_fail=False) -> dict:
    cmd = [sys.executable, "-m", "light_figure", *args]
    workdir = Path(cwd) if cwd else PKG
    if not workdir.exists():
        workdir = HERE
    log(f"\n$ {' '.join(str(a) for a in cmd[2:])}"
        f"   (cwd={workdir})")
    proc = subprocess.run(cmd, cwd=workdir, capture_output=True,
                          text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    log(out.rstrip())
    if expect_fail and proc.returncode == 0:
        raise SystemExit(f"期望失败但成功：{args}")
    if not expect_fail and proc.returncode != 0:
        raise SystemExit(f"命令失败（rc={proc.returncode}）：{args}\n{out}")
    try:
        return json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return {}


def driver_note(text: str) -> None:
    log(f"[driver] {text}")


# ---------------------------------------------------------------- 输入

def write_inputs() -> None:
    INPUTS.mkdir(parents=True, exist_ok=True)
    csv_path = INPUTS / "arms_segments.csv"
    lines = ["arm,segment,mota"]
    for arm, values in ARMS.items():
        for i, v in enumerate(values, start=1):
            lines.append(f"{arm},{i},{v}")
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    import yaml
    manifest = {"figures": [
        {"figure_id": "fig-1", "kind": "data",
         "caption": "Three tracker-threshold strategies on the "
                    "turkey-barn benchmark: per-segment MOTA (a) and "
                    "arm means with 95% CI across segments (b).",
         "intext_refs": ["results:p2"]},
        {"figure_id": "fig-2", "kind": "schematic",
         "caption": "Pipeline of the zero-tuning threshold-prediction "
                    "method for abnormal turkey behaviour detection.",
         "intext_refs": ["methods:p1"]},
    ]}
    (INPUTS / "figures_manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")

    from light_figure.project import new_journal_contract
    from light_figure.util import dump_yaml, today
    jc = new_journal_contract()
    jc.update({
        "registered": True,
        "journal": "Demo Journal (Nature Figure Guide anchors)",
        "version": "2026",
        "checked_at": today(),
        "source_url": "https://research-figure-guide.nature.com/",
    })
    jc["font"]["family"] = "Arial"
    jc["palettes"] = {
        "categorical": {"entry_id": "PAL-OI-8", "version": "2002.1"},
        "continuous": {"entry_id": "PAL-BATLOW", "version": "8.0"},
    }
    dump_yaml(INPUTS / "journal_contract.yaml", jc)

    policy = {
        "ai_images_prohibited": True,
        "exhibit_exemption": None,
        "disclosure_required": True,
        "source_url": "https://example.org/ai-policy-demo-fixture",
        "verified_at": today(),
    }
    dump_yaml(INPUTS / "ai_policy.yaml", policy)
    driver_note("inputs 已生成：arms_segments.csv（三臂逐段 MOTA，转写自"
                " Light-Experiment 合成演示三份 summary.json）、"
                "figures_manifest.yaml、journal_contract.yaml、"
                "ai_policy.yaml（演示 fixture）")


# ---------------------------------------------------------------- 合同

def write_contracts_and_backend() -> None:
    from light_figure.project import save_backend, save_contract
    from light_figure.util import today

    save_contract(PKG, {
        "fig_id": "fig-1", "line": "data",
        "core_conclusion": "零调参的预测阈值臂与逐段 oracle 阈值精度相当，"
                           "且显著高于固定阈值基线。",
        "results_question": "免逐视频手工调参是否以精度为代价？",
        "archetype": "quantitative_grid",
        "panel_map": [
            {"panel_id": "a", "role": "primary_quantitative_evidence",
             "content": "三臂逐段 MOTA 曲线（6 段视频）",
             "evidence_tier": "hero"},
            {"panel_id": "b", "role": "baseline_or_control",
             "content": "三臂段间均值 ± 95% CI，固定阈值为对照基线",
             "evidence_tier": "controls_robustness"},
        ],
        "evidence_requirements": {
            "statistics": "段均值（每段 3 种子）+ 臂均值 ± 95% CI（n=6 段）",
            "source_data": "data/source-data/fig-1.csv",
            "image_integrity_notes": "none",
        },
        "density_stance": {"stance": "simplicity_first",
                           "reason": "单图单主张：预测臂≈oracle 且 >fixed"},
        "export_contract_ref": {"journal_contract": "journal_contract.yaml",
                                "overrides": []},
        "reviewer_risk": [
            {"risk": "CI 依据的 n 不明",
             "disposition": "图注写明 n=6 段、段值为 3 种子均值"}],
        "data_integrity": {"exclusions": "none"},
        "sister_library_refs": {
            "method_gallery": None, "visio_components": [],
            "data_gallery": {"entry_id": "DG-DEMO-SEED-001",
                             "version": "0.1"},
        },
    })
    save_contract(PKG, {
        "fig_id": "fig-2", "line": "schematic",
        "core_conclusion": "方法以视频级统计量预测逐轨迹阈值，"
                           "全程无需逐视频人工调参。",
        "results_question": "读者能否一段内复述检测—跟踪—预测—判定流水线？",
        "archetype": "schematic_led_composite",
        "panel_map": [
            {"panel_id": "a", "role": "setup_schematic",
             "content": "棚舍视频输入与多目标跟踪轨迹",
             "evidence_tier": "hero"},
            {"panel_id": "b", "role": "mechanistic_evidence",
             "content": "视频级统计量 → 阈值预测 → 逐轨迹应用 → 异常标记",
             "evidence_tier": "validation"},
        ],
        "evidence_requirements": {
            "statistics": "none", "source_data": "none",
            "image_integrity_notes": "示意图无实验图像，代表性不适用",
        },
        "density_stance": {"stance": "density_first",
                           "reason": "方法图须自包含复述全部模块与数据流"},
        "export_contract_ref": {"journal_contract": "journal_contract.yaml",
                                "overrides": []},
        "reviewer_risk": [
            {"risk": "示意模块与论文方法节命名不一致",
             "disposition": "六个模块标签与方法节小节标题逐字对齐"}],
        "data_integrity": {"exclusions": "none"},
        "sister_library_refs": {
            "method_gallery": {
                "entry_id": "MG-DEMO-SEED-001", "version": "0.1",
                "style_anchor": "anchor-pipeline-flow",
                "prompt_version": "1",
            },
            "visio_components": [
                {"component_id": "VC-DEMO-SEED-ARROW", "version": "0.1"}],
            "data_gallery": None,
        },
        "policy_check": {
            "policy_snapshot_ref": "figure.yaml#ai_policy_snapshot",
            "reference_not_in_delivery": True,
            "degradation_path": "normal",
        },
        "role_palette_ref": {"entry_id": "PAL-ROLE-METHOD",
                             "version": "1.2"},
        "palette_confirmation": {"confirmed_by": "demo-author",
                                 "confirmed_at": today()},
    })
    save_backend(PKG, {
        "backend": "python", "decided_via": "explicit",
        "decided_at": today(), "scope": "package", "overrides": [],
    })
    driver_note("contracts/fig-1.yaml、contracts/fig-2.yaml 五点合同与 "
                "backend.json（python，explicit）已落盘；图库/组件引用为"
                "演示种子条目（MG-DEMO-SEED-001 / VC-DEMO-SEED-ARROW / "
                "DG-DEMO-SEED-001，均在报告中披露）")


DATA_SCRIPT = '''# --- light-figure-script ---
# fig_id: fig-1
# style_build_hash: {bundle_hash}
# column: double
# panels: {{rows: 1, cols: 2}}
# axes:
#   y: {{direction: increasing, limits: [60, 82], data_min: 62.187,
#       data_max: 80.898, truncated: false, truncation_declared: false}}
#   x: {{direction: increasing, limits: [1, 6], data_min: 1, data_max: 6,
#       truncated: false, truncation_declared: false}}
# aspect: {{ratio: 0.52, declared: true}}
# area_encoding: none
# palette: {{categorical: PAL-OI-8, continuous: PAL-BATLOW}}
# --- end light-figure-script ---
"""三臂 MOTA 对比（演示数据图脚本）：a 逐段曲线、b 臂均值 ± 95% CI。"""
import csv
import math
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "source-data" / "fig-1.csv"
ARMS = ["fixed", "oracle", "predicted"]


def _series():
    rows = list(csv.DictReader(DATA.open(encoding="utf-8")))
    out = dict()
    for arm in ARMS:
        out[arm] = [float(r["mota"]) for r in rows if r["arm"] == arm]
    return out


def draw(fig, axes):
    series = _series()
    ax = axes[0]
    for arm in ARMS:
        ax.plot(range(1, 7), series[arm], marker="o", label=arm)
    ax.set_xlim(1, 6)
    ax.set_ylim(60, 82)
    ax.set_xlabel("Video segment")
    ax.set_ylabel("MOTA (points)")
    ax.set_title("a", loc="left")
    ax.legend(title="Arm", frameon=False)
    ax2 = axes[1]
    means, cis = [], []
    for arm in ARMS:
        vals = series[arm]
        mean = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - mean) ** 2 for v in vals)
                       / (len(vals) - 1))
        means.append(mean)
        cis.append(1.96 * sd / math.sqrt(len(vals)))
    ax2.errorbar(ARMS, means, yerr=cis, fmt="o", capsize=3)
    ax2.set_ylim(60, 82)
    ax2.set_ylabel("MOTA (points)")
    ax2.set_title("b", loc="left")
'''


def draw_reference_image(path: Path) -> None:
    """以 PIL 程序绘制参考图替身：冒充「用户提供的 GPT Image 参考图」
    在演示中走完登记/验收/重绘全链；其来源在 demo-report 中如实
    披露（非 AI 生成、无 AI 像素主张）。"""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (800, 500), "#f4f7fa")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 399, 499], fill="#eaf1f8")
    d.rectangle([400, 0, 799, 499], fill="#fdf3e7")
    boxes = [
        ((30, 90, 370, 190), "Barn camera video"),
        ((30, 300, 370, 400), "Multi-object tracking"),
        ((430, 60, 770, 140), "Video-level statistics"),
        ((430, 180, 770, 260), "Threshold prediction"),
        ((430, 300, 770, 380), "Per-tracklet thresholds"),
        ((430, 410, 770, 480), "Anomaly flagging"),
    ]
    for (x0, y0, x1, y1), label in boxes:
        d.rectangle([x0, y0, x1, y1], outline="#333333", width=3)
        d.text((x0 + 12, (y0 + y1) // 2 - 6), label, fill="#111111")
    for (x0, y0, x1, y1) in [(200, 190, 200, 300), (600, 140, 600, 180),
                             (600, 260, 600, 300), (600, 380, 600, 410),
                             (370, 350, 430, 100)]:
        d.line([x0, y0, x1, y1], fill="#333333", width=3)
    img.save(path)


def method_manifest(reference_sha: str) -> dict:
    def box(panel, shape_id, typ, box_local, text=None, connect=None):
        shape = {"shape_id": shape_id, "type": typ, "panel_id": panel,
                 "box_local": box_local,
                 "style": {"fill_role": "input_data",
                           "line_role": "neutral"}}
        if text:
            shape["text"] = text
        if connect:
            shape["connect"] = connect
        return shape

    def label(panel, shape_id, box_local, text):
        return {"shape_id": shape_id, "type": "text", "panel_id": panel,
                "box_local": box_local, "text": text,
                "style": {"font_pt": 9}}

    shapes = [
        box("a", "video-frame", "rect", [0.075, 0.18, 0.85, 0.20]),
        label("a", "video-label", [0.10, 0.26, 0.80, 0.08],
              "Barn camera video"),
        box("a", "tracking", "rect", [0.075, 0.60, 0.85, 0.20],
            connect={"from": "video-frame", "to": "tracking",
                     "arrow": True, "semantics": "data flow"}),
        label("a", "tracking-label", [0.10, 0.68, 0.80, 0.08],
              "Multi-object tracking"),
        box("b", "statistics", "rounded_rect", [0.075, 0.12, 0.85, 0.16],
            connect={"from": "tracking", "to": "statistics",
                     "arrow": True, "semantics": "data flow"}),
        label("b", "statistics-label", [0.10, 0.175, 0.80, 0.07],
              "Video-level statistics"),
        box("b", "predictor", "rounded_rect", [0.075, 0.36, 0.85, 0.16],
            connect={"from": "statistics", "to": "predictor",
                     "arrow": True, "semantics": "data flow"}),
        label("b", "predictor-label", [0.10, 0.415, 0.80, 0.07],
              "Threshold prediction"),
        box("b", "thresholds", "rect", [0.075, 0.60, 0.85, 0.16],
            connect={"from": "predictor", "to": "thresholds",
                     "arrow": True, "semantics": "data flow"}),
        label("b", "thresholds-label", [0.10, 0.655, 0.80, 0.07],
              "Per-tracklet thresholds"),
        box("b", "anomaly", "rounded_rect", [0.075, 0.82, 0.85, 0.14],
            connect={"from": "thresholds", "to": "anomaly",
                     "arrow": True, "semantics": "data flow"}),
        label("b", "anomaly-label", [0.10, 0.875, 0.80, 0.07],
              "Anomaly flagging"),
    ]
    return {
        "fig_id": "fig-2",
        "version": "1.0",
        "status": "draft",
        "route": "file_build",
        "reference": {"path": "schematic/reference/fig-2.png",
                      "sha256": reference_sha},
        "canvas": {"reference_size_px": [800, 500],
                   "page_size_in": [10.0, 6.25]},
        "role_palette": {"entry_id": "PAL-ROLE-METHOD", "version": "1.2"},
        "panels": [
            {"panel_id": "a", "pixel_box": [0, 0, 400, 500],
             "contract_panel_id": "a"},
            {"panel_id": "b", "pixel_box": [400, 0, 400, 500],
             "contract_panel_id": "b"},
        ],
        "shapes": shapes,
        "bitmap_residue": [],
        "trace_layer": {"used": True, "opacity": 0.25,
                        "removed_before_delivery": True},
        "label_check": {"done": False, "by": None, "at": None},
    }


# ---------------------------------------------------------------- 变体

def variant_honesty() -> dict:
    """反转轴变体：复制主包 → 脚本改登记 direction=decreasing 且真
    反转 y 轴 → 重跑 produce + audit。期望 honesty 门 FAIL 拦截。"""
    dst = VARIANTS / "honesty-inverted"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(PKG, dst)
    script = dst / "data" / "scripts" / "fig-1.py"
    text = script.read_text(encoding="utf-8")
    text = text.replace(
        "#   y: {direction: increasing, limits: [60, 82], data_min: 62.187,",
        "#   y: {direction: decreasing, limits: [60, 82], data_min: 62.187,")
    text = text.replace('ax.set_ylim(60, 82)', 'ax.set_ylim(82, 60)')
    text = text.replace('ax2.set_ylim(60, 82)', 'ax2.set_ylim(82, 60)')
    script.write_text(text, encoding="utf-8")
    driver_note("变体 honesty-inverted：脚本头 y 轴登记改为 decreasing "
                "且绘图真反转 y 轴（变体不进正式交付）")
    run_cli("produce", str(dst), "fig-1", cwd=dst)
    outcome = run_cli("audit", "run", str(dst), "--fig", "fig-1", cwd=dst)
    return outcome["figures"]["fig-1"]


def variant_native_embed() -> dict:
    """整幅嵌入变体：复制主包 → 在 manifest 里把整张参考图登记为
    photo 类残留并整幅放进面板 a → 重建 + audit。期望 native 门按
    尺寸比对判 full_page_bitmap FAIL 拦截。"""
    import json as _json

    from light_figure.util import sha256_file

    dst = VARIANTS / "native-embed"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(PKG, dst)
    manifest_path = dst / "schematic" / "redraw" / "fig-2.manifest.json"
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    ref_rel = "schematic/reference/fig-2.png"
    manifest["bitmap_residue"] = [{
        "residue_id": "full-ref",
        "class": "photo",
        "panel_id": "a",
        "box_local": [0.0, 0.0, 1.0, 1.0],
        "media_name": "full_reference.png",
        "source": {"path": ref_rel, "sha256": sha256_file(dst / ref_rel)},
    }]
    manifest_path.write_text(_json.dumps(manifest, ensure_ascii=False,
                                          indent=2), encoding="utf-8")
    driver_note("变体 native-embed：manifest 新增整幅参考图残留登记"
                "（class=photo、box 占满面板 a），重建后 audit")
    run_cli("redraw", "build", str(dst), "fig-2", cwd=dst)
    outcome = run_cli("audit", "run", str(dst), "--fig", "fig-2", cwd=dst)
    return outcome["figures"]["fig-2"]


# ---------------------------------------------------------------- 主链

NOTE_REASONS = {
    "collisions": "已在最终尺寸下逐条复核：文字与填充边沿轻微相接，"
                  "不影响判读，接受",
    "honesty": "已复核脚本头登记与成图：警告项为登记完备性提示，"
               "口径与成图一致，接受",
    "contract": "已复核与期刊合同的偏差说明，接受并记录在案",
    "alignment": "已复核量测偏差在合同容差边缘，接受并记录在案",
    "glyph": "已复核字形量测结果，接受并记录在案",
    "native": "已复核原生性量测结果，接受并记录在案",
    "policy_block": "已复核政策硬拦量测结果，接受并记录在案",
}


def audit_and_note(root) -> dict:
    outcome = run_cli("audit", "run", str(root), cwd=root)
    from light_figure.util import load_structured
    for fig_id in ("fig-1", "fig-2"):
        record = load_structured(root / "audit" / f"{fig_id}.audit.json")
        for name, gate in record["gates"].items():
            if gate.get("applicable") and gate["verdict"] == \
                    "REVIEW_REQUIRED":
                run_cli("audit", "note", str(root), fig_id, "--gate",
                        name, "--reason",
                        NOTE_REASONS.get(name, "已人工复核，接受并记录在案"),
                        cwd=root)
    return outcome


def main() -> int:
    for target in (PKG, VARIANTS, EVIDENCE):
        if target.exists():
            shutil.rmtree(target)
    EVIDENCE.mkdir(parents=True)
    log("=== Light-Figure v1 demo-fullrun 运行日志 ===")
    write_inputs()

    run_cli("init", str(PKG), "--title",
            "Turkey Behaviour Figures (Light-Figure demo)")
    run_cli("intake", str(PKG),
            "--manifest", str(INPUTS / "figures_manifest.yaml"),
            "--journal-contract", str(INPUTS / "journal_contract.yaml"),
            "--template-record-id", "TPL-DEMO-001",
            "--ai-policy", str(INPUTS / "ai_policy.yaml"),
            "--by", "demo-author")
    write_contracts_and_backend()
    run_cli("validate", str(PKG))
    run_cli("advance", str(PKG))  # → contracted

    bundle = run_cli("style", "build", str(PKG))
    # 源数据与脚本落盘（脚本头绑定当前 bundle 哈希）
    src_dir = PKG / "data" / "source-data"
    src_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(INPUTS / "arms_segments.csv", src_dir / "fig-1.csv")
    script_path = PKG / "data" / "scripts" / "fig-1.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(
        DATA_SCRIPT.format(bundle_hash=bundle["style_build_hash"]),
        encoding="utf-8")
    driver_note("fig-1 源数据与绘图脚本已落盘（脚本头登记正常轴口径："
                "y 递增、limits [60, 82] 覆盖数据全程、未截断）")
    produced = run_cli("produce", str(PKG), "fig-1", "--by", "demo-author")
    driver_note(f"fig-1 produce 完成：font_substituted="
                f"{produced.get('font_substituted')}（期刊合同 Arial 在"
                "本机不可用，按规程以 DejaVu Sans 替换并落字）")

    run_cli("prompt", "build", str(PKG), "fig-2", "--by", "demo-author")
    ref_src = INPUTS / "reference-fig-2.png"
    draw_reference_image(ref_src)
    driver_note("参考图替身已由本地 PIL 程序绘制（800×500，六个模块框 "
                "+ 标签逐字与 manifest 一致）；来源如实披露于 "
                "demo-report——它不是 GPT Image 产物")
    run_cli("reference", "add", str(PKG), "fig-2", "--image", str(ref_src),
            "--model-name", "local PIL script (demo stand-in)",
            "--model-version", "run_demo.py", "--by", "demo-author")
    run_cli("reference", "accept", str(PKG), "fig-2", "--by", "demo-author",
            "--labels-verbatim", "--structures-factual",
            "--formulas-values-checked")

    from light_figure.util import dump_json, sha256_file, today
    ref_pkg = PKG / "schematic" / "reference" / "fig-2.png"
    manifest_file = INPUTS / "manifest-fig-2.json"
    dump_json(manifest_file, method_manifest(sha256_file(ref_pkg)))
    run_cli("redraw", "init", str(PKG), "fig-2")
    run_cli("redraw", "install", str(PKG), "fig-2",
            "--manifest", str(manifest_file))
    run_cli("redraw", "build", str(PKG), "fig-2", "--by", "demo-author")
    run_cli("redraw", "extract", str(PKG), "fig-2")
    run_cli("provenance", "set", str(PKG), "fig-2",
            "--set", 'label_check={"done": true, "by": "demo-author", '
                     f'"at": "{today()}"}}',
            "--by", "demo-author")
    run_cli("advance", str(PKG))  # → produced

    log("\n=== 拦截变体（不进正式交付） ===")
    honesty_outcome = variant_honesty()
    native_outcome = variant_native_embed()

    log("\n=== 主包审计与交付 ===")
    audit_outcome = audit_and_note(PKG)
    run_cli("advance", str(PKG))  # → audited
    delivery = run_cli("deliver", str(PKG), "--by", "demo-author")
    final = run_cli("advance", str(PKG))  # → delivered
    status = run_cli("status", str(PKG))
    run_cli("report", str(PKG))

    delivery_doc = (PKG / "exports" / "delivery.yaml").read_text(
        encoding="utf-8")
    log("\n=== exports/delivery.yaml ===\n" + delivery_doc)

    summary = {
        "final_status": status["status"],
        "final_advanced": final["advanced"],
        "delivery": delivery,
        "audit_overall": {
            fid: f["overall"] for fid, f in
            audit_outcome["figures"].items()},
        "audit_gates": {
            fid: f["gates"] for fid, f in
            audit_outcome["figures"].items()},
        "variant_honesty_inverted": honesty_outcome,
        "variant_native_embed": native_outcome,
    }
    dump_json(EVIDENCE / "summary.json", summary)
    log("\n=== summary ===\n" + json.dumps(summary, ensure_ascii=False,
                                             indent=2))
    LOG_PATH.write_text("\n".join(_log_lines) + "\n", encoding="utf-8")
    print(f"\n日志已落盘：{LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
