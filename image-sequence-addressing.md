# 图像序列寻址：文件帧号、图片序号与剪辑时间

分析对象：本仓库 checkout，commit `bad7ab5`，`ImageSequenceReference` schema 版本 1。
证据等级标注：

- **[源码]** 直接读源码得到的结论，附 `文件:行号`。
- **[实测]** 在本次分析中从本仓库源码编译核心库（`opentime/*`、`opentimelineio/*`，不含 `bundle.cpp`）后运行探针得到的结果。
- **[测试]** 仓库内已有测试对某一行为的断言支持（读测试代码得出，本环境未执行测试套件——仓库未预置构建产物）。
- **[待证媒体证据]** 无法由 OTIO 逻辑本身回答、必须取自文件系统/解码器/渲染器的证据。

> 关于构建：`src/deps/{Imath,pybind11,rapidjson,minizip-ng}` 在该 checkout 中为空子模块。探针使用
> `/usr/local` 的 Imath 与 PyPI sdist 中的 rapidjson 头文件编译；`bundle.cpp` 依赖 minizip-ng 未能链接，
> 因此 otioz/otiod 打包路径的结论仅来自源码阅读 + 对其循环算术的等价复现，标注为 **[源码+复算]**。

---

## 0. 结论摘要

1. 一个 `ImageSequenceReference` 里同时存在三套坐标：**时间（RationalTime）**、**图片序号（image number，
   0 起、连续）**、**文件帧号（frame number，写进文件名、可跳号、可负）**。三者没有一一对应关系，且
   `frame_for_time()` 返回的是**文件帧号空间里步长为 1 的连续整数**，不是图片序号。
2. 可用时长 → 图片数量是**按 `rate/frame_step` 重采样后向零取整**；最后一张图片的显示区间是
   `[start + (n-1)·step/rate, start + n·step/rate)`。`available_range` 尾部若不能被 `step` 整除，
   会留下**没有任何已声明图片的尾巴**，而这段时间仍然在可用范围内。
3. `end_frame()` 与 `number_of_images_in_sequence()` **不自洽**：`end_frame = start + 帧数(按 rate) - 1`，
   完全不含 `frame_step`。`step > 1` 时 `end_frame` 恒大于最后一张图片的文件号（差 `(m mod k)+(k-1)`，
   `m = int(可用帧数)`）；`step = 1` 时二者相等，与 `start_frame` 无关。
   `duration < step` 时出现 `n = 0` 而 `end_frame > start`。
4. `missing_frame_policy` 在核心库中**只被读写序列化，从未被执行**。它不检查磁盘、不替换画面、不决定错误。
   "能生成媒体地址"、"已声明显示时间"、"文件实际存在且可解码"是三个独立命题，库只负责前两者中的字符串/时间运算。
5. 旧时间线保持兼容的条件很窄：JSON 里 `ImageSequenceReference.1` 的**全部 8 个字段（含
   `missing_frame_policy`）必须存在**，否则反序列化直接失败（缺失键 → `KEY_NOT_FOUND`；缺策略字段 →
   `JSON_PARSE_ERROR: Unknown missing_frame_policy:`）。额外未知键被容忍。

---

## 1. 源码事实：三套坐标的定义与唯一实现

### 1.1 定义与公式

| 概念 | 定义位置 | 公式 / 语义 |
|---|---|---|
| 文件帧号 `F` | `src/opentimelineio/imageSequenceReference.cpp:131` | `F(i) = start_frame + i * frame_step`；可负；`i` 是图片序号 |
| 文件时长 | `imageSequenceReference.cpp:34-38` | `frame_duration = RationalTime(frame_step, rate)` |
| 图片数量 `n` | `imageSequenceReference.cpp:56-67` | `n = int(duration.to_frames(rate / frame_step))` |
| `end_frame` | `imageSequenceReference.cpp:41-53` | `start_frame + int(duration.to_frames(rate)) - 1`（无 `/step`） |
| 图片 `i` 的显示起点 | `imageSequenceReference.cpp:168-184` | `pt(i) = start_time + i·frame_duration`，再换算到序列 `rate`（`TimeTransform(first_frame_time, i, -1)` 以 `frame_duration.rate == _rate` 为目标速率） |
| 时间 → 文件帧号 | `imageSequenceReference.cpp:70-94` | `F = start_frame + int((t - start).to_frames(rate))`（无 `/step`） |
| 图片序号 → 媒体地址 | `imageSequenceReference.cpp:97-165` | `base + ("/"?) + prefix + ("-"?) + zero_pad + \|F\| + suffix` |

底层两点决定了上面所有取整行为：

- `RationalTime::to_frames(double rate)` 是 `int(value_rescaled_to(rate))`，即 **C++ `double → int` 向零截断**
  （`src/opentime/rationalTime.h:229-236`）。无四舍五入、无容差。
- `TimeRange::contains(t)` 是**半开区间** `start ≤ t < end_time_exclusive()`
  （`src/opentime/timeRange.h:175-178`）。

### 1.2 关键源码事实（逐条）

**S1 [源码] 图片数量按"播放帧率"截断。**
`playback_rate = rate / frame_step`，`n = int(duration.value_rescaled_to(playback_rate))`。
当 `available_range` 与序列同帧率时等价于 `n = trunc(D / step)`（D 为可用帧数）。

**S2 [源码] `end_frame()` 与 `frame_step` 无关。**
代码只做 `num_frames = duration.to_frames(_rate)`，注释写着 "Subtract 1 for inclusive frame ranges"
（`imageSequenceReference.cpp:48-52`）。因此它表达的是"若步长为 1，文件帧号空间的上界"，
而不是"最后一张已声明图片的文件号"。

**S3 [源码] `frame_for_time()` 不感知步长。**
它返回 `start_frame + 帧偏移`，帧偏移按 `rate` 换算，**从不除以 `frame_step`**。
所以返回值的量纲是"以 1 为步长的文件帧号"，对步进序列的大部分时刻，它指向**两个已声明文件号之间的空洞**。

**S4 [源码] `frame_for_time()` 出错时返回 `0`，与合法文件帧号 `0` 无法区分。**
只有 `error_status` 能区分（`imageSequenceReference.cpp:74-82`）。

