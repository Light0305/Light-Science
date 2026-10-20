"""light-patent 端到端演示驱动（离线、脱敏、自造案例）。

主线：火鸡行为检测项目中一项尚未公开的改进方案（时序融合 +
个体基线偏差），团队已发表的基础论文作为最接近现有技术 D1
如实登记。全程走本包命令面对应的模块函数，关键纪律点各留
实证：P0 审计先行、未核验条目拒锁 D1、植入不确定词被检查器
咬住后修正过检、第 33 条出处修改、会稿问题清单导出。

运行：python run_demo.py（产物落同目录 case/，可整删重跑）
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from light_patent import check, draft, intake, ledger, novelty, oa  # noqa: E402
from light_patent.project import PatentError, init_package, load_case  # noqa: E402
from light_patent.validate import validate_package  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE / "case"
TITLE = "一种基于时序融合的家禽异常行为检测方法"
PAPER_DOI = "DOI:10.1016/j.compag.2025.110856"

log = []


def step(name, obj):
    log.append({"step": name, "result": obj})
    print(f"[{name}] {json.dumps(obj, ensure_ascii=False)[:300]}")


def main():
    if ROOT.exists():
        shutil.rmtree(ROOT)
    case = init_package(ROOT, TITLE, ai_related=True)
    step("init", {"case_id": case["case_id"], "status": case["status"]})

    # P0：改进方案本身无在先公开，具名确认；基础论文是现有技术
    # 背景，不构成本案发明点的公开（其公开状态在查新池如实登记）。
    audit = intake.run_audit(ROOT, {
        "confirmed_complete": True, "examiner": "演示登记人（项目成员）",
        "ethics_flags": ["数据采集"],
        "ethics_review": {"conclusion": "通过自查",
                          "basis": "舍内动物行为视频，不含个人信息与推荐决策"},
        "disclosures": []})
    step("P0 audit", {"conclusion": audit["conclusion"]})

    # P1：代码盘点 + 源图谱 + 三候选选最强
    scan = intake.scan_code(ROOT, HERE / "inputs" / "repo")
    step("P1 scan-code", {"files": scan["files"], "anchors": scan["anchors"]})
    intake.register_sources(ROOT, {"sources": [
        {"kind_prefix": "P", "route": "paper", "ref": "内部技术记录 TN-07 第 2-4 节",
         "note": "未公开改进方案记录"},
        {"kind_prefix": "E", "route": "experiment", "ref": "实验日志 R-31",
         "note": "个体基线偏差公式与消融结果"},
        {"kind_prefix": "F", "route": "paper", "ref": "系统框图 v3",
         "note": "装置实施例结构图"},
        {"kind_prefix": "P", "route": "oral", "ref": "交底访谈纪要 2026-10-18",
         "note": "口头交底补充，仅作补充输入"},
    ]})
    mined = intake.register_candidates(ROOT, {
        "selected": "CAND-1",
        "candidates": [
            {"candidate_id": "CAND-1", "title": "时序融合加个体基线偏差检测",
             "technical_problem": "单帧分类误报率高、群体统一阈值不适配个体差异",
             "technical_means": "时序融合模型提取行为特征向量，按个体基线分布偏差计异常分数",
             "technical_effect": "降低误报，异常分数可分级报警",
             "evidence": [{"anchor": "P001"}, {"anchor": "E001"}],
             "claim_category": "方法加装置加介质",
             "gaps": ["报警联动接口参数未定"],
             "risks": ["与团队已发表单帧方案贴近，靠区别特征拉开"]},
            {"candidate_id": "CAND-2", "title": "多摄像头拼接跟踪",
             "technical_problem": "单摄像头遮挡丢失个体",
             "technical_means": "跨摄像头轨迹拼接",
             "technical_effect": "减少轨迹断裂",
             "evidence": [{"anchor": "P001"}],
             "claim_category": "方法",
             "gaps": ["拼接标定流程未定型"],
             "risks": ["实施细节不足，降为后备案"]},
            {"candidate_id": "CAND-3", "title": "报警分级推送策略",
             "technical_problem": "报警过多导致值班疲劳",
             "technical_means": "按异常分数分级推送",
             "technical_effect": "减少无效报警打扰",
             "evidence": [{"anchor": "P002"}],
             "claim_category": "方法",
             "gaps": ["分级阈值待实验标定"],
             "risks": ["单独成案创造性弱，并入主案从属特征"]},
        ]})
    step("P1 mine", mined)
    return case


def part2():
    # P2：两轮召回登记。已发表基础论文如实入池（团队自有在先公开）。
    novelty.register_search(ROOT, {
        "round": "means_phrases", "channel_id": "cnipa-epub-manual",
        "query": "IPC:G06V AND 家禽行为检测", "outcome": "ok",
        "results": [
            {"pub_number": PAPER_DOI,
             "title": "Abnormal turkey behaviour detection (团队已发表基础论文)",
             "applicant": "本团队", "pub_date": "2025",
             "url": "https://doi.org/10.1016/j.compag.2025.110856",
             "verified": True, "evidence_level": "full_text", "relevance": 5},
            {"pub_number": "CN118765432A", "title": "一种基于视频分析的畜禽异常报警方法",
             "applicant": "某农业科技公司", "pub_date": "2024-06-01",
             "url": "https://example.invalid/CN118765432A",
             "verified": True, "evidence_level": "abstract", "relevance": 3},
            {"pub_number": "CN119000111A", "title": "一种动物行为识别装置",
             "applicant": "待核", "pub_date": "", "url": "",
             "verified": False, "evidence_level": "abstract", "relevance": 4},
        ]})
    novelty.register_search(ROOT, {
        "round": "classification_neighborhood",
        "channel_id": "cnipa-epub-manual",
        "query": "IPC:G06V10 AND 行为检测", "outcome": "ok", "results": []})
    # 纪律实证：未核验条目拒锁 D1
    try:
        novelty.lock_d1(ROOT, {
            "pub_number": "CN119000111A", "rationale": "相关度高",
            "evidence_level": "abstract", "gate": "pass",
            "feature_comparison": [{"feature_ref": "CF-02", "in_d1": False}]})
        step("P2 lock unverified", {"unexpected": "未被拒绝"})
    except PatentError as exc:
        step("P2 lock unverified rejected", {"gaps": exc.gaps})
    locked = novelty.lock_d1(ROOT, {
        "pub_number": PAPER_DOI,
        "rationale": "团队已发表基础论文公开了单帧分类全流程，与本案同问题同场景，为最接近现有技术",
        "evidence_level": "full_text", "gate": "pass_with_doubts",
        "gate_reasons": ["区别特征组合（时序融合加个体基线）未被公开，创造性终局留代理师复核"],
        "feature_comparison": [
            {"feature_ref": "CF-01", "claim_feature": "抽帧序列", "in_d1": True,
             "note": "基础论文已公开"},
            {"feature_ref": "CF-02", "claim_feature": "时序融合模型", "in_d1": False,
             "contribution": "对误报问题有贡献", "note": "基础论文为单帧分类"},
            {"feature_ref": "CF-03", "claim_feature": "个体基线偏差异常分数",
             "in_d1": False, "contribution": "对误报问题有贡献",
             "note": "基础论文用群体统一阈值"},
        ]})
    step("P2 lock D1", locked)

    # P3：撰写。v1 故意在权要 2 植入不确定词「优选」，供 P4 咬合实证。
    from conftest_payloads import claims_payload, spec_text, abstract_text
    payload = claims_payload()
    # 演示中 scan-code 锚点按文件名序生成：C002 为 tracker/fusion.py
    payload["claims"][1]["features"][0]["support"]["anchors"] = ["C002"]
    payload["claims"][1]["features"][0]["text"] = \
        "时序融合检测模型中的时序聚合模块优选采用滑动窗口注意力对视频帧序列进行加权聚合"
    draft.register_claims(ROOT, payload)
    (HERE / "_spec.md").write_text(spec_text(), encoding="utf-8")
    (HERE / "_abstract.md").write_text(abstract_text(), encoding="utf-8")
    draft.register_text(ROOT, "specification", HERE / "_spec.md")
    draft.register_text(ROOT, "abstract", HERE / "_abstract.md")
    draft.register_numerals(ROOT, {"numerals": [
        {"mark": "1", "name": "视频采集单元", "description": "采集舍内视频"},
        {"mark": "2", "name": "处理单元", "description": "运行检测模型"}]})
    draft.register_gaps(ROOT, {"gaps": [
        {"item": "报警联动接口参数", "location": "说明书实施例三"}]})
    report1 = check.run_check(ROOT)
    step("P4 check v1 (planted flaw)", {
        "errors": report1["errors"], "grade": report1["delivery_grade"],
        "bite": [f["detail"] for f in report1["findings"]
                 if f["check_id"] == "C-03"]})
    # 修正后重登记、剥离申报副本、红队落账、复检
    draft.register_claims(ROOT, claims_payload())
    stripped = draft.strip_filing(ROOT)
    step("P3 strip filing", stripped)
    check.register_redteam(ROOT, {
        "claims_team": {"checked": ["新颖性", "创造性三步法", "客体"],
                        "not_checked": ["同族检索"],
                        "findings": [{"point": "独权区别特征组合成立",
                                      "severity": "info"}]},
        "package_team": {"checked": ["跨文件一致性", "哈希时序", "正文洁净"],
                         "not_checked": [], "findings": []}})
    report2 = check.run_check(ROOT)
    step("P4 check v2", {"errors": report2["errors"],
                         "warnings": report2["warnings"],
                         "grade": report2["delivery_grade"]})

    worth = ledger.set_worth_it(ROOT, {
        "verdict": "file_narrowed",
        "rationale": "区别特征组合有实验支撑，值得以收窄独权申请；多摄像头拼接另行立项",
        "evidence": [{"ref": "novelty/d1.yaml"},
                     {"ref": "intake/candidates.yaml"},
                     {"ref": "check/check_report.yaml"}]})
    step("P6 worth-it", {"verdict": worth["verdict"]})
    filed = ledger.register_filing(ROOT, {
        "application_no": "CN202610000000.X（演示模拟号）",
        "filing_date": "2026-10-22"})
    step("P6 filing (simulated)", filed)

    # P5：模拟审查意见 + 第 33 条出处修改 + 会稿清单导出
    oa.register_office_action(ROOT, {
        "action_id": "OA-1（演示模拟）", "notified_at": "2027-03-01",
        "response_months": 4,
        "defects": [{"defect_id": "D-1", "article": "专利法第 22 条第 3 款",
                     "claim_refs": [1], "cited_docs": [PAPER_DOI],
                     "summary": "审查员认为权要 1 相对 D1 与公知常识结合不具创造性"}]})
    amended = oa.register_amendment(ROOT, {
        "amendment_id": "AM-1", "target": "权利要求 1",
        "before": "时序聚合特征在从属权要 2",
        "after": "将滑动窗口注意力时序聚合特征并入权利要求 1",
        "defect_ref": "D-1", "basis_pointer": "原权利要求 2",
        "basis_quote": "时序聚合模块采用滑动窗口注意力对视频帧序列进行加权聚合",
        "art33_checked": True})
    step("P5 amendment", amended)
    meeting = oa.export_meeting_questions(ROOT)
    step("P5 meeting questions", meeting)
    result = validate_package(ROOT)
    step("validate", {"ok": result["ok"], "errors": result["errors"],
                      "status": result["status"]})
    step("final status", {"status": load_case(ROOT)["status"]})


if __name__ == "__main__":
    main()
    part2()
    print(json.dumps({"steps": len(log)}, ensure_ascii=False))
