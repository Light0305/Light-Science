"""共享夹具：把案件驱动到各阶段的辅助函数与标准载荷。

主线案例为自造脱敏案例（未公开的家禽行为检测改进方案），与
演示同源；全部离线，不碰任何外部网络与真实渠道。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from light_patent import draft, intake, novelty
from light_patent.project import init_package

TITLE = "一种基于时序融合的家禽异常行为检测方法"

SPEC_TEXT = """# 说明书

## 技术领域
本发明涉及家禽养殖监测领域，具体涉及一种基于时序融合的家禽异常行为检测方法。

## 背景技术
现有舍内监控多采用单帧图像分类，难以刻画行为的时序变化。

## 发明内容
本发明获取舍内监控视频流并按固定帧间隔抽取视频帧序列，将视频帧序列输入时序融合检测模型得到每只家禽个体的行为特征向量，其中时序融合检测模型包含空间特征提取模块与时序聚合模块；根据行为特征向量与个体基线行为分布之间的偏差量计算异常分数；当异常分数超过自适应阈值时输出异常行为报警信息，其中自适应阈值由个体基线行为分布的统计量确定。时序聚合模块采用滑动窗口注意力对视频帧序列进行加权聚合。

## 附图说明
图1为系统结构示意图，其中1为视频采集单元，2为处理单元。

## 具体实施方式
实施例一：视频采集单元1采集舍内视频，处理单元2运行检测模型。模型的空间特征提取模块为卷积主干网络，时序聚合模块与空间特征提取模块串联连接；训练步骤包括以标注行为片段为样本、按交叉熵损失迭代更新参数，训练参数含学习率与窗口长度；模型输入为视频帧序列，输出为行为特征向量与异常分数，输入输出的对应关系由个体编号绑定。
实施例三：报警联动接口参数待补充：报警联动接口参数。

## 撰写说明
本段为过程记录，申报副本中应被剥离。支持状态与查新过程只记于此。

<!-- 过程批注：源锚点 P001 对应内部记录 -->
"""

ABSTRACT_TEXT = """# 说明书摘要