**S5 [源码] 边界检查是不对称的：只查上界，不查下界。**
`target_url_for_image_number` 与 `presentation_time_for_image_number` 只检查
`image_number >= number_of_images_in_sequence()`（`:123`、`:172`），**没有任何 `image_number < 0` 检查**。
不过两者对负索引的实际接受度不同：

- `target_url_for_image_number` 在索引检查**之前**还有两道守卫（`rate == 0`、无范围/零时长，
  `:101-122`），负索引要先通过它们才可能被当作合法索引拼名。
- `presentation_time_for_image_number` 只有上界检查，负索引一律进入函数体，
  结果可能是"看似合理的时间"或 `bad_optional_access`（见 S6）。

具体矩阵见 §4.1。

**S6 [源码] `presentation_time_for_image_number` 对"无 `available_range`"没有保护。**
它先做 `>= n` 的检查，然后直接 `available_range().value()`（`:181`）。当
`available_range == std::nullopt` 且 `image_number < 0` 时，`std::optional::value()` 抛出
`std::bad_optional_access`（C++ 异常，不是 `ErrorStatus`）。Python 绑定下 pybind11 的默认
`std::exception` 翻译会把它变成 `RuntimeError`（`pybind11/detail/internals.h` 的
`translate_exception`；该映射不在本仓库源码内，属绑定层推断）。

**S7 [源码] 序列化字段全部是"必需"（`read` 而非 `read_if_present`）。**
`read_from` 使用 `reader.read(...)` 读取 `target_url_base`、`name_prefix`、`name_suffix`、
`start_frame`、`frame_step`、`rate`、`frame_zero_padding`，再读 `missing_frame_policy`
（`imageSequenceReference.cpp:194-234`）。`Reader::read` 在键缺失时报 `KEY_NOT_FOUND`
（`_fetch` 实现对未找到的键统一 `_error(ErrorStatus(KEY_NOT_FOUND, key))`，
`src/opentimelineio/deserialization.cpp:381-418`）。

**S8 [源码] 策略值的未知/缺失一律视为 JSON 解析错误。**
`missing_frame_policy` 只接受 `"error" | "hold" | "black"`，其他（包括空串、`null`）产生
`JSON_PARSE_ERROR: "Unknown missing_frame_policy: <value>"`（`:214-234`）。
注意源码对空串的处理是**报错而不是回落到默认值 `error`**。

**S9 [源码] 负文件号的名字构造。**
`abs(F)` 转十进制、按 `frame_zero_padding` 左侧补零、再在**前导补一个 `-`**
（`:131-159`）。因此 `-1` 在 pad=4 下是 `-0001`（总宽 5），与 `0001` 宽度不同。
这与文档示例一致（`docs/tutorials/otio-serialized-schema.md:479-484`）。

**S10 [源码] 整数宽度在反序列化时静默截断。**
`read` 先取 `int64_t`，再 `static_cast<int>`（`:190-205`），没有范围检查。

**S11 [源码] 打包器把图片序号当成文件帧号二次步进。**
`src/opentimelineio/bundle.cpp:212-214`：
```cpp
for (int frame = 0; frame < seq->number_of_images_in_sequence(); frame += seq->frame_step())
    file = file_from_url(seq->target_url_for_image_number(frame));
```
循环变量是**图片序号**，却按 `frame_step` 递增，于是只打包约 `n/step` 张图片。

**S12 [源码] 打包器只按"地址能否解析"判断，不按"文件是否存在"。**
`file_from_url`（`bundle.cpp:592-647`）只做 URL→路径的字符串解码；`register_bundle_file`
（`bundle.cpp:104-134`）只登记路径，不做 `exists()`。存在性直到 `dry_run` 的
`std::filesystem::file_size`（`:679`）才可能抛 `FILE_OPEN_FAILED`。

**S13 [源码] `error_if_not_file` 对序列的判断只反映循环最后一次迭代。**
`file` 在循环里被反复覆盖（`bundle.cpp:216`），循环后策略检查读取的是最后一次赋值的
`file.has_value()`（`:238-260`）。它验证的是"最后一个 URL 能否解析成路径"，不是"任一文件存在"。
[源码+复算] 若 `n <= 0`（零时长、负时长、负步长、`duration < step`），循环体一次也不执行，
`file` 保持空值，于是 `error_if_not_file` 会把一个**合法的空序列**判成 "is not a file"
（`FILE_WRITE_FAILED`），而 `missing_if_not_file` 会把它替换成 `MissingReference`。
这不是"文件缺失"的证据，只是循环没有迭代。

**S14 [源码] `original_target_url` 对序列保存的是路径而非 URL，且固定取图片 0。**
`bundle.cpp:235`：`original_target_url = file_from_url(seq->target_url_for_image_number(0));`
既丢了 `file://` 前缀，也丢了序列的其余信息；当 `n <= 0` 时该调用返回空串
（`ILLEGAL_INDEX` 被忽略、未被检查）。

**S15 [源码] 文档/绑定注释的措辞与实际语义存在偏差。**
- 绑定把 `end_frame` 描述为 "Last frame number in the sequence"
  （`src/py-opentimelineio/opentimelineio-bindings/otio_serializableObjects.cpp:1615-1617`），
  但见 S2。
- `missing_frame_policy` 的枚举注释是 "Behavior that should be used by **applications** when an image
  file in the sequence can't be found on disk"，`hold`/`black` 的注释都以
  "Application should ..." 开头（同文件 `:1518-1532`）；属性注释是 "Directive for how frames in
  sequence not found during playback or rendering should be handled"（`:1610-1613`）。这明确把执行
  责任推给应用，而不是库。

---

## 2. 非零源起点、负文件帧号、非单位步长同时存在

### 2.1 可用时长 ↔ 图片数量 ↔ 最后一张图片的显示区间

设：

- `S` = `available_range.start_time`（秒为 `s0`），`D` = 可用帧数（按序列 `rate` 计），`rate = r`，`step = k`。
- `n = trunc(D / k)`（同帧率时；异帧率见 2.3）。
- 最后一张图片序号 `n-1`，文件帧号 `F_last = start + (n-1)·k`。
- **最后一张图片的显示区间**：`[s0 + (n-1)·k/r, s0 + n·k/r)`，长度 `k/r`（= `frame_duration`）。
- `available_range` 的排他终点是 `s0 + D/r`。
- **未覆盖尾巴**：`[s0 + n·k/r, s0 + D/r)`，长度 `(D - n·k)/r`，**没有任何已声明图片**。
- `end_frame = start + D - 1`（与 `k` 无关）。

