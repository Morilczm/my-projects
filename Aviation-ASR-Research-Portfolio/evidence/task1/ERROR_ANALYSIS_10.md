# 任务一：10 个 dev 错误的分类分析

分析对象：正式 LoRA `train_full_163783`，完整 dev 推理作业 `167720`；对照基模 dev 作业 `162200`。

结论：正式 LoRA 改善了总体 spoken WER，但存在模板化新增、实体类型混淆、数值/单位及触发词错误。以下 10 条分析已完成文本证据核对、错误分类、训练前后比较、指标解释及后续验证建议。

## 证据范围与方法

- 只使用冻结 dev 的参考转写及两模型保存的预测，未读取或使用 test。
- 10 条是按错误机制挑选的案例，不是随机样本；案例数与分类占比不能当作全 dev 错误率。部分样本属于同一课程，不能视为独立泛化试验。
- row_id 为预测 CSV 内从 0 开始的行编号；附录保留 sql_id、record_set、archive_path、archive_member 和文件 SHA-256，便于追溯。
- 已确认的是“预测相对所给参考的文本差异”。尚未听音，参考也不是逐条人工听录音金标准；不把推测写成已确认的声学原因。
- 实体指标沿用固定规则：逐句以（类型，规范值）集合匹配。类型/值正确才为 TP，额外值为 FP，缺失值为 FN；相同值在同句去重。规则未覆盖的错误会另作文字分析。
- 单句 WER 使用与原评估一致的规范化和词级 Levenshtein 距离。S/D/I 分解在并列最优时按“匹配、替换、删除、插入”回溯；其具体分解可能不唯一，总编辑距离不变。单句 WER 可以超过 100%。

## 完整 dev 背景（并非由 10 个案例估计）

| 指标 | Baseline | 正式 LoRA |
|---|---:|---:|
| spoken WER | 47.29% | 43.29% |
| 整句 Exact | 21.67% | 29.00% |
| 实体 micro P（全部 1,200 条） | 95.97% | 56.18% |
| 实体 micro R（全部 1,200 条） | 66.30% | 67.13% |
| 实体 micro F1（全部 1,200 条） | 78.42% | 61.17% |
| 规范化后空输出 | 67 | 0 |

完整 dev 已确认：LoRA 有 159 条预测出现参考规则实体中不存在的 EXO321；67 条基模空输出中 57 条变成含有该呼号的输出，67 条中没有一条达到整句 Exact。因此“空输出为零”不能解释成“原空输出已修复”。这是文本/规则统计，不是对真实音频中呼号出现情况的人工判断。

## 分类总览

| 主类别 | 本报告案例数 |
|---|---:|
| 呼号前缀错认 | 1 |
| 整句模板替换或扩写 | 3 |
| 实体类型与上下文混淆 | 2 |
| 实体触发词错认 | 2 |
| 单位及数字序列混淆 | 1 |
| 实体数值替换 | 1 |

| 案例 | row_id | 主类别 | 核心错误 | 训练前后变化 |
|---|---:|---|---|---|
| E01 | 2 | 呼号前缀错认 | 呼号数字保留，但航空公司前缀错误 | 呼号错误持续，普通词局部改善 |
| E02 | 6 | 整句模板替换或扩写 | 空输出被无关航空模板替换 | 原有漏报持续，并新增呼号误报 |
| E03 | 82 | 整句模板替换或扩写 | 单词任务出现长句扩写和实体新增 | 两者均扩写；LoRA 新增两个可解析实体 |
| E04 | 25 | 整句模板替换或扩写 | 时间区间与飞行高度层整段遗漏 | 三个实体漏报持续，新增一个呼号误报 |
| E05 | 145 | 实体类型与上下文混淆 | 时间表达被改写为飞行高度层 | 局部修复与新增错误并存，实体误报增加 |
| E06 | 241 | 实体类型与上下文混淆 | 机位号被改成跑道号 | 一般短语改善，位置实体类型退化 |
| E07 | 24 | 实体触发词错认 | 高度层数字正确，触发短语仍错误 | 普通词改善，高度层漏报持续 |
| E08 | 1031 | 单位及数字序列混淆 | 风速单位变成角度，数字序列也发生变化 | 两个原本正确的速度实体退化 |
| E09 | 1116 | 实体触发词错认 | QNH 缩写错认导致气压实体丢失 | 一个原本正确的 QNH 实体退化 |
| E10 | 173 | 实体数值替换 | 距离错误值改变，但没有恢复为正确值 | 错值改变，实体计数没有改善 |

