# 任务二：20 个 dev 错误与恢复案例

全部案例来自 Task1-ASR dev 输入，未使用 test，未听音。词错误数按冻结 `normalize_eval` 逐句计算。

| ID | row | 类别 | Raw/Guarded/Legacy/保守错误数 | Gate |
|---|---:|---|---:|---|
| T2-01 | 48 | accepted_candidate_improves_vs_legacy | 5/5/8/5 | accept |
| T2-02 | 79 | accepted_candidate_improves_vs_legacy | 8/8/11/8 | accept |
| T2-03 | 597 | accepted_candidate_improves_vs_legacy | 6/6/9/6 | accept |
| T2-04 | 24 | accepted_candidate_improves_vs_legacy | 4/4/6/4 | accept |
| T2-05 | 257 | accepted_candidate_improves_vs_legacy | 19/19/20/19 | accept |
| T2-06 | 908 | raw_regresses_vs_legacy | 173/113/113/113 | generation_length_cap |
| T2-07 | 183 | raw_regresses_vs_legacy | 9/12/4/12 | unsupported_content_or_entity_change |
| T2-08 | 671 | raw_regresses_vs_legacy | 8/11/3/11 | unsupported_content_or_entity_change |
| T2-09 | 841 | raw_regresses_vs_legacy | 98/93/93/93 | generation_length_cap |
| T2-10 | 435 | raw_regresses_vs_legacy | 8/11/4/11 | unsupported_content_or_entity_change |
| T2-11 | 1181 | gate_rejects_harmful_candidate | 16/11/14/11 | unsupported_content_or_entity_change |
| T2-12 | 456 | gate_rejects_harmful_candidate | 10/6/11/6 | unsupported_content_or_entity_change |
| T2-13 | 645 | gate_rejects_harmful_candidate | 11/7/10/7 | unsupported_content_or_entity_change |
| T2-14 | 806 | gate_rejects_harmful_candidate | 10/6/8/6 | unsupported_content_or_entity_change |
| T2-15 | 1117 | gate_rejects_harmful_candidate | 20/16/16/16 | unsupported_content_or_entity_change |
| T2-16 | 258 | gate_rejects_beneficial_candidate | 61/125/60/125 | generation_length_cap |
| T2-17 | 547 | gate_rejects_beneficial_candidate | 5/11/10/11 | unsupported_content_or_entity_change |
| T2-18 | 805 | gate_rejects_beneficial_candidate | 6/12/6/12 | unsupported_content_or_entity_change |
| T2-19 | 32 | gate_rejects_beneficial_candidate | 1/6/0/6 | unsupported_content_or_entity_change |
| T2-20 | 84 | gate_rejects_beneficial_candidate | 4/9/6/9 | unsupported_content_or_entity_change |

## T2-01 · row_id=48 · accepted_candidate_improves_vs_legacy

候选通过 gate，词错误数低于 legacy rules；但通常与保守规则规范化后相同，收益不能全部归因于 T5。

- 样本：sql_id=1110444；subset=04；split=dev；audio_reviewed=false。
- Task1-ASR 输入：corresponding aircraft niner two two four the airport management department has already sent a squad to remove the tire fragments remain at this frequency i'll call you as soon as the taxiway is available
- Canonical 参考：DPC9224, the Airport Management Department has already sent a squad to remove the tire fragments, remain this frequency, I will call you as soon as the taxiway is available.
- T5 raw（5 errors）：corresponding aircraft 9224, the airport management department has already sent a squad to remove the tire fragments, remain at this frequency. I'll call you as soon as the taxiway is available.
- T5 guarded（5 errors）：corresponding aircraft 9224, the airport management department has already sent a squad to remove the tire fragments, remain at this frequency. I'll call you as soon as the taxiway is available.
- Legacy rules（8 errors）：corresponding aircraft niner two two four the airport management department has already sent a squad to remove the tire fragments remain at this frequency i ll call you as soon as the taxiway is available
- 保守回退（5 errors）：corresponding aircraft 9224 the airport management department has already sent a squad to remove the tire fragments remain at this frequency i'll call you as soon as the taxiway is available
- Gate：accepted=true；reason=accepted；EOS=true。
- raw_t5 实体：FP=[]；FN=[['callsign', 'DPC9224']]。
- guarded_t5 实体：FP=[]；FN=[['callsign', 'DPC9224']]。
- legacy_rules 实体：FP=[]；FN=[['callsign', 'DPC9224']]。

