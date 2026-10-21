# Vendored: vsdx 0.6.1

- 上游: dave-howard/vsdx — https://github.com/dave-howard/vsdx
- 作者: Dave Howard (dave@codypy.com)
- 版本: 0.6.1(钉死;升级须重走本文件的核对流程并更新哈希表)
- 许可: BSD 3-Clause License, Copyright (c) 2020 Dave Howard
  (全文见同目录 LICENSE;再分发须保留版权声明与免责条款,BSD-3
  第 1/2 条——本目录与包文档 SKILL §16.2 的署名即为此设)
- 来源工件: PyPI wheel `vsdx-0.6.1-py3-none-any.whl`
  SHA-256 = ec52e8d3453850ba12ee2cd16d1bf20f2cc55e44583d0ec73f481099786ca7bb
- 收编方式: 自 wheel 解出 `vsdx/` 包本体逐字节复制,**源文件零
  改动**;本地适配只在加载层(vsdxpost.load_vendored_vsdx):
  以顶层名 vsdx 注册进 sys.modules 后执行(vsdx 内部以绝对名
  自引用,此为上游预期形态),加载前断言 __version__ == 0.6.1。
- 依赖处置: 上游声明依赖 Jinja2 与 deprecation。本包只用其
  .vsdx 读写/改字改色/diff 面,不用 Jinja 模板渲染;两依赖缺位
  时由加载层注册惰性占位(用到模板/弃用装饰路径才报错点名),
  不许因无关依赖缺位拖垮后处理主面;装有真依赖时优先用真的。
- 用途: Visio 文件级后处理格(改字/改色/抽取/diff),命令面为
  `redraw post` 命令组(vsdxpost.py);不承担从零重建(SKILL
  §16.2 后处理格口径)。

## 逐文件 SHA-256(与 wheel 内工件逐字节核对,2026-10-21)

    __init__.py        f67c308f5476cf706bac7eddc7580dab00f6e05c432b4a0923b818e19957a7e0
    connectors.py      4846f276359292c8f16ed000a6d8eb3136ba97285f5bbd8e0f81f2ee12f10764
    formulae.py        d1960a944fd47c4df429382702216b54407d3c49ffd95133c78c98c2d2a80519
    geometry.py        d5ae7ecfd5f94378d11607de0fc5454f49b130a5db675806921e0f3f9342cc46
    media.py           fad5833d471ee2a52447abe3331f58b9570db88c981ab3d258ea4e378457ab5c
    pages.py           79a7c67a6b7905b7553deae439931f8b7048f06ebc169578a61c4cb81f3248ad
    shapes.py          960f9c24e8a867e6af94383548398eec13cd7c028490b7e5111b220df2accde3
    vsdxdiff.py        d394c1c9767ea8b84b6acffd1390ed0065a16fc70c57f4084a02db629101bfd8
    vsdxfile.py        e1c0811546c65f9400bcb803d3f263abd7d441592075a96251cd352e3b9ab8bf
    media/media.vsdx   f5ead22055be37b867a858cf94f1ecca4fe06d954c7c39f44cca72958a4410af
    LICENSE            8635bc8d4455bf416d640ab4b79f800a05a862c59b748c215e0ff4a4e2e319c6