## 逐例分析

### E01 · row_id=2 · 呼号数字保留，但航空公司前缀错误

主类别：**呼号前缀错认**。子集：`04` / `communication_training_multi_turn`；sql_id：`843022`。

**参考文本**

> air cruiser tree tree zero one roger maintenance will be there soon the runway inspectors retrieved a single piece of rubber on the runway

**Baseline（规范化后）**

> proviso three three zero one roger maintenance will be there soon the runway inspectors re tri re tried a single piece of rubber on the runway

**正式 LoRA（规范化后）**

> probe zero tree tree zero one roger maintenance will be there soon the runway inspectors retrieved a single piece of rubber on the runway

| 模型 | 单句 WER | S / D / I | 实体 TP / FP / FN |
|---|---:|---:|---:|
| baseline | 33.33% | 4 / 1 / 3 | 0 / 0 / 1 |
| lora | 8.33% | 2 / 0 / 0 | 0 / 0 / 1 |

**已确认的文本差异。** 参考开头是 air cruiser tree tree zero one。Baseline 写成 proviso three three zero one，LoRA 写成 probe zero tree tree zero one。LoRA 保留了 3301 的数字词，但未恢复 air cruiser；普通词 retrieved 则由基模的 re tri re tried 改对。

**实体和评价影响。** 两个模型均漏掉 CALLSIGN:air_cruiser:3301。LoRA 的 probe zero 不在固定呼号前缀列表中，因此规则没有额外记录 FP；这不表示错误前缀不存在。普通词改善与完整呼号识别失败可以同时发生。

- 参考实体：callsign=CALLSIGN:air_cruiser:3301
- LoRA 错误新增（FP）：无
- LoRA 漏报（FN）：callsign=CALLSIGN:air_cruiser:3301

**训练前后判断。** 呼号错误持续，普通词局部改善。

**可能原因与证据边界。** 待验证：航空公司前缀的声学识别或领域词汇覆盖不足。仅凭输出无法判断 air cruiser 是否为录音中的实际读法，也不能断言训练集中缺少该词。

**改进与验证建议。** 优先听开头呼号并核对课程参考；审计 train 中 air cruiser 及其他前缀覆盖。后续对照可关注呼号完整片段，不能只提高数字 token 权重；不得把 probe zero 直接改映射为 air cruiser 来修分。

### E02 · row_id=6 · 空输出被无关航空模板替换

主类别：**整句模板替换或扩写**。子集：`03` / `scenario_practice_single_turn`；sql_id：`1191514`。

**参考文本**

> deviation from the route is limited within five kilometers on each side due to dangerous area

**Baseline（规范化后）**

> （空；原始输出为单独句点 `.`）

**正式 LoRA（规范化后）**

> exo tree two one nanyue approach roger report your intentions

| 模型 | 单句 WER | S / D / I | 实体 TP / FP / FN |
|---|---:|---:|---:|
| baseline | 100.00% | 0 / 16 / 0 | 0 / 0 / 1 |
| lora | 100.00% | 10 / 6 / 0 | 0 / 1 / 1 |

**已确认的文本差异。** 参考要求因危险区域限制航路偏离在每侧五公里内。Baseline 原始输出为单独句点，规范化为空；LoRA 改为 exo tree two one nanyue approach roger report your intentions，与限制偏航的内容不对应。