## T2-02 · row_id=79 · accepted_candidate_improves_vs_legacy

候选通过 gate，词错误数低于 legacy rules；但通常与保守规则规范化后相同，收益不能全部归因于 T5。

- 样本：sql_id=951694；subset=03；split=dev；audio_reviewed=false。
- Task1-ASR 输入：you are not on echo not taxi we are at zero four zero zero
- Canonical 参考：you are now on E, and the taxiway ahead is T4.
- T5 raw（8 errors）：you are not on echo, not taxi, we are at 0400.
- T5 guarded（8 errors）：you are not on echo, not taxi, we are at 0400.
- Legacy rules（11 errors）：you are not on echo not taxi we are at zero four zero zero
- 保守回退（8 errors）：you are not on echo not taxi we are at 0400
- Gate：accepted=true；reason=accepted；EOS=true。

## T2-03 · row_id=597 · accepted_candidate_improves_vs_legacy

候选通过 gate，词错误数低于 legacy rules；但通常与保守规则规范化后相同，收益不能全部归因于 T5。

- 样本：sql_id=1244288；subset=03；split=dev；audio_reviewed=false。
- Task1-ASR 输入：a suitcase seems to be left behind at the base one two one seven have you got it in sight
- Canonical 参考：a suitcase seems to be left behind on bay 217, confirm you have it in sight.
- T5 raw（6 errors）：a suitcase seems to be left behind at the base 1217, have you got it in sight?
- T5 guarded（6 errors）：a suitcase seems to be left behind at the base 1217, have you got it in sight?
- Legacy rules（9 errors）：a suitcase seems to be left behind at the base one two one seven have you got it in sight
- 保守回退（6 errors）：a suitcase seems to be left behind at the base 1217 have you got it in sight
- Gate：accepted=true；reason=accepted；EOS=true。

## T2-04 · row_id=24 · accepted_candidate_improves_vs_legacy

候选通过 gate，词错误数低于 legacy rules；但通常与保守规则规范化后相同，收益不能全部归因于 T5。

- 样本：sql_id=861036；subset=04；split=dev；audio_reviewed=false。
- Task1-ASR 输入：roger from zero four zero zero utc to zero six zero zero utc by level tree one zero below for band traffic
- Canonical 参考：Roger. From 0400 UTC to 0600 UTC, FL310 or below for BUNTA traffic.
- T5 raw（4 errors）：Roger, from 0400 UTC to 0600 UTC, by level 310 below for band traffic.
- T5 guarded（4 errors）：Roger, from 0400 UTC to 0600 UTC, by level 310 below for band traffic.
- Legacy rules（6 errors）：roger from 0400 UTC to 0600 UTC by level tree one zero below for band traffic
- 保守回退（4 errors）：roger from 0400 UTC to 0600 UTC by level 310 below for band traffic
- Gate：accepted=true；reason=accepted；EOS=true。
- raw_t5 实体：FP=[]；FN=[['flight_level', 'FL310']]。
- guarded_t5 实体：FP=[]；FN=[['flight_level', 'FL310']]。
- legacy_rules 实体：FP=[]；FN=[['flight_level', 'FL310']]。

## T2-05 · row_id=257 · accepted_candidate_improves_vs_legacy

候选通过 gate，词错误数低于 legacy rules；但通常与保守规则规范化后相同，收益不能全部归因于 T5。

- 样本：sql_id=898842；subset=02/01；split=dev；audio_reviewed=false。
- Task1-ASR 输入：exo tree two one we are going to make a turn on the runway zero two zero to avoid the weather report your intentions
- Canonical 参考：maintenance
- T5 raw（19 errors）：EXO321, we are going to make a turn on the RWY 020 to avoid the weather, report your intentions.
- T5 guarded（19 errors）：EXO321, we are going to make a turn on the RWY 020 to avoid the weather, report your intentions.
- Legacy rules（20 errors）：EXO321 we are going to make a turn on the RWY 02 zero to avoid the weather report your intentions
- 保守回退（19 errors）：EXO321 we are going to make a turn on the runway 020 to avoid the weather report your intentions
- Gate：accepted=true；reason=accepted；EOS=true。
- raw_t5 实体：FP=[['callsign', 'EXO321']]；FN=[]。
- guarded_t5 实体：FP=[['callsign', 'EXO321']]；FN=[]。
- legacy_rules 实体：FP=[['callsign', 'EXO321'], ['runway', 'RWY02']]；FN=[]。

