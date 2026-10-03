# 实体错误初步诊断（仅文本，尚未听音）

这些计数描述预测与参考及固定解析规则的差异，不能据此确定真实音频内容或训练退化的根因。

- LoRA 在 159 条参考未包含该规则实体值的样本中输出 EXO321。
- Baseline 的 67 条规范化空输出中，有 57 条被 LoRA 替换为含有该新增呼号的文本。
- 这 67 条中，LoRA 达到整句完全匹配的数量为 0。
- 因此空输出降至零不代表原来的空输出样本被正确识别。
- 下一步应抽取重复模板样本听音，检查音频是否为空/过短/被截断、参考是否准确及模型生成行为；目前不修改规则、不使用 test 调参。

## 人工复核候选

### row_id=2，关注 callsign

- 参考：air cruiser tree tree zero one roger maintenance will be there soon the runway inspectors retrieved a single piece of rubber on the runway
- Baseline：proviso three three zero one roger maintenance will be there soon the runway inspectors re tri re tried a single piece of rubber on the runway
- LoRA：probe zero tree tree zero one roger maintenance will be there soon the runway inspectors retrieved a single piece of rubber on the runway
- 参考实体：[["callsign", "CALLSIGN:air_cruiser:3301"]]
- LoRA FP：[]
- LoRA FN：[["callsign", "CALLSIGN:air_cruiser:3301"]]

### row_id=6，关注 callsign

- 参考：deviation from the route is limited within five kilometers on each side due to dangerous area
- Baseline：（规范化为空）
- LoRA：exo tree two one nanyue approach roger report your intentions
- 参考实体：[["distance", "DIST5KM"]]
- LoRA FP：[["callsign", "CALLSIGN:exo:321"]]
- LoRA FN：[["distance", "DIST5KM"]]

### row_id=15，关注 callsign

- 参考：the latest weather information of surface wind zero two zero degrees five meters per second gusting twelve meters per second visibility one tousand five hundred meters moderate to heavy rain with thunderstorm will last for at least thirty minutes
- Baseline：yes
- LoRA：exo tree two one roger mayday report your intentions
- 参考实体：[]
- LoRA FP：[["callsign", "CALLSIGN:exo:321"]]
- LoRA FN：[]

### row_id=50，关注 distance

- 参考：we can see a typhoon at ten o'clock about five miles request a right turn immediately
- Baseline：（规范化为空）
- LoRA：exo tree two one report the reason for missed approach
- 参考实体：[["distance", "DIST5NM"]]
- LoRA FP：[["callsign", "CALLSIGN:exo:321"]]
- LoRA FN：[["distance", "DIST5NM"]]

### row_id=82，关注 distance

- 参考：divert
- Baseline：i just realized that i have been working hard on something for more than a year in his eyes it is nothing in order to make the show better he can be good at it
- LoRA：exo tree two one we are going to make a turn at one o'clock fifteen miles ahead of us
- 参考实体：[]
- LoRA FP：[["callsign", "CALLSIGN:exo:321"], ["distance", "DIST15NM"]]
- LoRA FN：[]

### row_id=25，关注 time

- 参考：level restriction from zero two tree zero utc to zero six zero zero utc and using flight level tree two zero as a temporary level
- Baseline：thank you very much
- LoRA：exo tree two one nanyue approach roger report your intentions
- 参考实体：[["flight_level", "FL320"], ["time", "TIME0230UTC"], ["time", "TIME0600UTC"]]
- LoRA FP：[["callsign", "CALLSIGN:exo:321"]]
- LoRA FN：[["flight_level", "FL320"], ["time", "TIME0230UTC"], ["time", "TIME0600UTC"]]

### row_id=145，关注 time

- 参考：roger from zero two zero zero utc to zero six zero zero utc flight level two niner zero to flight level tree tree zero is not available for bunta traffic
- Baseline：roger from zero two zero zero utc to zero six zero zero utc flight level two ninety zero to flight level three three zero is not available for bonnet traffic
- LoRA：roger flight level two zero zero utc to zero six zero zero utc flight level two niner zero to flight level tree tree zero is not available for bunta traffic
- 参考实体：[["flight_level", "FL290"], ["flight_level", "FL330"], ["time", "TIME0200UTC"], ["time", "TIME0600UTC"]]
- LoRA FP：[["flight_level", "FL200"]]
- LoRA FN：[["time", "TIME0200UTC"]]

### row_id=29，关注 runway

- 参考：we're changing the runway in use now runway one niner will be available in ten minutes you are number six in sequence
- Baseline：you
- LoRA：exo tree two one report the reason for missed approach
- 参考实体：[["runway", "RWY19"]]
- LoRA FP：[["callsign", "CALLSIGN:exo:321"]]
- LoRA FN：[["runway", "RWY19"]]

### row_id=241，关注 runway

- 参考：a suitcase seems to be left behind on bay two one seven confirm you have it in sight
- Baseline：call sign a suitcase seems to be left behind on bay two one seven confirm you have it inside
- LoRA：corsair a suitcase seems to be left behind on runway two one seven confirm you have it in sight
- 参考实体：[]
- LoRA FP：[["runway", "RWY217"]]
- LoRA FN：[]

### row_id=24，关注 flight_level

- 参考：roger from zero four zero zero utc to zero six zero zero utc flight level tree one zero or below for bunta traffic
- Baseline：roger from zero four zero zero utc two zero six zero zero utc by level three one zero below for bound traffic
- LoRA：roger from zero four zero zero utc to zero six zero zero utc by level tree one zero below for band traffic
- 参考实体：[["flight_level", "FL310"], ["time", "TIME0400UTC"], ["time", "TIME0600UTC"]]
- LoRA FP：[]
- LoRA FN：[["flight_level", "FL310"]]

### row_id=1031，关注 speed

- 参考：we've just encountered wind shear wind aloft changed from two tree zero degrees one tree zero knots to two five zero degrees seven zero knots the aircraft pitched up for a while to avoid overspeed we didn't have time to request approval and request a lower level now
- Baseline：encountered wind shear wind aloft changed from two hundred thirty degrees one three zero knots to two five zero degrees seven zero knots the aircraft pitched up for a while to avoid over speed we didn't have time to request approval and request a lower level now
- LoRA：we encountered wind shear wind aloft changed from two hundred thirty zero degrees one zero tree zero degrees to two five zero degrees seven zero degrees the aircraft pitched up for a while to avoid over speed we didn't have time to request approval and request a lower level now
- 参考实体：[["speed", "SPD130KT"], ["speed", "SPD70KT"]]
- LoRA FP：[]
- LoRA FN：[["speed", "SPD130KT"], ["speed", "SPD70KT"]]

### row_id=1116，关注 qnh

- 参考：weather information of airport surface wind two five zero degrees tree meters per second visibility two tousand two hundred meters temperature tree one dewpoint two niner qnh one zero zero five runway in use zero two right
- Baseline：vanar information of location approach surface wind two five zero degrees three meters per second visibility two thousand two hundred meters temperature three one dew point two nine qnh one zero zero five runway units zero to right
- LoRA：vary information of the airport surface wind two five zero degrees tree meters per second visibility two tousand two hundred meters temperature tree one due point two niner qns one zero zero five runway in sight zero two right
- 参考实体：[["qnh", "QNH1005"]]
- LoRA FP：[]
- LoRA FN：[["qnh", "QNH1005"]]