**实体和评价影响。** Baseline 漏掉 DIST5KM；LoRA 仍漏掉该距离，另新增参考未支持的 CALLSIGN:exo:321。非空文本没有恢复这条指令。

- 参考实体：distance=DIST5KM
- LoRA 错误新增（FP）：callsign=CALLSIGN:exo:321
- LoRA 漏报（FN）：distance=DIST5KM

**训练前后判断。** 原有漏报持续，并新增呼号误报。

**可能原因与证据边界。** 待验证：弱音频证据、音频/参考不一致、预处理异常或模型偏向常见模板均可能造成该现象。现有证据只确认文本发生整句替换，不能认定是噪声或过拟合。

**改进与验证建议。** 听音核对录音内容，检查时长、能量、截断和采样率处理；再与其他 EXO321 输出逐条对照。模型选择同时检查 FP 和 WER，不能以“无空输出”为成功标准。

### E03 · row_id=82 · 单词任务出现长句扩写和实体新增

主类别：**整句模板替换或扩写**。子集：`02/01` / `word`；sql_id：`840304`。

**参考文本**

> divert

**Baseline（规范化后）**

> i just realized that i have been working hard on something for more than a year in his eyes it is nothing in order to make the show better he can be good at it

**正式 LoRA（规范化后）**

> exo tree two one we are going to make a turn at one o'clock fifteen miles ahead of us

| 模型 | 单句 WER | S / D / I | 实体 TP / FP / FN |
|---|---:|---:|---:|
| baseline | 3500.00% | 1 / 0 / 34 | 0 / 0 / 0 |
| lora | 1900.00% | 1 / 0 / 18 | 0 / 2 / 0 |

**已确认的文本差异。** 该样本属于 word 子集，参考只有 divert。Baseline 输出一段与参考无关的长英文；LoRA 输出 exo tree two one we are going to make a turn at one o'clock fifteen miles ahead of us，也未给出 divert。

**实体和评价影响。** Baseline 没有规则实体，但转写严重错误；LoRA 的长句虽然更像航空话语，却新增 CALLSIGN:exo:321 和 DIST15NM。参考无规则实体的句子必须保留在误报统计中。

- 参考实体：无
- LoRA 错误新增（FP）：callsign=CALLSIGN:exo:321；distance=DIST15NM
- LoRA 漏报（FN）：无

**训练前后判断。** 两者均扩写；LoRA 新增两个可解析实体。

**可能原因与证据边界。** 待验证：孤立单词任务与长句解码先验可能不匹配，或音频与参考有问题。没有音频时长证据，不能把“参考短”直接当成“录音短”。

**改进与验证建议。** 先确认是否确实读了 divert、是否有静音/背景语音；按 word 与完整话语分层检查输出长度比和重复模板。只在 dev 上设计保守的长度/置信度对照，不为本例单独截断输出。

### E04 · row_id=25 · 时间区间与飞行高度层整段遗漏

主类别：**整句模板替换或扩写**。子集：`04` / `communication_training_multi_turn`；sql_id：`1003892`。

**参考文本**

> level restriction from zero two tree zero utc to zero six zero zero utc and using flight level tree two zero as a temporary level

**Baseline（规范化后）**

> thank you very much

**正式 LoRA（规范化后）**

> exo tree two one nanyue approach roger report your intentions

| 模型 | 单句 WER | S / D / I | 实体 TP / FP / FN |
|---|---:|---:|---:|
| baseline | 100.00% | 4 / 21 / 0 | 0 / 0 / 3 |
| lora | 96.00% | 9 / 15 / 0 | 0 / 1 / 3 |

**已确认的文本差异。** 参考包含 0230 UTC 到 0600 UTC 的时间限制，以及临时 FL320。Baseline 只输出 thank you very much；LoRA 输出与 row 6 相同的 EXO321 模板，三个关键实体均未保留。