## T2-06 · row_id=908 · raw_regresses_vs_legacy

T5 原始候选比 legacy rules 产生更多词错误；检查是否存在数值合并、重复或长度截断。

- 样本：sql_id=1184420；subset=03；split=dev；audio_reviewed=false。
- Task1-ASR 输入：mayday mayday mayday we've encountered a lightning strike over the navi at our right the fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel
- Canonical 参考：Mayday Mayday Mayday, Approach, , we've encountered lightning strike over , rear fuselage damaged, left elevator lost, request priority landing.
- T5 raw（173 errors）：MAYDAY MAYDAY MAYDAY,, we've encountered a lightning strike over the navi at our right. The fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel
- T5 guarded（113 errors）：mayday mayday mayday we've encountered a lightning strike over the navi at our right the fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel
- Legacy rules（113 errors）：MAYDAY MAYDAY MAYDAY we ve encountered a lightning strike over the navi at our right the fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel
- 保守回退（113 errors）：mayday mayday mayday we've encountered a lightning strike over the navi at our right the fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel fuel
- Gate：accepted=false；reason=generation_length_cap；EOS=false。

## T2-07 · row_id=183 · raw_regresses_vs_legacy

T5 原始候选比 legacy rules 产生更多词错误；检查是否存在数值合并、重复或长度截断。

- 样本：sql_id=1229798；subset=03；split=dev；audio_reviewed=false。
- Task1-ASR 输入：the latest weather information of the location surface wind zero two zero degrees five meters per second gusting one two meters per second visibility one tousand five hundred meters moderate to heavy rain with thunderstorms last for at least tree zero minutes
- Canonical 参考：the latest weather information of , surface wind 020 degrees, 5 m or s, gusting 12 m or s, visibility 1500m, moderate to heavy rain with thunderstorm will last for at least 30 minutes.
- T5 raw（9 errors）：the latest weather information of the location, surface wind 020 degrees, 5m or s, gusting 12m or s, visibility 1500m, moderate to heavy rain, with thunderstorms last for at least 300 minutes.
- T5 guarded（12 errors）：the latest weather information of the location surface wind 020 degrees 5m per second gusting 12m per second visibility 1500m moderate to heavy rain with thunderstorms last for at least 30 minutes
- Legacy rules（4 errors）：the latest weather information of the location surface wind 020 degrees 5 m/s gusting 12 m/s visibility 1500m moderate to heavy rain with thunderstorms last for at least 30 minutes
- 保守回退（12 errors）：the latest weather information of the location surface wind 020 degrees 5m per second gusting 12m per second visibility 1500m moderate to heavy rain with thunderstorms last for at least 30 minutes
- Gate：accepted=false；reason=unsupported_content_or_entity_change；EOS=true。
- guarded_t5 实体：FP=[]；FN=[['altitude_m', '12M'], ['altitude_m', '5M']]。

## T2-08 · row_id=671 · raw_regresses_vs_legacy

T5 原始候选比 legacy rules 产生更多词错误；检查是否存在数值合并、重复或长度截断。

- 样本：sql_id=1199282；subset=03；split=dev；audio_reviewed=false。
- Task1-ASR 输入：the latest weather information service wind zero two zero degrees five meters per second gusting one two meters per second visibility one tousand five hundred meters moderate heavy rain with thunderstorm will last for at least tree zero minutes
- Canonical 参考：the latest weather information of , surface wind 020 degrees, 5 m or s, gusting 12 m or s, visibility 1500m, moderate to heavy rain with thunderstorm will last for at least 30 minutes.
- T5 raw（8 errors）：the latest weather information service, wind 020 degrees, 5m or s, gusting 12m or s, visibility 1500m, moderate heavy rain with thunderstorm will last for at least 300 minutes.
- T5 guarded（11 errors）：the latest weather information service wind 020 degrees 5m per second gusting 12m per second visibility 1500m moderate heavy rain with thunderstorm will last for at least 30 minutes
- Legacy rules（3 errors）：the latest weather information service wind 020 degrees 5 m/s gusting 12 m/s visibility 1500m moderate heavy rain with thunderstorm will last for at least 30 minutes
- 保守回退（11 errors）：the latest weather information service wind 020 degrees 5m per second gusting 12m per second visibility 1500m moderate heavy rain with thunderstorm will last for at least 30 minutes
- Gate：accepted=false；reason=unsupported_content_or_entity_change；EOS=true。
- guarded_t5 实体：FP=[]；FN=[['altitude_m', '12M'], ['altitude_m', '5M']]。

