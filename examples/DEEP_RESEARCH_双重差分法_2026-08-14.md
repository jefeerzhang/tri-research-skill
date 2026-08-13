# 双重差分法的最新理论进展与经验研究（2020—2026）

## 概述

双重差分法（DiD）是政策评估与因果推断中应用最广的准实验方法。2020 年以来的一系列研究指出：当处理时点交错、处理效应存在异质性时，传统双向固定效应（TWFE）估计量会产生系统性偏误甚至负权重，这被称为"DiD 革命"[1][2][12]。此后发展出以 Callaway-Sant'Anna、Sun-Abraham、Borusyak 插补等为代表的新一代异质性稳健估计量，平行趋势检验的规范也随之改写[5][6][7][9][10]。本报告梳理 2020 至今的理论进展与经验研究，并总结其中的主要争议与未来方向。

## 已有事实

**1. 交错处理下 TWFE 估计量会产生负权重偏误。** Goodman-Bacon 的分解定理证明：交错处理下的 TWFE-DiD 估计量是全部 2×2 DiD 比较的加权平均，其中"以已处理组为对照"的坏比较会被赋予负权重[1]。de Chaisemartin 与 D'Haultfœuille 给出负权重的充要条件，指出当处理效应随组别与时期变化时，TWFE 系数的符号可能与其估计的所有处理效应方向相反[2]。该结论后被推广到多值处理与多个处理的一般情形[3]，并在一篇系统综述中整理为统一框架[4]。

**2. 交错 DiD 已发展出五类异质性稳健估计量。** Callaway 与 Sant'Anna 提出"组别-时期平均处理效应"（group-time ATT）及双重稳健半参数估计量 csdid[5]；Sun 与 Abraham 提出交互加权估计量（interaction-weighted，eventstudyinteract）直接估计组别-时期动态效应[6]；Borusyak、Jaravel 与 Spiess 提出插补（imputation）估计量，在"无预期效应+平行趋势"下达到高效[7]；Gardner 提出两阶段回归估计量 did2s[8]；de Chaisemartin 与 D'Haultfœuille 提出 did_multiplegt，估计处理切换者（switchers）的瞬时与跨期处理效应[26]。

**3. 平行趋势"预检验"存在选择偏差。** Roth 证明仅在事前趋势"通过"预检验后才报告的条件估计量会系统性偏大、置信区间过窄，标准做法不可靠[9]；Rambachan 与 Roth 以"事前违背对事后违背具信息性"替代精确平行趋势，构造 HonestDiD 敏感性区间[10]。更早的 Malani 与 Reif 已证明把事前趋势解释为预期效应会系统改变估计的处理效应[11]。

**4. 前沿拓展覆盖连续处理、合成 DiD、模糊 DiD 与聚类推断。** Arkhangelsky 等提出合成 DiD，在双重去偏基础上引入合成权重[13]；Callaway、Goodman-Bacon 与 Sant'Anna 把 DiD 推广到连续/剂量处理，识别平均剂量响应[14]；de Chaisemartin 与 D'Haultfœuille 的模糊 DiD 处理不完全依从情形[15]；在少量处理组或少量簇下，Ferman 与 Pinto、MacKinnon 与 Webb 分别提出异方差稳健检验与随机化推断[16][17]。

**5. 经验研究已采用新方法，经典结论也接受了再检验。** Baker、Larcker 与 Wang 用稳健估计量复现 12 篇已发表研究，发现约四分之一结论的符号或显著性发生反转[18]；Cengiz 等的最低工资研究构成堆叠事件研究的基准，此后被"现代 DiD"方法反复重估[19]；2025 年 Chen 等进一步提出高效 DiD 与事件研究估计量[20]。中文文献方面，林梦芸等在《管理世界》构建了理解 DiD 最新发展的模型误设统一框架[21]，陈强等系统整理 DiD 安慰剂检验并提供 Stata 命令[22]，赵西亮给出最新发展的中文综述[23]。刘冲等阐释交错 DiD 中 TWFE 的偏误根源与估计方法选择[27]，张征宇等提出负权重的新机制与解决方案[28]；连享会等平台系统介绍了 csdid 等命令的中文实操[24]，广东外语外贸大学等机构持续编译 DiD 前沿方法解读[25]。

## 主要文献观点