**实体和评价影响。** 两模型均漏掉 TIME0230UTC、TIME0600UTC、FL320；LoRA 再增加一个错误呼号。没有一个正确关键实体，长短输出差异不能作为识别恢复的证据。

- 参考实体：flight_level=FL320；time=TIME0230UTC；time=TIME0600UTC
- LoRA 错误新增（FP）：callsign=CALLSIGN:exo:321
- LoRA 漏报（FN）：flight_level=FL320；time=TIME0230UTC；time=TIME0600UTC

**训练前后判断。** 三个实体漏报持续，新增一个呼号误报。

**可能原因与证据边界。** 待验证：整段声学条件未被有效利用、输入/参考不匹配，或模型生成退化。它与不同参考的 row 6 输出相同，支持检查重复模板现象，但不足以定位训练根因。

**改进与验证建议。** 核对这段多轮课程音频与 archive_member，听清时间区间和高度层；检查是否读取了正确片段或存在长音频截断。确认链路后，再考虑训练步数/学习率对照及周期 checkpoint。

### E05 · row_id=145 · 时间表达被改写为飞行高度层

主类别：**实体类型与上下文混淆**。子集：`04` / `communication_training_multi_turn`；sql_id：`1107410`。

**参考文本**

> roger from zero two zero zero utc to zero six zero zero utc flight level two niner zero to flight level tree tree zero is not available for bunta traffic

**Baseline（规范化后）**

> roger from zero two zero zero utc to zero six zero zero utc flight level two ninety zero to flight level three three zero is not available for bonnet traffic

**正式 LoRA（规范化后）**

> roger flight level two zero zero utc to zero six zero zero utc flight level two niner zero to flight level tree tree zero is not available for bunta traffic

| 模型 | 单句 WER | S / D / I | 实体 TP / FP / FN |
|---|---:|---:|---:|
| baseline | 13.33% | 4 / 0 / 0 | 3 / 0 / 1 |
| lora | 6.67% | 2 / 0 / 0 | 3 / 1 / 1 |

**已确认的文本差异。** 参考开头 from zero two zero zero utc 表示 0200 UTC。LoRA 变为 flight level two zero zero utc，固定规则提取成 FL200，原时间丢失。同时，LoRA 将基模的 two ninety zero 改成 two niner zero，恢复 FL290，并修正了 bunta。

**实体和评价影响。** Baseline 为 TP=3、FN=1；LoRA 为 TP=3、FP=1、FN=1。LoRA 修复一个 FL290 漏报，却把已正确的 TIME0200UTC 改坏，并新增 FL200。two ninety zero 的数字读法不被当前 FL 规则覆盖，这是基模该 FN 的解析因素，不能直接等价为“数字值听错”。

- 参考实体：flight_level=FL290；flight_level=FL330；time=TIME0200UTC；time=TIME0600UTC
- LoRA 错误新增（FP）：flight_level=FL200
- LoRA 漏报（FN）：time=TIME0200UTC

**训练前后判断。** 局部修复与新增错误并存，实体误报增加。

**可能原因与证据边界。** 待验证：相邻时间/高度层语境对生成产生干扰；也需听音确认是否读成了不同形式。已确认的问题是输出加入 flight level 并改变数字序列，不只是规则是否宽松。

**改进与验证建议。** 核对原音频中 from/flight level 和四位时间；按“数字＋触发词＋单位”分析成组错误。规则不支持的等值读法单独记录；若将来修订规则，必须版本化并同时重算两模型。

### E06 · row_id=241 · 机位号被改成跑道号

主类别：**实体类型与上下文混淆**。子集：`03` / `scenario_practice_single_turn`；sql_id：`1535660`。

**参考文本**

> a suitcase seems to be left behind on bay two one seven confirm you have it in sight

**Baseline（规范化后）**

> call sign a suitcase seems to be left behind on bay two one seven confirm you have it inside

**正式 LoRA（规范化后）**