## T2-09 · row_id=841 · raw_regresses_vs_legacy

T5 原始候选比 legacy rules 产生更多词错误；检查是否存在数值合并、重复或长度截断。

- 样本：sql_id=840820；subset=03；split=dev；audio_reviewed=false。
- Task1-ASR 输入：exo tree two one we are going to make a turn at ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock ten o'clock
- Canonical 参考：radar shows the field is covered by thunderstorm and unable to land, request maintain level and hold at the west side of the field.
- T5 raw（98 errors）：EXO321, we are going to make a turn at 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'clock, 10 o'
- T5 guarded（93 errors）：EXO321 we are going to make a turn at 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock
- Legacy rules（93 errors）：EXO321 we are going to make a turn at 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock
- 保守回退（93 errors）：EXO321 we are going to make a turn at 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock 10 o'clock
- Gate：accepted=false；reason=generation_length_cap；EOS=false。
- raw_t5 实体：FP=[['callsign', 'EXO321']]；FN=[]。
- guarded_t5 实体：FP=[['callsign', 'EXO321']]；FN=[]。
- legacy_rules 实体：FP=[['callsign', 'EXO321']]；FN=[]。

## T2-10 · row_id=435 · raw_regresses_vs_legacy

T5 原始候选比 legacy rules 产生更多词错误；检查是否存在数值合并、重复或长度截断。

- 样本：sql_id=886358；subset=03；split=dev；audio_reviewed=false。
- Task1-ASR 输入：the latest weather information of the location surface wind zero two zero degrees five meters per second gusting one two meters per second with speed one tousand five hundred meters moderate to heavy rain with thunderstorm will last for at least thirty minutes
- Canonical 参考：the latest weather information of , surface wind 020 degrees, 5 m or s, gusting 12 m or s, visibility 1500m, moderate to heavy rain with thunderstorm will last for at least 30 minutes.
- T5 raw（8 errors）：the latest weather information of the location, surface wind 020 degrees, 5m or s, gusting 12m or s, with speed 1500m, moderate to heavy rain, with thunderstorm will last for at least 30 minutes.
- T5 guarded（11 errors）：the latest weather information of the location surface wind 020 degrees 5m per second gusting 12m per second with speed 1500m moderate to heavy rain with thunderstorm will last for at least 30 minutes
- Legacy rules（4 errors）：the latest weather information of the location surface wind 020 degrees 5 m/s gusting 12 m/s with speed 1500m moderate to heavy rain with thunderstorm will last for at least 30 minutes
- 保守回退（11 errors）：the latest weather information of the location surface wind 020 degrees 5m per second gusting 12m per second with speed 1500m moderate to heavy rain with thunderstorm will last for at least 30 minutes
- Gate：accepted=false；reason=unsupported_content_or_entity_change；EOS=true。
- guarded_t5 实体：FP=[]；FN=[['altitude_m', '12M'], ['altitude_m', '5M']]。

## T2-11 · row_id=1181 · gate_rejects_harmful_candidate

T5 候选比保守回退更差，gate 的拒绝降低了该句词错误。

- 样本：sql_id=23450；subset=03；split=dev；audio_reviewed=false。
- Task1-ASR 输入：we'll share information of the airport surface wind two five zero degrees tree meters per second visibility two two zero zero meters temperature tree one two point two niner qnh one zero zero five runway zero two right
- Canonical 参考：weather information of airport, surface wind 250 degrees, 3 meters per second, visibility 2200m, temperature 31, dewpoint 29, QNH 1005, runway in use 02R.
- T5 raw（16 errors）：we'll share information of the airport surface wind 25000 degrees, 3m or s, visibility 2000m, temperature 312 point 229, QNH 1005, RWY 02R.
- T5 guarded（11 errors）：we'll share information of the airport surface wind 250 degrees 3m per second visibility 2200m temperature 312 point 29 QNH 1005 RWY 02R
- Legacy rules（14 errors）：we ll share information of the airport surface wind 250 degrees 3 m/s visibility 2200m temperature 31 two point two niner QNH 1005 RWY 02R
- 保守回退（11 errors）：we'll share information of the airport surface wind 250 degrees 3m per second visibility 2200m temperature 312 point 29 QNH 1005 RWY 02R
- Gate：accepted=false；reason=unsupported_content_or_entity_change；EOS=true。
- raw_t5 实体：FP=[['altitude_m', '2000M'], ['altitude_m', '3M']]；FN=[['altitude_m', '2200M']]。
- legacy_rules 实体：FP=[['altitude_m', '3M']]；FN=[]。