1. **默认的 TWFE 设定在交错处理下不再默认可信**：报告前应做 Bacon 分解诊断负权重，并选择与新设定匹配的稳健估计量[1][2][4][12]。
2. 稳健估计量之间的差异主要落在**对照组选择与目标参数定义**：Callaway-Sant'Anna 默认以"尚未处理组"为对照、Sun-Abraham 以"最后一期未处理组"为对照、Borusyak 插补基于"从未处理组"，三者估计的目标 ATT 并不完全相同，实证中应做跨估计量的一致性检验[5][6][7][12]。
3. 平行趋势从"可检验的假设"转向"可做敏感性分析的假设"：HonestDiD 的置信集提供了比二值"通过/不通过"更细的报告方式[9][10]。
4. 2022 年后，中文计量研究开始对齐国际规范：顶刊普遍要求"稳健估计量 + 事件研究 + 平行趋势敏感性 + 安慰剂检验"的完整流程，并开始用统一框架消化 DiD 方法论进展[21][22][23][24][25]。

## 主要矛盾与冲突点

1. **平行趋势预检验是否可信**：传统做法把"事前趋势不显著"当作 DiD 可行的充分证据，但 Roth 证明这一做法引入选择偏差、使点估计与区间失真[9]；而预检验在实践中仍很常见，HonestDiD 敏感性分析尚未完全替代它[10]。
2. **新估计量是否实质改变经典结论**：Baker-Larcker-Wang 发现约四分之一已发表研究在新方法下符号或显著性反转[18]，但最低工资文献用"现代 DiD"方法重估后效应仍接近零，呈现"方法进步但结论稳健"与"结论反转"并存的分歧[19]。
3. **TWFE 是否应被完全弃用**：负权重批评者主张在交错+异质性下弃用 TWFE[1][2]，但设计稳健（design-robust）TWFE 修正路线认为 TWFE 在特定设定下仍可有效[29]，模拟比较也显示 TWFE 与新型动态估计量的适用边界存在重叠，对"何时仍可用 TWFE"存在张力[4][30]。
4. **处理度量与函数形式的敏感性**：Roth 与 Sant'Anna 指出估计结果对函数形式与处理度量高度敏感，削弱了稳健估计量"一劳永逸"的适用性主张[12][14]。

## 未来研究方向

1. **高效且设计稳健的估计量**是活跃方向：在插补估计量基础上进一步提升效率，并发展设计稳健的 TWFE 修正[7][20][29]。
2. **平行趋势的不可检验部分**需要更一般化的敏感性框架，HonestDiD 向连续处理、非参数设定与高维协变量的推广仍是开放问题[10][13][14]。
3. **连续处理 DiD 的推断理论**（剂量响应置信带）与机器学习结合的时变连续处理估计仍处早期，需要更多理论与实证检验[14]。
4. **少量处理组/少量簇下的稳健推断**仍需系统化，尤其向交错处理与事件研究一致置信带的扩展[16][17]。
5. 检验**中文实证的新规范落地效果**、并用稳健估计量系统复现国内经典政策评估，是中文计量学界仍需推进的方向[21][23]。

## 参考文献