> corsair a suitcase seems to be left behind on runway two one seven confirm you have it in sight

| 模型 | 单句 WER | S / D / I | 实体 TP / FP / FN |
|---|---:|---:|---:|
| baseline | 22.22% | 1 / 1 / 2 | 0 / 0 / 0 |
| lora | 11.11% | 1 / 0 / 1 | 0 / 1 / 0 |

**已确认的文本差异。** 参考是 bay two one seven，即机位/停机位 217。Baseline 保留 bay，但把 in sight 写成 inside；LoRA 修正 in sight 的同时，把 bay 改成 runway，得到 runway two one seven，并在句首输出 corsair。

**实体和评价影响。** LoRA 新增 RWY217。现有规则没有 bay 类别，也不校验跑道编号是否在 01–36，因此只记录跑道 FP，不会记录 bay 217 的 FN。RWY217 不符合常见跑道编号范围，是文本和规则诊断都应标出的异常；baseline 实体 0 错误并不说明整句正确。

- 参考实体：无
- LoRA 错误新增（FP）：runway=RWY217
- LoRA 漏报（FN）：无

**训练前后判断。** 一般短语改善，位置实体类型退化。

**可能原因与证据边界。** 待验证：模型偏向更常见的 runway 词或声学混淆。规则接受三位跑道号是已确认的解析限制，但不能用删除该 FP 来掩盖 bay→runway 的文本错误。

**改进与验证建议。** 听音核对 bay，单列 bay/runway/taxiway 类型混淆；保留当前指标，另作编号合法性诊断。若补充 bay 提取或跑道校验，应作为新规则版本完整重评，不修改本轮历史分数。

### E07 · row_id=24 · 高度层数字正确，触发短语仍错误

主类别：**实体触发词错认**。子集：`04` / `communication_training_multi_turn`；sql_id：`861036`。

**参考文本**

> roger from zero four zero zero utc to zero six zero zero utc flight level tree one zero or below for bunta traffic

**Baseline（规范化后）**

> roger from zero four zero zero utc two zero six zero zero utc by level three one zero below for bound traffic

**正式 LoRA（规范化后）**

> roger from zero four zero zero utc to zero six zero zero utc by level tree one zero below for band traffic

| 模型 | 单句 WER | S / D / I | 实体 TP / FP / FN |
|---|---:|---:|---:|
| baseline | 21.74% | 4 / 1 / 0 | 2 / 0 / 1 |
| lora | 13.04% | 2 / 1 / 0 | 2 / 0 / 1 |

**已确认的文本差异。** 参考 flight level tree one zero or below 被两个模型写成 by level ... below。LoRA 将前面的连接词 two 改为 to，并采用 tree 数字读法，但 by level 仍未变回 flight level，or 也仍缺失。

**实体和评价影响。** 两模型正确提取 TIME0400UTC 和 TIME0600UTC，但均漏掉 FL310。310 数字序列保留，完整的高度层短语没有保留；关键词错误和精确解析要求共同使召回下降。

- 参考实体：flight_level=FL310；time=TIME0400UTC；time=TIME0600UTC
- LoRA 错误新增（FP）：无
- LoRA 漏报（FN）：flight_level=FL310

**训练前后判断。** 普通词改善，高度层漏报持续。

**可能原因与证据边界。** 待验证：flight 与 by 的声学或生成混淆。仅凭数字正确不能宣布高度层实体完全正确，也不能直接把所有 by level 都当作 flight level。

**改进与验证建议。** 听音检查 flight level 和 or below；汇总同类短语错误，后续监督关注完整实体 span。若尝试实体加权，对词组触发部分和数字统一处理并检查是否增加误报。

### E08 · row_id=1031 · 风速单位变成角度，数字序列也发生变化

主类别：**单位及数字序列混淆**。子集：`03` / `scenario_practice_single_turn`；sql_id：`81958`。

**参考文本**