本发明公开一种基于时序融合的家禽异常行为检测方法，获取舍内监控视频帧序列，输入包含空间特征提取与时序聚合的检测模型得到行为特征向量，按与个体基线分布的偏差计算异常分数，超过自适应阈值时输出报警信息，可降低单帧误报。
"""


def claims_payload():
    return {
        "ai_sufficiency": {"items": [
            "model_modules", "model_levels_links", "training_steps_params",
            "input_output_setting", "scenario_binding"]},
        "claims": [
            {"claim_no": 1, "type": "method", "depends_on": [],
             "preamble": "一种家禽异常行为检测方法，包括：",
             "features": [
                 {"feature_ref": "CF-01", "box": "necessary",
                  "text": "获取舍内监控视频流并按固定帧间隔抽取视频帧序列",
                  "support": {"state": "explicit", "anchors": ["P001"],
                              "spec_section": "发明内容"}},
                 {"feature_ref": "CF-02", "box": "necessary",
                  "text": "将视频帧序列输入时序融合检测模型得到每只家禽个体的行为特征向量，其中时序融合检测模型包含空间特征提取模块与时序聚合模块",
                  "support": {"state": "explicit", "anchors": ["P001", "E001"],
                              "spec_section": "发明内容"}},
                 {"feature_ref": "CF-03", "box": "necessary",
                  "text": "根据行为特征向量与个体基线行为分布之间的偏差量计算异常分数",
                  "support": {"state": "explicit", "anchors": ["E001"],
                              "spec_section": "发明内容"}},
                 {"feature_ref": "CF-04", "box": "necessary",
                  "text": "当异常分数超过自适应阈值时输出异常行为报警信息，其中自适应阈值由个体基线行为分布的统计量确定",
                  "support": {"state": "inherent", "anchors": ["P001"],
                              "spec_section": "发明内容"}},
             ]},
            {"claim_no": 2, "type": "method", "depends_on": [1],
             "preamble": "根据权利要求1所述的家禽异常行为检测方法，其特征在于：",
             "features": [
                 {"feature_ref": "CF-05", "box": "embodiment_choice",
                  "text": "时序融合检测模型中的时序聚合模块采用滑动窗口注意力对视频帧序列进行加权聚合",
                  "support": {"state": "explicit", "anchors": ["C001"],
                              "spec_section": "具体实施方式"}},
             ]},
            {"claim_no": 3, "type": "apparatus", "depends_on": [],
             "preamble": "一种家禽异常行为检测装置，包括：",
             "features": [
                 {"feature_ref": "CF-06", "box": "necessary",
                  "text": "视频采集单元，用于获取舍内监控视频流并按固定帧间隔抽取视频帧序列",
                  "support": {"state": "explicit", "anchors": ["F001"],
                              "spec_section": "附图说明"}},
                 {"feature_ref": "CF-07", "box": "necessary",
                  "text": "处理单元，用于运行权利要求1所述方法中的时序融合检测模型并输出异常行为报警信息",
                  "support": {"state": "explicit", "anchors": ["F001"],
                              "spec_section": "附图说明"}},
             ]},
            {"claim_no": 4, "type": "medium", "depends_on": [],
             "preamble": "一种计算机可读存储介质，其上存储有计算机程序，",
             "features": [
                 {"feature_ref": "CF-08", "box": "necessary",
                  "text": "该程序被处理器执行时实现权利要求1所述的方法步骤",
                  "support": {"state": "explicit", "anchors": ["C001"],
                              "spec_section": "具体实施方式"}},
             ]},
        ],
    }


@pytest.fixture()
def case_root(tmp_path):
    root = tmp_path / "case"
    init_package(root, TITLE, ai_related=True)
    return root


def audit_clear(root):
    return intake.run_audit(root, {
        "confirmed_complete": True, "examiner": "测试登记人",
        "ethics_flags": ["数据采集"],
        "ethics_review": {"conclusion": "通过自查",
                          "basis": "舍内动物行为数据，不含个人信息"},
    })


def drive_to_mined(root):
    audit_clear(root)
    intake.register_sources(root, {"sources": [
        {"kind_prefix": "P", "route": "paper", "ref": "内部技术记录 TN-01 第 3 节",
         "note": "未公开改进方案记录"},
        {"kind_prefix": "E", "route": "experiment", "ref": "实验日志 R-12",
         "note": "偏差量公式来源"},
        {"kind_prefix": "F", "route": "paper", "ref": "系统框图 v2",
         "note": "装置结构图"},
        {"kind_prefix": "C", "route": "code", "anchor": "C001",
         "ref": "tracker/fusion.py", "note": "时序融合实现"},
    ]})
    intake.register_candidates(root, {
        "selected": "CAND-1",
        "candidates": [{
            "candidate_id": "CAND-1", "title": "时序融合异常检测",
            "technical_problem": "单帧分类误报率高",
            "technical_means": "时序融合模型加个体基线偏差",
            "technical_effect": "降低误报并给出异常分数",
            "evidence": [{"anchor": "P001"}, {"anchor": "E001"}],
            "claim_category": "方法加装置加介质",
            "gaps": ["报警联动接口参数未定"],
            "risks": ["与单帧检测现有技术贴近"],
        }],
    })
    return root


def drive_to_searched(root):
    drive_to_mined(root)
    novelty.register_search(root, {
        "round": "means_phrases", "channel_id": "cnipa-epub-manual",
        "query": "IPC:G06V AND 家禽行为检测", "outcome": "ok",
        "results": [
            {"pub_number": "CN111111111A", "title": "一种禽类行为识别方法",
             "applicant": "某大学", "pub_date": "2023-05-01",
             "url": "https://example.invalid/CN111111111A",
             "verified": True, "evidence_level": "full_text", "relevance": 5},
            {"pub_number": "CN222222222A", "title": "一种畜禽监控系统",
             "applicant": "某公司", "pub_date": "2024-01-15",
             "url": "https://example.invalid/CN222222222A",
             "verified": True, "evidence_level": "abstract", "relevance": 3},
            {"pub_number": "CN333333333A", "title": "一种动物异常报警方法",
             "applicant": "待核", "pub_date": "",
             "url": "", "verified": False,
             "evidence_level": "abstract", "relevance": 4},
        ]})
    novelty.register_search(root, {
        "round": "classification_neighborhood",
        "channel_id": "cnipa-epub-manual",
        "query": "IPC:G06V10 AND 行为检测", "outcome": "ok", "results": []})
    novelty.lock_d1(root, {
        "pub_number": "CN111111111A",
        "rationale": "同为禽类视频行为识别且公开单帧分类全流程，最接近",
        "evidence_level": "full_text", "gate": "pass_with_doubts",
        "gate_reasons": ["时序融合与个体基线组合未被公开，留代理师复核"],
        "feature_comparison": [
            {"feature_ref": "CF-01", "claim_feature": "抽帧序列",
             "in_d1": True, "note": "D1 已公开"},
            {"feature_ref": "CF-02", "claim_feature": "时序融合模型",
             "in_d1": False, "contribution": "对误报问题有贡献",
             "note": "D1 为单帧分类"},
            {"feature_ref": "CF-03", "claim_feature": "个体基线偏差异常分数",
             "in_d1": False, "contribution": "对误报问题有贡献",
             "note": "D1 用群体统一阈值"},
        ]})
    return root


def drive_to_drafted(root, tmp_path):
    drive_to_searched(root)
    draft.register_claims(root, claims_payload())
    spec_src = Path(tmp_path) / "spec.md"
    spec_src.write_text(SPEC_TEXT, encoding="utf-8")
    abs_src = Path(tmp_path) / "abstract.md"
    abs_src.write_text(ABSTRACT_TEXT, encoding="utf-8")
    draft.register_text(root, "specification", spec_src)
    draft.register_text(root, "abstract", abs_src)
    draft.register_numerals(root, {"numerals": [
        {"mark": "1", "name": "视频采集单元", "description": "采集舍内视频"},
        {"mark": "2", "name": "处理单元", "description": "运行检测模型"},
    ]})
    draft.register_gaps(root, {"gaps": [
        {"item": "报警联动接口参数", "location": "说明书实施例三"}]})
    return root