[1] Goodman-Bacon, Andrew, "Difference-in-differences with variation in treatment timing", Journal of Econometrics, 2021, 层级: 1, 来源: AnySearch, URL: https://www.sciencedirect.com/science/article/abs/pii/S0304407621001445
[2] de Chaisemartin, Clément & D'Haultfœuille, Xavier, "Two-way fixed effects estimators with heterogeneous treatment effects", American Economic Review, 2020, 层级: 1, 来源: AnySearch, URL: https://www.aeaweb.org/articles?id=10.1257/aer.20181169
[3] de Chaisemartin, Clément & D'Haultfœuille, Xavier, "Two-way fixed effects and differences-in-differences estimators with several treatments", Journal of Econometrics, 2023, 层级: 1, 来源: AnySearch, URL: https://www.sciencedirect.com/science/article/abs/pii/S0304407623001963
[4] de Chaisemartin, Clément & D'Haultfœuille, Xavier, "Two-way fixed effects and differences-in-differences with heterogeneous treatment effects: a survey", NBER Working Paper 29734, 2022, 层级: 2, 来源: AnySearch, URL: https://www.nber.org/papers/w29734
[5] Callaway, Brantly & Sant'Anna, Pedro H. C., "Difference-in-differences with multiple time periods", Journal of Econometrics, 2021, 层级: 1, 来源: AnySearch, URL: https://www.sciencedirect.com/science/article/abs/pii/S0304407620303948
[6] Sun, Liyang & Abraham, Sarah, "Estimating dynamic treatment effects in event studies with heterogeneous treatment effects", Journal of Econometrics, 2021, 层级: 1, 来源: AnySearch, URL: https://www.sciencedirect.com/science/article/abs/pii/S030440762030378X
[7] Borusyak, Kirill; Jaravel, Xavier & Spiess, Jann, "Revisiting event study designs: robust and efficient estimation", Review of Economic Studies, 2024, 层级: 1, 来源: Exa, URL: https://doi.org/10.1093/restud/rdae007
[8] Gardner, John, "Two-stage differences in differences", arXiv:2207.05943, 2022, 层级: 2, 来源: AnySearch, URL: https://arxiv.org/abs/2207.05943
[9] Roth, Jonathan, "Pretest with caution: event-study estimates after testing for parallel trends", American Economic Review: Insights, 2022, 层级: 1, 来源: Exa, URL: https://www.aeaweb.org/articles?id=10.1257/aeri.20210236
[10] Rambachan, Ashesh & Roth, Jonathan, "A more credible approach to parallel trends", Review of Economic Studies, 2023, 层级: 1, 来源: Exa, URL: https://doi.org/10.1093/restud/rdad018
[11] Malani, Anup & Reif, Julian, "Interpreting pre-trends as anticipation: impact on estimated treatment effects from tort reform", Journal of Public Economics, 2015, 层级: 1, 来源: AnySearch, URL: https://doi.org/10.1016/j.jpubeco.2015.01.001
[12] Roth, Jonathan; Sant'Anna, Pedro H. C.; Bilinski, Alyssa & Poe, John, "What's trending in difference-in-differences? A synthesis of the recent econometrics literature", Journal of Econometrics, 2023, 层级: 1, 来源: Exa, URL: https://www.sciencedirect.com/science/article/abs/pii/S0304407623001318
[13] Arkhangelsky, Dmitry; Athey, Susan; Hirshberg, David A.; Imbens, Guido W. & Wager, Stefan, "Synthetic difference-in-differences", American Economic Review, 2021, 层级: 1, 来源: AnySearch, URL: https://www.aeaweb.org/articles?id=10.1257/aer.20190159
[14] Callaway, Brantly; Goodman-Bacon, Andrew & Sant'Anna, Pedro H. C., "Difference-in-differences with a continuous treatment", NBER Working Paper 32117, 2024, 层级: 2, 来源: Exa, URL: https://doi.org/10.3386/w32117
[15] de Chaisemartin, Clément & D'Haultfœuille, Xavier, "Fuzzy differences-in-differences", Review of Economic Studies, 2018, 层级: 1, 来源: AnySearch, URL: https://academic.oup.com/restud/article-abstract/85/2/999/4096388
[16] Ferman, Bruno & Pinto, Cristine, "Inference in differences-in-differences with few treated groups and heteroskedasticity", Review of Economics and Statistics, 2019, 层级: 1, 来源: AnySearch, URL: https://doi.org/10.1162/rest_a_00759
[17] MacKinnon, James G. & Webb, Matthew D., "Randomization inference for difference-in-differences with few treated clusters", Journal of Econometrics, 2020, 层级: 1, 来源: AnySearch, URL: https://www.sciencedirect.com/science/article/abs/pii/S0304407620301445
[18] Baker, Andrew C.; Larcker, David F. & Wang, Charles C. Y., "How much should we trust staggered difference-in-differences estimates?", Journal of Financial Economics, 2022, 层级: 1, 来源: SciVerse, URL: https://www.hbs.edu/ris/Publication%20Files/21-112_8a5a4ab3-b9e7-447d-a0fe-a504b3890fb9.pdf
[19] Cengiz, Doruk; Dube, Arindrajit; Lindner, Attila & Zipperer, Ben, "The effect of minimum wages on low-wage jobs", Quarterly Journal of Economics, 2019, 层级: 1, 来源: SciVerse, URL: https://academic.oup.com/qje/article-abstract/134/3/1405/5484905
[20] Chen, Jiafeng 等, "Efficient difference-in-differences and event study estimators", Cowles Foundation Discussion Paper No. 2892, Yale University, 2025, 层级: 2, 来源: WebSearch, URL: https://elischolar.library.yale.edu/cowles-discussion-paper-series/2892/
[21] 林梦芸, 徐阳, 郭汝飞, 易君健, "在模型误设的统一框架下理解双重差分方法的最新发展", 管理世界, 2025, 层级: 1, 来源: SciVerse, URL: https://doi.org/10.19744/j.cnki.11-1235/f.2025.0084
[22] 陈强, 齐霁, 颜冠鹏, "双重差分法的安慰剂检验：一个实践的指南", 管理世界, 2025, 层级: 1, 来源: Exa, URL: https://ygakj.gdufs.edu.cn/info/1260/1892.htm
[23] 赵西亮, "双重差分法原理及其最新发展：一个不完全综述", SSRN Working Paper (abstract_id=4788185), 2024, 层级: 2, 来源: Exa, URL: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4788185
[24] 连享会（连玉君团队）, "DID新进展：异质性多期DID估计的新方法-csdid", 连享会 lianxh.cn, 2022, 层级: 3, 来源: SerpApi, URL: https://www.lianxh.cn/details/1071.html
[25] 广东外语外贸大学粤港澳大湾区会计与经济发展研究中心, "前沿方法：多期DID估计的新范式——异质性处理效应下的偏误纠正与路径选择", 前沿方法系列, 2024, 层级: 3, 来源: WebSearch, URL: https://ygakj.gdufs.edu.cn/info/1254/1552.htm
[26] de Chaisemartin, Clément & D'Haultfœuille, Xavier, "Difference-in-differences estimators of intertemporal treatment effects", Review of Economics and Statistics, 2024, 层级: 1, 来源: Exa, URL: https://doi.org/10.1162/rest_a_01414
[27] 刘冲, 沙学康, 张妍, "交错双重差分：处理效应异质性与估计方法选择", 数量经济技术经济研究, 2022, 层级: 1, 来源: Exa, URL: http://iqte.cssn.cn/xsjl/yyjlszlt/202308/t20230828_5681591.shtml
[28] 张征宇 等, "双重差分法下固定效应估计量的负权重问题——新的机制与解决方案", 数量经济技术经济研究, 2025, 层级: 1, 来源: Exa, URL: https://www.ncpssd.cn/Literature/articleinfo?id=SLJJJSJJYJ2025004010&langType=1&nav=1&type=journalArticle
[29] Arkhangelsky, Dmitry; Imbens, Guido; Lei, Lihua & Luo, Xiaoman, "Design-robust two-way-fixed-effects regression for panel data", Quantitative Economics, 2024, 层级: 1, 来源: Exa, URL: https://www.econometricsociety.org/publications/quantitative-economics/2024/11/01/Design-Robust-Two-Way-Fixed-Effects-Regression-For-Panel-Data/file/quan200345.pdf
[30] Rüttenauer, Tobias & Aksoy, Ozan, "When can we use two-way fixed effects? A comparison of TWFE and novel dynamic DiD estimators", arXiv:2402.09928, 2024, 层级: 2, 来源: Exa, URL: https://arxiv.org/abs/2402.09928

## 执行情况

| 项目 | 说明 |
|------|------|
| 执行流程 | 源检测 → 研究意图澄清 → 计划确认 → 状态机初始化 → 3 子代理并行检索 + Lead 六路补强 → 结果确认 → 综合撰写 → 验证 |
| 搜索源使用 | AnySearch: 15 / SciVerse: 10 / Exa: 10 / SerpApi: 3 / WebSearch: 8（Tavily: 6） |
| 覆盖质量 | 中文 7 条 / 英文 23 条；权威期刊（层级 1）22 条、可信来源（层级 2）6 条、补充来源（层级 3）2 条 |
| 维度覆盖 | 5 维度全部双语覆盖：TWFE 负权重 / 异质性稳健估计量 / 平行趋势检验 / 前沿拓展 / 经验应用 |
| 耗时 | 检索约 15 分钟（3 子代理并行 + Lead 补强），综合撰写约 10 分钟 |
| 报告位置 | ~/tri-research-reports/DEEP_RESEARCH_双重差分法_2026-08-14.md |