> we've just encountered wind shear wind aloft changed from two tree zero degrees one tree zero knots to two five zero degrees seven zero knots the aircraft pitched up for a while to avoid overspeed we didn't have time to request approval and request a lower level now

**Baseline（规范化后）**

> encountered wind shear wind aloft changed from two hundred thirty degrees one three zero knots to two five zero degrees seven zero knots the aircraft pitched up for a while to avoid over speed we didn't have time to request approval and request a lower level now

**正式 LoRA（规范化后）**

> we encountered wind shear wind aloft changed from two hundred thirty zero degrees one zero tree zero degrees to two five zero degrees seven zero degrees the aircraft pitched up for a while to avoid over speed we didn't have time to request approval and request a lower level now

| 模型 | 单句 WER | S / D / I | 实体 TP / FP / FN |
|---|---:|---:|---:|
| baseline | 14.58% | 4 / 2 / 1 | 2 / 0 / 0 |
| lora | 18.75% | 5 / 1 / 3 | 0 / 0 / 2 |

**已确认的文本差异。** 参考包含 one tree zero knots（130 节）和 seven zero knots（70 节）。Baseline 保留两个速度；LoRA 将其写成 one zero tree zero degrees 和 seven zero degrees，还把前面的风向读法写成 two hundred thirty zero degrees。

**实体和评价影响。** Baseline 的两个 speed 实体均为 TP；LoRA 两个都成为 FN。缺少 knots 后，规则不再把这些数值识别为速度；130→1030 及 knots→degrees 也是直接可见的内容差异，不应只归为“规则漏检”。

- 参考实体：speed=SPD130KT；speed=SPD70KT
- LoRA 错误新增（FP）：无
- LoRA 漏报（FN）：speed=SPD130KT；speed=SPD70KT

**训练前后判断。** 两个原本正确的速度实体退化。

**可能原因与证据边界。** 待验证：长句中多组方向/速度数字与单位相互干扰。是否由真实口误、噪声、截断或生成行为造成，需要听音；参考长不自动意味着音频超过模型时长上限。

**改进与验证建议。** 逐段听取风向/风速区域并检查时长和截断；对 dev 记录数字、单位配对错误。后续实体训练应覆盖单位 token，不能只对数字加权。

### E09 · row_id=1116 · QNH 缩写错认导致气压实体丢失

主类别：**实体触发词错认**。子集：`03` / `scenario_practice_single_turn`；sql_id：`9932`。

**参考文本**

> weather information of airport surface wind two five zero degrees tree meters per second visibility two tousand two hundred meters temperature tree one dewpoint two niner qnh one zero zero five runway in use zero two right

**Baseline（规范化后）**

> vanar information of location approach surface wind two five zero degrees three meters per second visibility two thousand two hundred meters temperature three one dew point two nine qnh one zero zero five runway units zero to right

**正式 LoRA（规范化后）**

> vary information of the airport surface wind two five zero degrees tree meters per second visibility two tousand two hundred meters temperature tree one due point two niner qns one zero zero five runway in sight zero two right

| 模型 | 单句 WER | S / D / I | 实体 TP / FP / FN |
|---|---:|---:|---:|
| baseline | 32.43% | 9 / 1 / 2 | 1 / 0 / 0 |
| lora | 16.22% | 4 / 0 / 2 | 0 / 0 / 1 |

**已确认的文本差异。** Baseline 保留 qnh one zero zero five；LoRA 将 qnh 改成 qns，1005 的数字读法保持不变。参考末尾 runway in use zero two right 在 LoRA 中也变成 runway in sight zero two right。

**实体和评价影响。** Baseline 的 QNH1005 为 TP，LoRA 为 FN。现有规则要求精确触发词 qnh，因此字母错误直接导致漏报。规则在参考的 runway in use 表达中也没有提取跑道，所以本条并未统计 RWY02R；不能由实体表推断本条只有一个语义错误。

- 参考实体：qnh=QNH1005
- LoRA 错误新增（FP）：无
- LoRA 漏报（FN）：qnh=QNH1005