**结论（源码事实）**：只要 `D mod k ≠ 0`，可用范围的尾部就既"可用"又"无图"。而只要 `k > 1`，
`end_frame` 与 `F_last` 就**总是不相等**。在 `available_range` 与序列同帧率时，令 `m = int(D)`，
差值恒为 `(m mod k) + (k-1)`：`end_frame = start + m - 1`，`F_last = start + floor(m/k)·k`。
`k = 1` 时二者相等，与 `start_frame`、`D` 的取值无关
（[实测] 120 组 `step=1` 配置，0 例外）。`D` 为小数时（下表第 5 行）两个量各自按自己的取整路径截断，
上式的 `m = int(D)` 仍然成立（`(10,2,24,47.5)` 的差值为 `(1)+1 = 2`，实测 `56-54 = 2`）。
下面 [实测] 数据全部来自把仓库源码编成库后的探针输出。

| 配置 `(start, step, rate, avail 起点+帧数)` | `n` | `end_frame` | 最后已声明文件 `F_last` | 最后图片显示区间 | 尾巴帧数 `D-nk` |
|---|---|---|---|---|---|
| `(1, 2, 24, 0+48)` | 24 | 48 | 47 | `[46/24, 48/24)` | 0 |
| `(101, 3, 24, 12+50)` | 16 | 150 | 146 | `[57/24, 60/24)` | 2 |
| `(-2, 3, 24, 12+48)` | 16 | 45 | 43 | `[57/24, 60/24)` | 0 |
| `(-1, 2, 24, 12+48)` | 24 | 46 | 45 | `[58/24, 60/24)` | 0 |
| `(10, 2, 24, 0+47.5)` | 23 | 56 | 54 | `[44/24, 46/24)` | 1.5 |
| `(0, 1, 24, 0+24)` | 24 | 23 | 23 | `[23/24, 24/24)` | 0 |

注意第 2 行：`end_frame = 150`，但 `F_last = 146`，且 `147..150` 全部落在可用范围之内
（`frame_for_time(58)=147`、`(59)=148`、`(60)=149`、`(61)=150`）。`147/148` 落在最后一张图片的显示
区间里（"相邻文件帧号的间隔"），`149/150` 落在尾巴里（"跨过尾部"）。

### 2.2 `frame_for_time` 的返回值在步进序列中的三种含义

对可用范围内的时刻 `t`，令 `F = frame_for_time(t)`、`i = (F - start) / k`（整数向下取整）：

| 情形 | 判据 | `F` 的含义 | 是否代表同一段素材 |
|---|---|---|---|
| `t ∈ [pt(i), pt(i+1))` 且 `F = start + i·k` | `(F-start) mod k == 0` | 图片 `i` **唯一合法的文件地址**；只在 `t ∈ [pt(i), pt(i)+1/rate)` 这一小段内成立（长度 1 个 `rate` 帧，而图片显示区间长 `k` 个 `rate` 帧） | 是，且是唯一"已声明"的地址 |
| `t ∈ [pt(i), pt(i+1))` 且 `F ≠ start + i·k` | `(F-start) mod k ≠ 0` | 一个**不存在的文件号**；仅当按 `floor((F-start)/k)` 回折成图片序号才有意义 | 仅作为"所在显示区间"代表同一张图；作为文件名不代表任何素材 |
| `t` 在尾巴内 | `i ≥ n` | 一个既非已声明、也非任何图片的号码 | 否 |

[实测] 按每个输出帧采样 `frame_for_time`（`rate=24`），结果如下。这是"剪辑时间"与"文件帧号"之间
最容易出错的地方：**步长 > 1 时，绝大多数输出帧得到的 `F` 都不是任何已声明的文件号**。

| 配置 | `n` | 合法文件号 | 空洞 | 尾巴 | 合法比例 |
|---|---|---|---|---|---|
| `(101, 3, 24, 12+50)` | 16 | 16 | 32 | 2 | 32% |
| `(1, 2, 24, 0+48)` | 24 | 24 | 24 | 0 | 50% |
| `(-1, 2, 24, 12+48)` | 24 | 24 | 24 | 0 | 50% |
| `(0, 1, 24, 0+24)` | 24 | 24 | 0 | 0 | 100% |

[实测] `(101, 3, 24, 12+50)` 的部分采样：

```
t=12.000 F=101  (F-101)%3=0  -> 已声明 p.0101
t=13.000 F=102  (F-101)%3=1  -> 空洞，无此文件
t=14.000 F=103  (F-101)%3=2  -> 空洞，无此文件
t=14.999 F=103  -> 空洞
t=15.000 F=104  (F-101)%3=0  -> 已声明 p.0104
t=56.900 F=145  -> 空洞
t=57.000 F=146  -> 已声明 p.0146（最后一张）
t=58.000 F=147  -> 空洞（仍在最后一张的显示区间内）
t=59.999 F=148  -> 空洞（仍在最后一张的显示区间内）
t=60.000 F=149  -> 尾巴，i=16=n，无任何图片
t=61.999 F=150  -> 尾巴，等于 end_frame
t=62.000 error INVALID_TIME_RANGE
```

**恒等式 [实测]**：对全部采样配置（9 种帧率 × 5 种步长 × 4 种起点，共 936 次检查），
`frame_for_time(presentation_time_for_image_number(i)) == start + i·k`，
且区间内 25%/50%/75% 处的 `frame_for_time` 落在 `[start+i·k, start+(i+1)·k)`。**零反例**。
这就是"第一张/下一张图片的合法地址"与"显示时间"之间的闭环。

### 2.3 浮点帧率会把"整除"变成"少一张"

S1 的 `int()` 截断在 `rate = 24000/1001`、`30000/1001` 等不可精确表示的值上会向下丢一张。

[实测]：

| `rate` | `step` | `D` | `D/k` 的浮点原始值 | `n` | 理想 `D/k` | 丢失 |
|---|---|---|---|---|---|---|
| 24000/1001 | 2 | 100 | `49.999999999999993` | **49** | 50 | 最后一张不可寻址 |
| 30000/1001 | 3 | 999 | `332.99999999999994` | **332** | 333 | 同上 |
| 30000/1001 | 7 | 7 | `0.9999999999999999` | **0** | 1 | 整段"有 1 帧却没有任何图片" |
| 30000/1001 | 7 | 49 | `6.999999999999999` | **6** | 7 | 少一张 |

