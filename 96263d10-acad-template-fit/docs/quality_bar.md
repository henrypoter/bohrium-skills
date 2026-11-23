# 成稿质量基线（"一份好成稿长什么样"）

SKILL.md §2 的扩展版：主路径只需照这张表产稿，`fit_check.py` 只是事后复核。目标值以**模板/规范实测**为准，本表给的是模板没写时的默认档与常见体裁档。

## 1. 目标值全表

| 项 | 默认/常见目标值 | 校验依据（脚本能否自动判） |
|-|-|-|
| 纸张 | A4 210×297mm；Letter 216×279mm；B5 176×250mm | `page.size` pass/fail |
| 页边距 | 学位论文：上下 2.54cm、左右 3.0cm；IEEE 会议：四边 0.75in；期刊：按 guide | `page.margin_*` 自动（cm/mm/in 归一到 cm，误差 ≤0.05cm） |
| 正文字号 | 10/11/12pt 三选一；中文小四=12pt、五号=10.5→11pt、小三=15pt | `body.font_size` 自动（中文字号名映射） |
| 行距 | 1.0（单倍）/1.15/1.25/1.5（1.5 倍）/2.0（双倍）；全篇只保留一处设定 | `body.line_spacing` 自动 |
| 栏数 | 单栏（学位论文、中文期刊、多数 preprint）或双栏（IEEE/ACM/会议）；全篇一致 | `page.columns` 自动 |
| 标题层级 | 一级 `\section`、二级 `\subsection`、三级 `\subsubsection`；编号由 LaTeX 生成，正文不手打"1 引言"；目录/书签随之生成 | 未自动（`unverified_items`），产稿时按此写 |
| 图题 | 图**下**方，`Figure N:` / `图 N`，9–10pt，与正文空 6pt；`\label{fig:x}` + `\ref` 可解析、编号连续 | `caption.figure.position` 自动 |
| 表题 | 表**上**方，`Table N:` / `表 N`，9–10pt；三线表（顶线/表头线/底线，无竖线） | `caption.table.position` 自动；三线表未自动 |
| 参考文献 | GB/T 7714-2015（中文期刊/学位论文）、IEEE、APA、Vancouver；字段顺序与作者截断随样式；正文 `\cite` 与条目一一对应，无悬空引用 | `refs.style` 自动（归一化匹配）；条目字段未自动 |
| 页眉页脚 | 页码连续可见；模板未要求页眉则不加；页眉文字与模板一致 | 未自动 |
| 交付物 | `/app/output` 有可编辑源（`.tex`/`.docx`）+ 同名 `.pdf`；PDF 可打开、字体无缺字形、页数与上限相符 | `compile.ok` / `pages` 自动 |

## 2. 逐项对照示例（坏稿 → 成稿）

页边距与纸张

```
坏：\documentclass[10pt,twocolumn,letterpaper]{article}
    \usepackage[margin=1in]{geometry}
好：\documentclass[12pt,a4paper]{article}
    \usepackage[top=2.54cm,bottom=2.54cm,left=3cm,right=3cm]{geometry}
```

字体与行距（organizer font revision3：Times 不可用，改 Liberation Serif）

```
坏：\usepackage{times}  \onehalfspacing
好：\usepackage{fontspec}\setmainfont{Liberation Serif}  \linespread{1.5}
```

标题层级（别只加粗/放大字号）

```
坏：\textbf{1 引言}        % 手打序号，不进目录，交叉引用断
好：\section{引言}\label{sec:intro}   % 编号/目录/书签由 LaTeX 生成
```

图题与交叉引用

```
坏：\begin{figure}\caption{结果}\includegraphics[width=.8\linewidth]{fig1}\end{figure}
    正文"见图 1"（手写号码，插图顺序一变就错）
好：\begin{figure}\centering\includegraphics[width=.8\linewidth]{fig1}
      \caption{结果}\label{fig:res}\end{figure}
    正文"见图~\ref{fig:res}"
```

三线表

```
坏：\begin{tabular}{|c|c|c|}\hline ... \hline\end{tabular}
好：\begin{tabular}{ccc}\toprule 方法 & 精度 & 召回 \\ \midrule ... \\ \bottomrule\end{tabular}
```

参考文献

```
坏：\bibliographystyle{plain}   % 与 GB/T 7714 规范不符
好：\bibliographystyle{gbt7714} \bibliography{refs}   % 缺 .bst 时脚本会告警（不阻断）
```

## 3. 成稿自检四问（产完立刻问自己）

1. `/app/output` 里有没有**能打开的同名 PDF**？没有 → 先补渲染，再谈其它。
2. 七项硬规格（纸张/页边距/字号/行距/栏数/文献样式/图表题注位置）是否与 guide 逐项对得上？对不上 → 回 `tpl_fit` 或手改，再重跑。
3. 内容单元（图/表/公式/脚注/引用/章节）计数有没有变？变了 → 查 `compliance.json` 的 `fidelity`，别把"改格式"做成"改内容"。
4. 每个没核到的项是否写进了 `uncertainty`（而不是假装已核）？

## 4. 与检查的关系

本表是**产稿时的写作目标**，不是事后评分表：先按目标值一次写对，`fit_check.py` 的 fail 才会少，返工才会 ≤1 轮。检查结论永远只进 `uncertainty`/`compliance.json`，不阻断成稿交付。