**训练前后判断。** 一个原本正确的 QNH 实体退化。

**可能原因与证据边界。** 待验证：缩写末字母发音或文本生成混淆。数字一致表明不是气压数值替换；参考/规则未覆盖的其他问题需单独标注。

**改进与验证建议。** 听清 QNH 缩写；独立统计航空缩写触发词准确率，检查 train 相关样本。不要把 qns 无条件映射为 qnh；规则改进需要独立证据和完整双模型重评。

### E10 · row_id=173 · 距离错误值改变，但没有恢复为正确值

主类别：**实体数值替换**。子集：`03` / `scenario_practice_single_turn`；sql_id：`1288968`。

**参考文本**

> we can see a typhoon at ten o'clock about five miles request a right turn immediately

**Baseline（规范化后）**

> we can see a typhoon at ten o'clock and one five five miles request right turn immediately

**正式 LoRA（规范化后）**

> we can see a typhoon at ten o'clock and fifteen miles request a right turn immediately

| 模型 | 单句 WER | S / D / I | 实体 TP / FP / FN |
|---|---:|---:|---:|
| baseline | 25.00% | 1 / 1 / 2 | 0 / 1 / 1 |
| lora | 12.50% | 2 / 0 / 0 | 0 / 1 / 1 |

**已确认的文本差异。** 参考距离是 five miles，即 5 海里。Baseline 写成 one five five miles（155），LoRA 写成 fifteen miles（15）；LoRA 同时恢复了 request a right turn 中的 a。

**实体和评价影响。** Baseline 为 FP=DIST155NM、FN=DIST5NM；LoRA 为 FP=DIST15NM、FN=DIST5NM。两者 TP 都为 0、FP/FN 数量相同。错误数字看起来更接近参考或文本更流畅，都不满足 entity-value 精确匹配。

- 参考实体：distance=DIST5NM
- LoRA 错误新增（FP）：distance=DIST15NM
- LoRA 漏报（FN）：distance=DIST5NM

**训练前后判断。** 错值改变，实体计数没有改善。

**可能原因与证据边界。** 待验证：five/fifteen 的发音混淆、数字生成错误，或参考读法不一致。现有文本不能证明音频中读的是 five。

**改进与验证建议。** 听取距离附近的音频；按逐位数字、整词数字和 teen 结尾分组检查。后续对照使用固定的规范值匹配，不允许“数值接近”算正确。

## 从案例得到的行动顺序

1. **优先核查整句模板替换。** 从 E02/E03/E04 及其他 EXO321 样本听音，核验文件映射、有效语音、时长与预处理。先排除输入与参考问题，再判断是否为模型退化。输出长度或非空率不能替代内容正确性。
2. **把数字、实体类型和单位一起检查。** E05/E06/E08 表明数字附近的触发词或单位改变会导致意义变化；不能只看数字是否保留。E10 表明 155→15 仍不是正确的 5。
3. **保留既有实体评估口径，单列解析局限。** 呼号前缀仅覆盖已有 9 类，bay 无类别，runway in use 不被当前模式提取，two ninety zero 不被 FL 数字解析接受。不要把“未统计”当作“无错”，也不要用临时映射消除当前错误。
4. **如追加训练，做受控对照。** 在输入链路核查之后，再比较更短训练/较小学习率或完整实体 span 加权；当前没有中间 checkpoint，不能凭空挑选本轮最佳中途权重。每次只改变一个因素，所有选择只用 dev。
5. **最终选择同时报告收益与代价。** 保留 WER/Exact 改善及实体 FP/F1 退化的全部证据。10 条案例不是改写参考、删除难例、改 test 或宣布某种改进有效的依据。

## 完成状态

已完成 10 条独立样本的文本层面分类错误分析：有原始证据、前后对照、词级/实体计数、明确的判断与可检验建议。可作为任务一“至少 10 个错误进行分类分析”的报告材料。音频听辨与声学根因确认尚未完成，报告没有声称已完成这些工作；这不替代最终 test、效率评估等其他验收项。