## T2-12 · row_id=456 · gate_rejects_harmful_candidate

T5 候选比保守回退更差，gate 的拒绝降低了该句词错误。

- 样本：sql_id=101180；subset=03；split=dev；audio_reviewed=false。
- Task1-ASR 输入：wide information of the airport surface wind two five zero degrees tree meters per second visibility two tousand two hundred meters temperature thirty one due point two niner qnh one zero zero five runway in use zero two right
- Canonical 参考：weather information of airport, surface wind 250 degrees, 3 meters per second, visibility 2200m, temperature 31, dewpoint 29, QNH 1005, runway in use 02R.
- T5 raw（10 errors）：wide information of the airport surface, wind 25000 degrees, 3m or s, visibility 2200m, temperature 301, due point 29 QNH 1005, runway in use 02R.
- T5 guarded（6 errors）：wide information of the airport surface wind 250 degrees 3m per second visibility 2200m temperature 31 due point 29 QNH 1005 runway in use 02R
- Legacy rules（11 errors）：wide information of the airport surface wind 250 degrees 3 m/s visibility 2200m temperature thirty one due point two niner QNH 1005 runway in use 02R
- 保守回退（6 errors）：wide information of the airport surface wind 250 degrees 3m per second visibility 2200m temperature 31 due point 29 QNH 1005 runway in use 02R
- Gate：accepted=false；reason=unsupported_content_or_entity_change；EOS=true。
- raw_t5 实体：FP=[['altitude_m', '3M']]；FN=[]。
- legacy_rules 实体：FP=[['altitude_m', '3M']]；FN=[]。

## T2-13 · row_id=645 · gate_rejects_harmful_candidate

T5 候选比保守回退更差，gate 的拒绝降低了该句词错误。

- 样本：sql_id=889476；subset=03；split=dev；audio_reviewed=false。
- Task1-ASR 输入：we have information of nanyue airport surface wind two five zero degrees tree meters per second visibility two tousand two hundred meters temperature tree one two point two niner qnh one zero zero five runway in use zero two right
- Canonical 参考：weather information of airport, surface wind 250 degrees, 3 meters per second, visibility 2200m, temperature 31, dewpoint 29, QNH 1005, runway in use 02R.
- T5 raw（11 errors）：we have information of Nanyue airport, surface wind 25000 degrees, 3m or s, visibility 2200m, temperature 325, QNH 1005, runway in use 02R.
- T5 guarded（7 errors）：we have information of nanyue airport surface wind 250 degrees 3m per second visibility 2200m temperature 312 point 29 QNH 1005 runway in use 02R
- Legacy rules（10 errors）：we have information of nanyue airport surface wind 250 degrees 3 m/s visibility 2200m temperature 31 two point two niner QNH 1005 runway in use 02R
- 保守回退（7 errors）：we have information of nanyue airport surface wind 250 degrees 3m per second visibility 2200m temperature 312 point 29 QNH 1005 runway in use 02R
- Gate：accepted=false；reason=unsupported_content_or_entity_change；EOS=true。
- raw_t5 实体：FP=[['altitude_m', '3M']]；FN=[]。
- legacy_rules 实体：FP=[['altitude_m', '3M']]；FN=[]。

## T2-14 · row_id=806 · gate_rejects_harmful_candidate

T5 候选比保守回退更差，gate 的拒绝降低了该句词错误。