在 `rate=24000/1001, step=2, D=100` 下：`n=49`（图片序号 `0..48`），最后已声明文件是 `start+96`，
最后一张图片的显示区间是 `[96/r, 98/r)`，可用终点是 `100/r`，因此留下 `[98/r, 100/r)` 共 2 帧尾巴；
"本应是第 50 张"的图片 `i=49` 返回 `ILLEGAL_INDEX`，而 `frame_for_time` 在 `t ∈ [98/r, 100/r)` 仍会
正常返回文件号（落在尾巴里）。

> 影响面：这不是"精度误差"，是**可用范围与图片集合的边界不一致**，属于可复现的行为，且随
> `D`/`k` 的不同组合随机出现（910 次整除采样中 41 次、350 次非整除采样中 6 次不符）。

### 2.4 负源起点与负文件帧号

[源码] 负 `start_frame` 完全合法且不会触发任何特殊分支；文件号 `F < 0` 时输出 `-` + 补零数字
（S9）。`available_range.start_time` 为负也合法（`frame_for_time(-10)` 对
`start=-1, step=2` 返回 `-1`）。

[实测] `(-2, 3, 24, 12+48)` 声明的文件号序列为：
`-0002, 0001, 0004, 0007, …, 0043`（共 16 个）。跨越零点、跳过 `0` 与负数奇数，这些都是"空洞"，
不是缺帧错误——空洞是**步进本身**的结果，不是渲染缺失。

**需要区分两类"空洞"**：

- **步进空洞**：`k > 1` 时相邻文件号之间不存在的号码。由 schema 定义，属于设计内。
- **尾部空洞**：`available_range` 尾部不能用 `k` 整除的部分。由数据或 S1/S3 的取整规则产生，
  属于"可用范围声称有内容但没有任何图片"。

[实测] 在 `start=1, step=2, 24fps, 12+48`（`n=24`）下，`target_url_for_image_number(-1)` 返回
`file:///.../p.-0001.exr`、状态 `OK`；`presentation_time_for_image_number(-1)` 返回 `10@24`、状态 `OK`。
即**负图片序号在有效序列上是一个未声明、但会静默成功的反向越界**（S5）。
但这不是无条件成立：同一份代码在 `n == 0` 时负索引会被零时长守卫挡住，见 §4.1。
这一点使"负索引"既不能当作可依赖的扩展能力，也不能当作会被拒绝的非法输入。

### 2.5 剪辑裁切跨过尾部 / 落在空洞里

[源码] `Clip` 不做任何夹取：`Clip::available_range()` 直接返回媒体引用的 `available_range`
（`src/opentimelineio/clip.cpp:161-189`），`Item::trimmed_range()` 直接返回 `source_range`
（`src/opentimelineio/item.h:95-98`）。唯一的夹取发生在 `Composition::trim_child_range`，
且那是相对**父合成自身**的 `source_range`，不是相对媒体
（`src/opentimelineio/composition.cpp:456-488`）。

因此[实测]：

- 媒体 `12+50`（`n=16`，最后显示到 `60/24`），Clip `source_range = 40+40`：
  `clip.duration() = 40`、`clip.available_range() = 12+50`，**递归期间不报告截断**。
- `frame_for_time(59.9) = 148`（空洞），`frame_for_time(60) = 149`（尾巴），
  `frame_for_time(62..79) = 0` 且 `INVALID_TIME_RANGE`。
- 即：**剪辑在时间上仍然占 40 帧，但后半段没有任何"已声明的图片"**，其中
  `[60/24, 62/24)` 是"可用但无图"，`[62/24, 80/24)` 是"超出媒体可用范围"。
  这两段的区别只由 `frame_for_time` 的错误状态表达，不由剪辑对象表达。

**哪些寻址结果仍代表同一段素材**（回答本节的判断问题）：

1. **同一张图**：`presentation_time(i)`、`target_url_for_image_number(i)`（`0 ≤ i < n`）、以及
   `frame_for_time(t)` 在 `t ∈ [pt(i), pt(i+1))` 的全部结果——它们指向同一个"图片 `i`"的**显示区间**。
2. **同一段素材（可寻址）**：只有 `target_url_for_image_number(i)` 对 `0 ≤ i < n` 的输出。
   这是唯一一类"既代表这张图，又是已声明的地址"的结果。
3. **同一段素材（不可寻址）**：`frame_for_time` 在区间内部返回的非整步文件号。它们只表示
   "落在图片 `i` 的显示区间"，不能当作文件名使用。
4. **不代表任何素材**：尾巴内的 `frame_for_time`（`i ≥ n`）、`t ≥ available_range` 终点（返回 0 +
   `INVALID_TIME_RANGE`）、以及所有负图片序号的结果。

---

## 3. 缺帧策略与素材引用的责任边界

### 3.1 源码事实

**[源码] `missing_frame_policy` 在核心库中没有任何执行点。**
全仓库对它的引用只有三类：

- 枚举定义与存取器：`imageSequenceReference.h:24-29, 126-136`；
- 反序列化/序列化：`imageSequenceReference.cpp:207-234, 256-269`；
- Python 绑定与文档字符串：`otio_serializableObjects.cpp:1518-1532, 1610-1613`。

搜遍 `src/` 与 `tests/`，没有任何渲染、播放、文件探测代码读取该字段做分支。
`hold`/`black`/`error` 的语义仅存在于注释（S15）。

**[源码] 素材引用本身也不做存在性判断。**
`MediaReference` / `ImageSequenceReference` 的方法全部是纯字符串/时间运算；`is_missing_reference()`
只有 `MissingReference` 返回 `true`（`mediaReference.cpp:22-25`、`missingReference.cpp:20-23`）。
"缺帧"在 OTIO 的模型里不是一种可检测状态，只是应用的一种**预期行为声明**。

### 3.2 三个独立命题

| 命题 | 由谁产生 | 能证明什么 | 不能证明什么 |
|---|---|---|---|
| 可生成的媒体地址 | `target_url_for_image_number(i)`，`0 ≤ i < n` | 按 schema 规则拼出的字符串；路径分隔符、补零、负号规则正确 | 文件存在、可读、可解码、内容正确 |
| 已声明的显示时间 | `presentation_time_for_image_number(i)`，`available_range` | 该图片在"引用自身时间轴"上应出现的半开区间 | 该时间在父时间线上如何放置、是否被裁切 |
| 实际存在且可解码的图像 | **不在 OTIO 内** | — | — |