## 样本追溯

- E01 / row_id=2 / sql_id=843022 / record_set=recording_score_record_20260408
  - archive_path：`/data/home/scyb475/run/data/recordingRecord 20260408.zip`
  - archive_member：`recordingRecord 20260408/843022/20260303170726.mp3`
- E02 / row_id=6 / sql_id=1191514 / record_set=recording_score_record_20260408
  - archive_path：`/data/home/scyb475/run/data/recordingRecord 20260408.zip`
  - archive_member：`recordingRecord 20260408/1191514/20260323172031.mp3`
- E03 / row_id=82 / sql_id=840304 / record_set=recording_score_record_20260408
  - archive_path：`/data/home/scyb475/run/data/recordingRecord 20260408.zip`
  - archive_member：`recordingRecord 20260408/840304/20260303144848.mp3`
- E04 / row_id=25 / sql_id=1003892 / record_set=recording_score_record_20260408
  - archive_path：`/data/home/scyb475/run/data/recordingRecord 20260408.zip`
  - archive_member：`recordingRecord 20260408/1003892/20260316113103.mp3`
- E05 / row_id=145 / sql_id=1107410 / record_set=recording_score_record_20260408
  - archive_path：`/data/home/scyb475/run/data/recordingRecord 20260408.zip`
  - archive_member：`recordingRecord 20260408/1107410/20260321105106.mp3`
- E06 / row_id=241 / sql_id=1535660 / record_set=recording_score_record_20260408
  - archive_path：`/data/home/scyb475/run/data/recordingRecord 20260408.zip`
  - archive_member：`recordingRecord 20260408/1535660/20260331084637.mp3`
- E07 / row_id=24 / sql_id=861036 / record_set=recording_score_record_20260408
  - archive_path：`/data/home/scyb475/run/data/recordingRecord 20260408.zip`
  - archive_member：`recordingRecord 20260408/861036/20260305003152.mp3`
- E08 / row_id=1031 / sql_id=81958 / record_set=recording_score_record_20260115
  - archive_path：`/data/home/scyb475/run/data/recordingRecord 20260115.zip`
  - archive_member：`recordingRecord 20260115/81958/20260114200748.mp3`
- E09 / row_id=1116 / sql_id=9932 / record_set=recording_score_record_20260115
  - archive_path：`/data/home/scyb475/run/data/recordingRecord 20260115.zip`
  - archive_member：`recordingRecord 20260115/9932/20251229132530.mp3`
- E10 / row_id=173 / sql_id=1288968 / record_set=recording_score_record_20260408
  - archive_path：`/data/home/scyb475/run/data/recordingRecord 20260408.zip`
  - archive_member：`recordingRecord 20260408/1288968/20260326071358.mp3`

## 文件与复现

- `ERROR_ANALYSIS_10.md`：本报告。
- `error_cases_10.json`：10 条完整参考/原始与规范化预测、实体 span、分类、建议和单句指标。
- `source_evidence.json`：从服务器既有记录提取的原始证据，包含输入指纹。
- `source_inputs.sha256`：源 dev 清单、两模型 CSV 和实体结果的 SHA-256。
- `validation.json`：样本数、身份、文本一致性、实体集合和词级距离检查结果。
- `build_error_analysis.py`：生成报告与逐条指标的脚本；使用 Python 标准库。

服务器归档目录：`/data/home/scyb475/run/czm/results/error_analysis_dev_167720_v1`。未复制音频和模型权重。

在归档目录中重新生成报告（写入新的时间戳子目录）：

```bash
cd /data/home/scyb475/run/czm/results/error_analysis_dev_167720_v1
python3 -B build_error_analysis.py --evidence source_evidence.json --output "rebuild_$(date -u +%Y%m%dT%H%M%SZ)"
```