- 样本：sql_id=56242；subset=04；split=dev；audio_reviewed=false。
- Task1-ASR 输入：roger chile star tree five four maintain flight level tree two zero over a kilo approved
- Canonical 参考：Roger. CZX354 maintaining FL320 over IKELA approved.
- T5 raw（10 errors）：Roger. Chile Star 3,5, maintain flight level 32 over a kilo approved.
- T5 guarded（6 errors）：roger chile star 354 maintain FL320 over a kilo approved
- Legacy rules（8 errors）：roger chile star tree five four maintain FL320 over a kilo approved
- 保守回退（6 errors）：roger chile star 354 maintain FL320 over a kilo approved
- Gate：accepted=false；reason=unsupported_content_or_entity_change；EOS=true。
- raw_t5 实体：FP=[['flight_level', 'FL32']]；FN=[['callsign', 'CZX354'], ['flight_level', 'FL320']]。
- guarded_t5 实体：FP=[]；FN=[['callsign', 'CZX354']]。
- legacy_rules 实体：FP=[]；FN=[['callsign', 'CZX354']]。

## T2-15 · row_id=1117 · gate_rejects_harmful_candidate

T5 候选比保守回退更差，gate 的拒绝降低了该句词错误。

- 样本：sql_id=17440；subset=03；split=dev；audio_reviewed=false。
- Task1-ASR 输入：we've just encountered a windshear with the wind lift changing from two tree zero degrees one tree zero knots to two five zero degrees seven zero knots the aircraft pitched up well to avoid overspeed we didn't have time to request a proof and request a lower level niner
- Canonical 参考：we've just encountered wind shear, wind aloft changed from 230 degrees 130 knots to 250 degrees 70 knots. The aircraft pitched up for a while to avoid overspeed. We didn't have time to request approval and request a lower level now.
- T5 raw（20 errors）：we've just encountered a windshear, with the wind lift changing from 2000 degrees to 2550 degrees, the aircraft pitched up well to avoid overspeed. We didn't have time to request a proof and request a lower level 9 or 9)
- T5 guarded（16 errors）：we've just encountered a windshear with the wind lift changing from 230 degrees 130kt to 250 degrees 70kt the aircraft pitched up well to avoid overspeed we didn't have time to request a proof and request a lower level niner
- Legacy rules（16 errors）：we ve just encountered a windshear with the wind lift changing from 230 degrees 130kt to 250 degrees 70kt the aircraft pitched up well to avoid overspeed we didn t have time to request a proof and request a lower level niner
- 保守回退（16 errors）：we've just encountered a windshear with the wind lift changing from 230 degrees 130kt to 250 degrees 70kt the aircraft pitched up well to avoid overspeed we didn't have time to request a proof and request a lower level niner
- Gate：accepted=false；reason=unsupported_content_or_entity_change；EOS=true。
- raw_t5 实体：FP=[]；FN=[['speed', '130KT'], ['speed', '70KT']]。

## T2-16 · row_id=258 · gate_rejects_beneficial_candidate

T5 候选词错误少于保守回退，但因内容/实体变化或长度上限被拒；这不等于候选全部正确。

- 样本：sql_id=1050864；subset=03；split=dev；audio_reviewed=false。
- Task1-ASR 输入：pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan
- Canonical 参考：PANPAN PANPAN PANPAN, , we have to fly heading 220 to avoid weather ahead, and we also request higher.
- T5 raw（61 errors）：PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN
- T5 guarded（125 errors）：pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan
- Legacy rules（60 errors）：PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN PANPAN pan
- 保守回退（125 errors）：pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan pan
- Gate：accepted=false；reason=generation_length_cap；EOS=false。
- raw_t5 实体：FP=[]；FN=[['heading', 'HEADING220']]。
- guarded_t5 实体：FP=[]；FN=[['heading', 'HEADING220']]。
- legacy_rules 实体：FP=[]；FN=[['heading', 'HEADING220']]。

## T2-17 · row_id=547 · gate_rejects_beneficial_candidate

T5 候选词错误少于保守回退，但因内容/实体变化或长度上限被拒；这不等于候选全部正确。

- 样本：sql_id=72022；subset=04；split=dev；audio_reviewed=false。
- Task1-ASR 输入：roger china star tree five four four over the cala flight level five tree two zero approved
- Canonical 参考：Roger. CZX354 maintaining FL320 over IKELA approved.
- T5 raw（5 errors）：Roger. CZX4544, over the CALA, FL350 approved.
- T5 guarded（11 errors）：roger china star tree five four four over the cala flight level 5320 approved
- Legacy rules（10 errors）：roger china star tree five four four over the cala FL532 zero approved
- 保守回退（11 errors）：roger china star tree five four four over the cala flight level 5320 approved
- Gate：accepted=false；reason=unsupported_content_or_entity_change；EOS=true。
- raw_t5 实体：FP=[['callsign', 'CZX4544'], ['flight_level', 'FL350']]；FN=[['callsign', 'CZX354'], ['flight_level', 'FL320']]。
- guarded_t5 实体：FP=[]；FN=[['callsign', 'CZX354'], ['flight_level', 'FL320']]。
- legacy_rules 实体：FP=[['flight_level', 'FL532']]；FN=[['callsign', 'CZX354'], ['flight_level', 'FL320']]。