[实测] 一个 `n = 16` 的引用，可以连续成功生成 16 个 `OK` 状态的 URL 和 16 个 `OK` 状态的显示时间，
**全程不接触文件系统**；同一份引用在文件一个都不存在时行为完全不变。

[源码] 反证：打包器把"路径能解析"当作"可打包"（S12），把存在性推迟到 `file_size`；测试辅助函数
`tests/test_bundle.cpp:92-125` 也是先拼名再 `create_file`（`std::ofstream` 空文件），
所以**打包测试证明的是名字的搬运，不是图像的正确性**。

### 3.3 旧时间线保持兼容的条件

**[源码 + 实测] 能成功加载的最低条件**：

1. `OTIO_SCHEMA` 为 `ImageSequenceReference.1`（`.0` 也接受；`.2` 及以上 → `SCHEMA_VERSION_UNSUPPORTED`；
   无版本号 → `MALFORMED_SCHEMA`）。
2. 8 个字段全部存在且类型正确：`target_url_base`、`name_prefix`、`name_suffix`、`start_frame`
   （整数）、`frame_step`（整数）、`rate`（数字）、`frame_zero_padding`（整数）、
   `missing_frame_policy`（`"error"|"hold"|"black"` 之一）。
3. `available_range` 可以缺省（`MediaReference::read_from` 用 `read_if_present`，
   `mediaReference.cpp:29-37`），但缺省后 `n = 0`、`end_frame = start_frame`，且
   `presentation_time_for_image_number(<0)` 会抛 `bad_optional_access`。

**[实测] 逐项验证**：

| 输入 | 结果 |
|---|---|
| 正常 8 字段 | `ok=1` |
| 缺 `missing_frame_policy` | `ok=0`，`JSON_PARSE_ERROR: Unknown missing_frame_policy: ` |
| `missing_frame_policy: null` | 同上（被当作空串，不回落到默认值） |
| `missing_frame_policy: "BOGUS"` | `ok=0`，`JSON_PARSE_ERROR` |
| 缺 `name_prefix` | `ok=0`，`KEY_NOT_FOUND: name_prefix` |
| 多出未知字段 `future_field` | `ok=1`（未消费的键被保留在 `_dict`，不报错） |
| `"ImageSequenceReference.0"` | `ok=1`（`0 < 1`，无 upgrade 函数，直接按 v1 读取） |
| `"ImageSequenceReference.1.2"` | `ok=1`，但降级为 `UnknownSchema`（`split_schema_string` 取最后一个 `.` 之
后为版本，`stringUtils.cpp:48-69`；名字变成 `ImageSequenceReference.1`，未注册） |
| `"ImageSequenceReference.2"` | `ok=0`，`SCHEMA_VERSION_UNSUPPORTED` |

**[源码] 版本映射没有升级/降级函数。**
`typeRegistry.cpp` 只为 `Marker`、`Clip` 注册了 up/down-grade；`ImageSequenceReference` 没有。
`CORE_VERSION_MAP.cpp` 从 `0.14.0` 到 `0.19.0.dev1` 全部标注版本 1。因此**向更老的标签降级不会改变
该类型的表示**。

**[源码] 0.13 → 当前版本的算术语义未变。**
对比 PyPI 上的 `OpenTimelineIO-0.13.0` 与当前仓库的 `imageSequenceReference.cpp`，
`frame_duration`、`end_frame`、`number_of_images_in_sequence`、`frame_for_time`、
`presentation_time_for_image_number` 的**算术表达式完全相同**（同样的 `to_frames(rate)`、
同样的 `rate/frame_step`、同样的 `TimeTransform` 调用）。可见差异只有三类，均不改变数值：

1. 命名空间 `OPENTIMELINEIO_VERSION` → `OPENTIMELINEIO_VERSION_NS`；
2. 当前版本给 `error_status` 加了空指针判断（`if (error_status)`），0.13 直接解引用；
3. `noexcept`、参数 `const` 位置、代码格式。

当前版本另外新增了构造参数 `available_image_bounds`（`imageSequenceReference.cpp:19-20`），
这是新增字段而非语义变更。
**0.13 是引入该 schema 的第一个版本**（0.12.1 sdist 中不存在该文件），且从那时起就写
`missing_frame_policy` 字段。

**因此兼容结论**：旧时间线能继续读取，当且仅当它是 0.13 及以后写出的、包含完整 8 字段的
`ImageSequenceReference.1`。任何"修复"都不能改变 `frame_for_time`/`end_frame` 的数值语义，
否则旧文件里的数字会在新版本中改变含义（例如若把 `frame_for_time` 改成返回图片序号，
`step ≠ 1` 的旧时间线会整体错位）。修正只能以**新增 API**（例如 `image_number_for_time`）的形式加入。

---

## 4. 无可用范围 / 无有效帧时的错误语义

先给出各函数的返回值，再给错误码含义。

### 4.1 退化配置的返回值矩阵 [实测]

`target_url_for_image_number` 的守卫**有顺序**（`imageSequenceReference.cpp:101-130`）：
① `rate == 0` → ② 无范围或 `duration.value() == 0` → ③ `image_number >= n`。
只有通过 ①② 之后，负索引才会走到 `F = start + i·k` 的拼名逻辑。因此"负索引永远成功"是**错的**，
正确的是"**负索引没有下界检查，但在 ①② 命中时仍会被挡住**"。

`presentation_time_for_image_number` 只有一个检查：`image_number >= n`（`:172`）。
负索引一律通过，随后直接访问 `available_range().value()`（`:181`）。

