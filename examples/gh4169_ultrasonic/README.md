# GH4169 超声参数预测平均晶粒尺寸

本例把作者公开的试样级超声参数接入 SamplePackage、HDF5 和配置驱动的训练 NPZ，
再用现有 CPU MLP 与均值、线性及岭回归基线进行评估。数据共有十个 GH4169 试样。
当前结果中线性回归比 MLP 更准确，适合作为这份小样本数据的参考方法。

## 数据与任务

唯一数据源为 Xi Chen、Guanhua Wu、Zhenggan Zhou、chen hao 的
[Mendeley Data v1](https://data.mendeley.com/datasets/v487vwmd7r/1)，
DOI 10.17632/v487vwmd7r.1，2019-05-27 发布。
[原论文公开页面](https://www.sciencedirect.com/science/article/abs/pii/S0963869518304225)
说明试样来自 GH4169 轧制棒材，并描述十个试样；本例没有引入其他数据集。

DATA.xlsx 的有效数据在 Sheet1；Sheet2 和 Sheet3 为空。Sheet1 有 224 个非空单元格，
没有公式，按公式模式与缓存值模式读取的数值一致。A4:A11 是 NO.1–NO.8，
A12:A13 是 T1/T2。每个试样一行汇总参数，作者结果表 A48:A49 再次将 T1/T2
标为测试样本。六张 JPG 是附带金相图，文件数不代表试样数，也不作为训练输入。

| 角色 | 原始位置 | 含义 | 单位 |
| --- | --- | --- | --- |
| 试样身份 | A4:A13 | 原始试样编号 | 标签 |
| 条件记录 | B4:B13 | 热处理原文 | 复合文本，不解析为数值 |
| 目标 | C4:C13 | 金相平均晶粒直径 | μm（配置记作 um） |
| 输入一 | D4:D13 | 平均衰减系数 ᾱ | dB/mm |
| 输入二 | F4:F13 | 平均纵波声速 c̄L | m/s |

D3/F3 的符号是嵌入 PNG，分别为工作簿 `xl/media/image1.png` 和 `image3.png`；
单纯读取单元格文本只能得到单位。本次已提取并目视检查这些表头。
所选 D/F 列为有量纲的作者汇总参数，不是本文重新归一化后的列。
不采用 Sheet1 16–49 行的目标相关系数、映射系数、拟合结果或作者预测。
两列输入按清楚的物理定义和单位固定，不用全体目标相关性筛选。

E/G 列的离散程度参数未进入这个固定的两均值任务。H 列带非线性系数倍率符号，
I/J 列为背散射特征符号，但其具体单位及表头与数值的对应仍有疑点；均未使用。
尤其 I 列的 ω₂ 与 J 列的 F_SHA1 表头需要进一步核实，不能依数值形态自行对调。
B9/B10 原文为 `11000℃/1h/WC`、`11300℃/1h/WC`，原样保存；没有据 JPG 名称纠正。
热处理原文作为标签登记单位 `1`，不表示其中的温度、时间是无量纲物理量。
没有逐测点波形、重复测量明细或金相计数记录，无法独立重算这些统计量及其不确定度。
主数据表有七个超声数值列，而相关系数区列出八项，末列符号也有差异；不能据此
补造缺失特征。本轮读取了论文公开页，尚未取得全文，完整采集设置和计数方法未核实。

## 规范化与来源分组

`prepare.py` 核对 `source.json` 固定的文件版本，再调用现有 XLSX block 适配器。
每个试样输出一个 HDF5 和对应的 `*.ingest.json`，包含原表列映射、工作表/行、
试样身份、单位、许可和转换记录。`workbook-audit.json` 保存全部工作表的非空值、
公式/缓存信息和处理选择。原始热处理字符串保留在表行及来源记录中。

十个 HDF5 的根来源仍是同一个 DATA.xlsx。生成的 `build.json` 用
`target_specimen: {column: specimen, evidence: ...}` 声明 A 列的实体试样身份，
按同一试样的全部测量分组。构建器核对源行和身份，保留整份工作簿的来源链。
没有通过改名文件或复制数据绕开来源检查。表坐标为记录轴，张量/取向声明仅表示
标量回归的适用性；这些包不提供 CPFE 或 Abaqus 求解所需的物理输入。

## 小样本评估

T1/T2 始终保留为作者测试样本。开发集固定四对：NO.1/NO.5、NO.2/NO.6、
NO.3/NO.7、NO.4/NO.8；按原编号制定，不按目标值寻找更好的划分。

开发集外层每次留出一对。其余六个试样再轮流取一对验证，得到三个 4/2/2
训练/验证/外层测试配置。各模型按内层验证 MSE 选择 checkpoint，等权平均后
预测外层两件试样。每个开发试样的外层预测都没有用自身目标训练或选择 checkpoint。
内层验证误差只用于选择，不作为最终泛化成绩。

最终四个 MLP 分别按 6/2/2 使用开发集和 T1/T2，四个验证选定的模型等权平均。
固定单隐藏层四单元 tanh、seed=17、学习率 0.003、最多 1500 epoch、patience=200。
输入和目标的均值/尺度仅在各模型训练子集拟合。该网络有 17 个参数，训练样本很少。

均值与 OLS 在外层六个、最终八个开发试样上拟合。岭回归的 alpha 候选为
0.01/0.1/1/10/100；在相应内层验证选择后，用全部可用开发试样重新拟合。
因此各 MLP 成员使用的拟合试样数少于这些重新拟合的基线，结果按这套流程比较。
没有使用目标插值、复制、图像切块或测点拆分制造独立样本。

2026-09-07 本地运行，误差单位均为 μm：

| 方法 | 开发集外层 MAE（n=8） | 开发集外层 RMSE | 作者测试 MAE（n=2） | 作者测试 RMSE |
| --- | ---: | ---: | ---: | ---: |
| 均值 | 45.00 | 51.84 | 20.62 | 27.22 |
| OLS | 9.18 | 10.00 | 5.54 | 5.71 |
| 岭回归 | 10.31 | 11.41 | 5.96 | 5.96 |
| MLP 集成 | 19.92 | 26.56 | 9.38 | 9.38 |

16 个 MLP checkpoint 已逐一读回，预测与训练保存值的最大绝对差为 0。
最终岭回归 alpha 为 0.01。部分内层 MLP 的最佳 epoch 为 1，另一些达到 1500；
这些选择表现出验证对组成和小样本训练的不稳定性，不能用单次较好的测试成绩替代。
开发集与最终评估使用不同训练规模，也不应直接将两列误差作学习曲线解释。
本例不复现作者 MUE：输入选择、学习器、目标函数和评估方法均不同。

这份数据可以检验接入、分组、训练和预测过程；十个同研究来源的试样不足以证明
跨材料批次、设备或探头条件的泛化。测试标签本来就公开，本地审查已见到它们，
本次保留了计算上的测试隔离，但不是前瞻性盲测。
训练完成后的描述性检查显示，八个开发试样的两列特征相关系数为 −0.9822。
这说明两种测量携带的信息高度相关，OLS 系数也不宜解释为独立的物理影响；
该检查没有用于改列、调参或选择测试划分。

## 本地复跑

在仓库根目录，使用项目 `.venv`；安装基础、native 和 training 依赖，绘图另需
matplotlib。每次选择新的输出目录。通过数据页的正常下载链接取得原始文件，
不要将错误网页另存为 Excel。

```powershell
.\.venv\Scripts\python.exe -X utf8 examples/gh4169_ultrasonic/prepare.py --source runs/public-data-screening/gh4169-20260907/raw/DATA.xlsx --output-dir runs/gh4169-rerun/normalized
.\.venv\Scripts\python.exe -X utf8 examples/gh4169_ultrasonic/evaluate.py --normalized-dir runs/gh4169-rerun/normalized --output-dir runs/gh4169-rerun/evaluation
.\.venv\Scripts\python.exe -X utf8 examples/gh4169_ultrasonic/plot.py --evaluation runs/gh4169-rerun/evaluation/evaluation.json
```

若只想构建默认的第一组 6/2/2 NPZ，可在规范化后单独运行：

```powershell
.\.venv\Scripts\pipeline.exe build-training-dataset --config runs/gh4169-rerun/normalized/build.json --run-dir runs/gh4169-rerun/dataset
```

`evaluate.py` 会为全部 16 个拟合写出独立的 `build.json`、dataset.npz、dataset.json、
训练配置、数据收据、model.pt 和训练历史；复跑单个拟合可用保存的 `fit.json`
执行 `pipeline train-surrogate --config <fit.json> --run-dir <new-model-directory>`。
最终集成由 `final-0` 到 `final-3` 的四个 checkpoint 通过 `predict_mlp` 预测后取均值，
模型按 `[attenuation_mean, longitudinal_velocity_mean]` 顺序接收两列输入。

`evaluation.json` 和 `predictions.csv` 保存每件试样、每种模型的预测、带符号误差、
绝对误差及汇总指标。`specimen-errors.png/svg` 为同一数据的静态图。
本轮完整结果在 `runs/gh4169-ultrasonic-20260907/`；
测试和下载证据也保存在该目录及原筛选目录的 `refresh/` 中。

原始文件、规范化数据、模型、逐试样结果及图均留在忽略目录，并保留
[CC BY-NC 3.0](https://creativecommons.org/licenses/by-nc/3.0/) 署名与非商业条件。
本例脚本和合成测试夹具使用项目代码许可，原数据许可不随之改变。
本轮没有提交、推送、发布数据/权重或创建新版本。