## T2-18 · row_id=805 · gate_rejects_beneficial_candidate

T5 候选词错误少于保守回退，但因内容/实体变化或长度上限被拒；这不等于候选全部正确。

- 样本：sql_id=1116030；subset=03；split=dev；audio_reviewed=false。
- Task1-ASR 输入：pan pan pan pan pan pan pan we have the flight heading two two zero to avoid weather hand and we just request a higher
- Canonical 参考：PANPAN PANPAN PANPAN, , we have to fly heading 220 to avoid weather ahead, and we also request higher.
- T5 raw（6 errors）：PANPAN PANPAN PANPAN,, we have the flight heading 230 to avoid weather, hand and we just request a higher.
- T5 guarded（12 errors）：pan pan pan pan pan pan pan we have the flight heading 220 to avoid weather hand and we just request a higher
- Legacy rules（6 errors）：PANPAN PANPAN PANPAN pan we have the flight heading 220 to avoid weather hand and we just request a higher
- 保守回退（12 errors）：pan pan pan pan pan pan pan we have the flight heading 220 to avoid weather hand and we just request a higher
- Gate：accepted=false；reason=unsupported_content_or_entity_change；EOS=true。
- raw_t5 实体：FP=[['heading', 'HEADING230']]；FN=[['heading', 'HEADING220']]。

## T2-19 · row_id=32 · gate_rejects_beneficial_candidate

T5 候选词错误少于保守回退，但因内容/实体变化或长度上限被拒；这不等于候选全部正确。

- 样本：sql_id=31918；subset=03；split=dev；audio_reviewed=false。
- Task1-ASR 输入：due to an error in the notam content a new notam numbered alpha zero one two four two two is issued to replace the notam numbered alpha zero one two tree two two
- Canonical 参考：Due to an error in the NOTAM content, a new NOTAM numbered A0124 or 22 is issued to replace the NOTAM numbered A0123 or 22.
- T5 raw（1 errors）：Due to an error in the NOTAM content, a new NOTAM numbered A0124 or 22 is issued to replace the NOTAM numbered A0126 or 22.
- T5 guarded（6 errors）：due to an error in the notam content a new notam numbered alpha 012422 is issued to replace the notam numbered alpha 012322
- Legacy rules（0 errors）：due to an error in the notam content a new notam numbered A0124/22 is issued to replace the notam numbered A0123/22
- 保守回退（6 errors）：due to an error in the notam content a new notam numbered alpha 012422 is issued to replace the notam numbered alpha 012322
- Gate：accepted=false；reason=unsupported_content_or_entity_change；EOS=true。

## T2-20 · row_id=84 · gate_rejects_beneficial_candidate

T5 候选词错误少于保守回退，但因内容/实体变化或长度上限被拒；这不等于候选全部正确。

- 样本：sql_id=899816；subset=03；split=dev；audio_reviewed=false。
- Task1-ASR 输入：pan pan pan pan pan pan we have flight heading two hundred twenty to avoid weather ahead and we also request height
- Canonical 参考：PANPAN PANPAN PANPAN, , we have to fly heading 220 to avoid weather ahead, and we also request higher.
- T5 raw（4 errors）：PANPAN PANPAN PANPAN,, we have flight heading 230 to avoid weather ahead, and we also request height.
- T5 guarded（9 errors）：pan pan pan pan pan pan we have flight heading 220 to avoid weather ahead and we also request height
- Legacy rules（6 errors）：PANPAN PANPAN PANPAN we have flight heading two hundred twenty to avoid weather ahead and we also request height
- 保守回退（9 errors）：pan pan pan pan pan pan we have flight heading 220 to avoid weather ahead and we also request height
- Gate：accepted=false；reason=unsupported_content_or_entity_change；EOS=true。
- raw_t5 实体：FP=[['heading', 'HEADING230']]；FN=[['heading', 'HEADING220']]。
- legacy_rules 实体：FP=[]；FN=[['heading', 'HEADING220']]。