| 配置 | `n` | `end_frame` | `target_url(0)` | `target_url(-1)` | `presentation_time(0)` | `presentation_time(-1)` | `frame_for_time(t)` |
|---|---|---|---|---|---|---|---|
| `available_range` 缺失 | 0 | `start_frame` | `ILLEGAL_INDEX` "Zero duration sequences has no frames." | `ILLEGAL_INDEX`（守卫 ②） | `ILLEGAL_INDEX` | **抛 `bad_optional_access`** | `INVALID_TIME_RANGE`，返回 0 |
| `duration == 0` | 0 | `start-1` | `ILLEGAL_INDEX`（同上消息） | `ILLEGAL_INDEX`（守卫 ②） | `ILLEGAL_INDEX` | 返回 `start + (-1)·k/r`，**OK** | 无时刻可查询（范围为空） |
| `duration < 0`（如 -48） | 负数（-48） | `start-49` | `ILLEGAL_INDEX`（守卫 ③） | `ILLEGAL_INDEX`（守卫 ③） | `ILLEGAL_INDEX` | `ILLEGAL_INDEX`（`-1 >= -48`） | 无时刻可查询 |
| `duration < 0` 且 `i ≤ -49` | 负数（-48） | `start-49` | `ILLEGAL_INDEX` | **返回 URL，OK**（i=-100 时 `-100 < -48`） | `ILLEGAL_INDEX` | **返回时间，OK** | 无时刻可查询 |
| `rate == 0` | 0 | `start-1` | `ILLEGAL_INDEX` "Zero rate sequence has no frames." | `ILLEGAL_INDEX`（守卫 ①） | `ILLEGAL_INDEX` | **返回 `start`，OK** | `frame_for_time` 仍返回数值（如 `20 → 1`），不报错 |
| `frame_step == 0` | **`INT_MIN`（-2147483648）** | `start + 帧数 - 1` | `ILLEGAL_INDEX`（守卫 ③，因 `0 >= INT_MIN`） | `ILLEGAL_INDEX`（同理） | `ILLEGAL_INDEX` | `ILLEGAL_INDEX` | `frame_for_time` 数值正常但语义无意义 |
| `frame_step < 0`（如 -2） | 负数（-24） | `start + 帧数 - 1` | `ILLEGAL_INDEX`（守卫 ③） | `ILLEGAL_INDEX`（`-1 >= -24`） | `ILLEGAL_INDEX` | `ILLEGAL_INDEX` | 同上；`i ≤ -25` 时 URL 又会"成功" |
| `duration` 不足一个 `step`（4 帧 / step 5） | 0 | `start+3` | `ILLEGAL_INDEX`（守卫 ③） | **返回 URL，OK**（`-1 < 0`） | `ILLEGAL_INDEX` | **返回时间，OK** | 有值区间存在，返回 `start..start+3` |
| 正常（`start=1, step=2, 24fps, 12+48`） | 24 | 48 | `p.0001`，OK | **返回 `p.-0001`，OK** | `12@24`，OK | **返回 `10@24`，OK** | 见 §2.2 |

**要点**：

- `end_frame` **不能**作为"是否存在帧"的判据：`n=0` 时它可能是 `start`（无范围）、
  `start-1`（零时长/零速率），也可能是 `start+D-1`（`D < step`）。
- `n` **不能**作为"正数即有效"的判据：零步长产生 `INT_MIN`，负步长/负时长产生负数。
- 负索引没有被显式拒绝，但能否"成功"取决于 `n` 是正是负、以及守卫 ①② 是否先命中。
  **这是不一致的定义，不是稳定契约**：同样传 `-1`，`n > 0` 时得到看似正常的 URL，
  `n == 0` 时被挡，`n < 0` 时又被接受。
- `presentation_time_for_image_number` 在无范围时抛 C++ 异常而非 `ErrorStatus`，与其余 API 风格不一致（S6）。

### 4.2 错误码的含义 [源码]

| `ErrorStatus::Outcome` | 产生点 | 中文含义 | Python 映射 |
|---|---|---|---|
| `ILLEGAL_INDEX` | `target_url_for_image_number`（零速率/零时长/索引越界）、`presentation_time_for_image_number`（索引越界） | "这次图片序号访问不成立"：或序列没有任何可寻址图片，或序号 ≥ `n`。**不区分**"序号非法"与"序列为空" | `IndexError`（`otio_errorStatusHandler.cpp:45-46`） |
| `ILLEGAL_INDEX` + details | 零速率 → `"Zero rate sequence has no frames."`；零时长/无范围 → `"Zero duration sequences has no frames."` | 消息文本；**无范围时也走"zero duration"文案**，是本条最易误导的地方 | 同上 |
| `INVALID_TIME_RANGE` | `frame_for_time` 在无范围或 `t ∉ [start, end_exclusive)` 时 | "这个时刻不在该引用的可用范围内"，返回值 `0` | 落到 `default:` → `ValueError`（`otio_errorStatusHandler.cpp:87-88`） |
| `JSON_PARSE_ERROR` | `read_from` 的策略值非法 | "存盘数据里的策略字段不是三个合法值之一"，整个对象读取失败 | `ValueError` |
| `KEY_NOT_FOUND` | 任一必需字段缺失 | "存盘数据缺少 schema 必填字段" | `KeyError` |
| `SCHEMA_VERSION_UNSUPPORTED` | 版本号大于 1 | "本版本读不懂更高版本的 schema" | `UnsupportedSchemaError` |
| `bad_optional_access`（非 `ErrorStatus`） | `presentation_time_for_image_number` 负索引 + 无范围 | "调用了不存在的 `available_range`"，属实现缺陷路径 | 绑定默认翻译 → `RuntimeError`（推断，见 S6） |

**必须强调的三个"错误含义"边界**：

1. `ILLEGAL_INDEX` **不代表**"该图片文件缺失"。它纯粹是编号是否落在 `[0, n)` 的算术判断。
2. `INVALID_TIME_RANGE` **不代表**"媒体损坏"或"帧缺失"。它只表示时刻不在 `available_range` 内。
3. 以上任何返回都**不代表**"磁盘上有没有这张图"。缺帧（文件缺失）在 OTIO 里没有错误码。

---

## 5. 已有测试支持 vs 未覆盖

### 5.1 已有测试（`tests/test_image_sequence_reference.py`）

| 测试 | 行号 | 锁定的行为 | 与本报告的关系 |
|---|---|---|---|
| `test_number_of_images_in_sequence` | 205-217 | `rate=24, D=48 → 48` | 支持 S1（整除、step=1） |
| `..._with_skip` | 219-234 | `step=2 → 24`，`step=3 → 16` | 支持 S1（整除、step>1） |
| `test_target_url_for_image_number` | 236-259 | 1..48 全序列命名 | 支持 S11 的名字规则 |
| `..._steps` | 261-307 | step=2/3、start=0 的跳号命名 | 支持 S9/S11 |
| `..._with_missing_slash` | 309-327 | base 无尾 `/` 时自动补 | 支持 `:149-156` |
| `test_abstract_target_url` | 329-367 | Python 辅助函数 `abstract_target_url` | 见 `schema/image_sequence_reference.py:73-86` |
| `test_presentation_time_for_image_number` | 369-393 | `12+2i` | 支持 `:181-183` |
| `..._with_offset` | 395-421 | 起点偏移时同样 `start+2i` | 支持 S3 的反面：显示时间与步长**有关** |
| `test_end_frame` | 423-442 | `start=1, D=48 → 48`，并显式断言 **"Frame step should not affect this"** | **直接锁定 S2**（`end_frame` 不含步长） |
| `test_end_frame_with_offset` | 444-463 | `start=101 → 148`，同样断言步长无关 | 锁定 S2；同时说明 147 这类"最后一张"并不在断言范围内 |
| `test_frame_for_time` | 465-499 | `frame_for_time` 返回**文件帧号**；并显式断言 `frame_step` 与查询速率都不影响结果 | **直接锁定 S3**（步长无关的连续文件号） |
| `test_frame_for_time_out_of_range` | 501-516 | 越界抛 `ValueError` | 支持 `INVALID_TIME_RANGE` → `ValueError` |
| `test_frame_range_for_time_range` | 518-537 | `(13, 29)` | 锁定 Python 辅助函数返回**文件帧号对**；该测试只覆盖 step=1 |
| `..._out_of_available_image_bounds` | 539-559 | 越界抛 `ValueError` | 同 `frame_for_time` 的传播 |
| `test_negative_frame_numbers` | 561-622 | `start=-1, step=2`：`n=24`、`pt(23)=58@24`、`p.-0001`、`p.0001`、…；step=1 时 `url(i)=i-1` | 支持 S9 与负起点；**未覆盖负 `start` 与尾部组合** |
| `test_target_url_for_image_number_with_missing_timing_info` | 624-672 | 无范围/零时长 → `IndexError("Zero duration sequences has no frames.")`；`rate=0` → `IndexError("Zero rate sequence has no frames.")` | 覆盖 4.1 的**正索引**分支 |
| `test_deserialize_invalid_enum_value` | 171-203 | `"BOGUS"` → `ValueError` | 支持 S8 |
| `test_serialize_roundtrip` | 125-169 | 写出/读回等价 | 部分支持 3.3（仅自身写出的数据） |
| `test_clone` / `test_create` / `test_str` / `test_repr` / 空白 base | 14-123, 674-702 | 构造、克隆、字符串化、空 base | 支持字段默认值与命名规则 |

**关键含义 [测试]**：`test_end_frame` 与 `test_frame_for_time` 是**两条显式断言**，分别把
`end_frame` 的"步长无关"和 `frame_for_time` 的"返回文件帧号、步长无关"钉死为契约。
因此 §2 中列举的所有"不一致"都不是实现偶然，而是被测试固化的定义——修正必须新增 API，不能改这两个函数。

### 5.2 与寻址相关的其它测试

| 测试 | 位置 | 覆盖 | 缺口 |
|---|---|---|---|
| `test_otioz_round_trip` | `tests/test_bundle.cpp:316-383` | 序列（`start=0, step=1, 24 帧`）被打包并解出 24 个**空文件** | 只覆盖 `step=1`；只验证名字存在 |
| `test_otiod_round_trip` | `tests/test_bundle.cpp:385-443` | 出包后 `target_url_for_image_number(0)` 是绝对路径且存在 | 同上；且 `file_from_url` + 图片 0 |
| `test_otioz_zip64` | `tests/test_bundle.cpp:701-...` | 6.5 万+ 帧序列的 ZIP64 分支 | `step=1` |
| `create_refs`（测试辅助） | `test_bundle.cpp:92-125` | **用文件帧号循环并当作图片序号传入**（`frame <= seq->end_frame()`，`frame += step`） | 只在 `step=1 ∧ start=0` 时全覆盖；`start` 越大漏得越多 |

[源码+复算] `create_refs` 用 `start_frame` 初始化循环变量、以 `end_frame()` 为上界、按 `frame_step`
递增，但把循环变量直接传给 `target_url_for_image_number(frame)`（参数是**图片序号**，上界是 `n`）。
正确性完全取决于 `start_frame` 恰好接近 0：`start` 越远离 0，通过的参数越少。实测结果：

| 配置（`D=48`, 24fps） | `n` | 辅助函数迭代次数 | 实际命中 `i < n` | 覆盖率 |
|---|---|---|---|---|
| `start=0, step=1` | 48 | 48 | 48 | 100% |
| `start=3, step=1` | 48 | 48 | 45 | 94% |
| `start=0, step=2` | 24 | 24 | 12 | 50% |
| `start=1, step=2` | 24 | 24 | 12 | 50% |
| `start=5, step=2` | 24 | 24 | 10 | 42% |
| `start=10, step=3` | 16 | 16 | 2 | 12.5% |
| `start=101, step=3` | 16 | 16 | **0** | 0% |

即 `start=101, step=3` 时"测试以为自己建了 16 张图，实际建了 0 张"。
`bundle.cpp` 的打包循环是另一个错误（从 `0` 开始、按 `step` 递增图片序号），只覆盖 `n/step`，
与 `start` 无关；两者叠加时覆盖的是两个错误集合的交集。

### 5.3 明确的测试盲区

以下行为**没有任何测试覆盖**（本报告全部经 [实测] 确认）：

1. 非整除时尾部与 `end_frame`/最后一张图的关系（§2.1 第 2 行、`fractional-dur`）。
2. `frame_for_time` 在显示区间内部返回"空洞文件号"（§2.2），以及 `(F-start) mod step ≠ 0` 的回折规则。
3. 负图片序号：`target_url(-1)`、`presentation_time(-1)` 在有效序列上静默成功，在 `n == 0` /
   `n < 0` 时结果又不同（S5、§4.1）。
4. 无 `available_range` 时 `presentation_time(-1)` 抛 `bad_optional_access` → Python `RuntimeError`（S6）。
5. `frame_step == 0`（`n = INT_MIN`）、`frame_step < 0`、`duration < 0`。
6. `duration < step` 时 `n = 0` 但 `end_frame > start` 的矛盾。
7. 浮点帧率（24000/1001、30000/1001）导致的少一张（§2.3）。
8. `start_frame` 超出 `int` 范围时的静默截断与 `abs(INT_MIN)` 的 `--` 双负号（S10）。
9. 异帧率 `available_range` 与序列 `rate` 混合（`12+60@24` 配 `rate=30`）时的 `n`/`end_frame`/显示时间速率。
10. 打包器 `step > 1` 的覆盖率（S11）与 `error_if_not_file` 的判据（S13）。

---

## 6. 待取得的媒体证据

以下问题**只能**由文件系统、解码器、渲染器或另一套实现对同一批文件的行为来回答。OTIO 的源码与测试
都不足以证明，需另行取证：

| # | 待证问题 | 为什么 OTIO 给不出 | 建议取证方式 |
|---|---|---|---|
| E1 | 对某个 `ImageSequenceReference`，`0 ≤ i < n` 中的哪些文件**真的在磁盘上** | `target_url_for_image_number` 只做字符串拼接；`file_from_url` 只做 URL 解码（S12） | 对每个 `i` 做 `stat`/`open`，把存在性比特与 `n` 对齐 |
| E2 | 已声明地址对应的文件**能否解码**、内容是否为该帧 | 库不打开文件 | 用 OpenImageIO/FFmpeg 等解码，记录成功/失败与首帧时间码 |
| E3 | 步进空洞（`F = start+i·k+1 …`）在磁盘上是否真的不存在 | 取决于产出方（渲染器）是否只渲染了 `k` 的倍数 | 列出目录内容，与 `{start+i·k}` 集合比对 |
| E4 | 尾部空洞内的渲染行为是否符合 `missing_frame_policy` | 库从不读取该字段（§3.1） | 在应用/渲染器中观察 `hold`/`black`/`error` 三种设置下的输出帧 |
| E5 | 负文件号命名（`-0001`）是否被目标解码器/文件系统接受 | 库只拼字符串 | 实际创建 `p.-0001.exr` 等并解码；检查跨平台文件系统限制 |
| E6 | 旧时间线（0.13/0.14 写出）在当前版本下**数值**是否不变 | 只能对比源码；没有跨版本行为测试 | 用 0.13/0.14 写一份含 `step>1`、负 `start` 的时间线，用当前版本读回，逐 `i` 对比 `n`/URL/`pt` |
| E7 | `end_frame` 为界的消费方（按文件帧号遍历）请求了哪些不存在的文件 | 见 S2、S11 | 在真实消费方中插桩，统计 `[F_last+1, end_frame]` 内的请求数与失败率 |
| E8 | 打包产物（otioz/otiod）中 `media/` 是否覆盖了全部已声明图片 | `bundle.cpp` 未能在本环境编译（minizip-ng 子模块为空） | 构建完整工程后，对 `step>1` 的序列做 `dry_run` 与解包，对比条目数与 `n` |
| E9 | 显示时间在半开区间边界（`pt(i+1) - ε`）上，各渲染器的采样是否落入图片 `i` | 库只定义时间，不定义采样约定 | 帧率为 24/29.97 的序列在边界处渲染对拍 |
| E10 | `missing_frame_policy` 的语义在业界实现中是否一致（`hold` 是"前一张"还是"最后一张可用"） | 注释只有一句话 | 对照 Nuke/Flame/RV 等的实际行为 |

---

## 7. 复现方法

本报告的 [实测] 数据由以下方式产生（未修改仓库）：

1. 从仓库源码编译核心库（排除 `bundle.cpp`）：
   ```sh
   SRC=<repo>/src
   clang++ -std=c++17 -O0 -fPIC -I$SRC -I/usr/local/include -I<rapidjson>/include -c <每个 .cpp>
   ```
2. 链接探针程序，仅需 `-L/usr/local/lib -lImath`。
3. 关键探针覆盖：`n`/`end_frame`/URL/`presentation_time`/`frame_for_time` 的联合采样；
   `frame_for_time(presentation_time(i))` 恒等式（936 次检查，0 反例）；浮点帧率扫描
   （910 + 350 次）；退化配置矩阵；反序列化兼容矩阵；`bundle.cpp` 与
   `tests/test_bundle.cpp::create_refs` 循环算术的等价复现。

仓库测试套件未在本环境运行（无内置构建产物；`src/deps/*` 子模块为空）。第 5 节的 [测试]
结论来自阅读测试代码，不是执行结果。

---

## 8. 给实现者的建议（不改变既有语义）

1. **不要修改** `frame_for_time` / `end_frame` 的返回值：它们被 `test_frame_for_time`、
   `test_end_frame` 显式锁定，改动会让旧时间线的数字改变含义（§3.3）。
2. 新增显式 API：`image_number_for_time(t)`——对可用范围内的 `t` 返回
   `floor((t - start)·rate / step)` 并夹到 `[0, n)`，即 §2.2 中"所在显示区间"的反演；
   再提供 `file_frame_number_for_image_number(i)`（返回 `start + i·k`，与
   `target_url_for_image_number` 同源），让调用方不必再自己把手算的 `F` 当作图片序号回传。
3. 修正 `bundle.cpp:212-214` 的循环变量（图片序号不应按 `frame_step` 递增），并修正
   `tests/test_bundle.cpp:111-115` 里把文件帧号当图片序号传入的同类循环
   （`frame` 为上界 `end_frame()` 的文件帧号，但 `:115` 传给 `target_url_for_image_number`）。
4. 为 `target_url_for_image_number` / `presentation_time_for_image_number` 增加 `image_number < 0`
   的 `ILLEGAL_INDEX`；为 `presentation_time_for_image_number` 增加 `available_range` 缺失保护，
   使其返回 `ErrorStatus` 而不是抛 `bad_optional_access`。
5. 若需修正 S1 的浮点截断，应作为**新字段/新 API 的语义**引入，并对 0.13+ 旧数据保留旧路径；
   替换 `int(...)` 为带容差的 `floor(x + ε)` 会改变历史文件的 `n`，属于不兼容变更。
6. 文档层面：把 `end_frame` 描述为"按 `rate` 计算的未步进上界"（不是"序列里最后一张图"），
   并明确 `missing_frame_policy` 是**面向应用的声明**，不是库的行为。
7. 把 §6 的 E1–E3 变成测试辅助：先 `stat` 每个 `0 ≤ i < n` 的地址，再断言"已声明集合"与
   "实际存在集合"的差集，才能让 `create_refs` 这类辅助函数的错误立刻暴露。
