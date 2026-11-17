# Roll / Slide / Slip 编辑与素材把手（Handles）消耗分析

基于 OpenTimelineIO 当前代码库（分支 `task/36`）的实际源码阅读。文末第 6 节区分了
**源码事实**、**对时间坐标的推断** 与 **需要剪辑样例才能确认的部分**。

---

## 0. 代码位置与适用范围

三类编辑操作只存在于 C++ 核心层，**没有暴露到 Python 绑定**：

| 操作 | 声明 | 实现 | 测试 |
|---|---|---|---|
| `algo::slip` | `src/opentimelineio/algo/editAlgorithm.h:123` | `src/opentimelineio/algo/editAlgorithm.cpp:582-611` | `tests/test_editAlgorithm.cpp:1624-1673` |
| `algo::slide` | `editAlgorithm.h:137` | `editAlgorithm.cpp:613-659` | `tests/test_editAlgorithm.cpp:1675-1719` |
| `algo::roll` | `editAlgorithm.h:176` | `editAlgorithm.cpp:710-803` | `tests/test_editAlgorithm.cpp:1907-1961` |
| 参照：`algo::trim` | `editAlgorithm.h:97` | `editAlgorithm.cpp:397-480` | `tests/test_editAlgorithm.cpp:1721-1849` |
| 参照：`algo::ripple` | `editAlgorithm.h:154` | `editAlgorithm.cpp:661-708` | `tests/test_editAlgorithm.cpp:1851-1905` |

`src/py-opentimelineio/opentimelineio/algorithms/` 只有 `track_algo.py`、`stack_algo.py`、
`timeline_algo.py`、`filter.py`；绑定层 `otio_*.cpp` 中没有任何对 `editAlgorithm.h` 的引用。
Python 侧与"把手"相关的只有 `track_algo.py` 的 `track_trimmed_to_range()` 与
`track_with_expanded_transitions()`（见第 4 节）。

## 1. 数据模型：可用范围、源起点与转场把手

### 1.1 三个时间范围

- **`source_range`**（`Item` 成员）：片段当前使用的源媒体窗口。
- **`trimmed_range()`**（`src/opentimelineio/item.h:95-98`）：`source_range` 已设置时返回它，
  否则回退到 `available_range()`。
- **`available_range()`**：
  - `Item` 基类（`item.cpp:50-58`）返回**零时长空范围**，若传入 `error_status` 则置
    `NOT_IMPLEMENTED`；
  - `Clip`（`clip.cpp:160-189`）返回其活动 `media_reference()->available_range()`；
    无媒体引用或引用未设范围时返回空范围并可置
    `CANNOT_COMPUTE_AVAILABLE_RANGE`；
  - `Gap` 不重写它，因此 Gap 的可用范围同样是空范围。

**关键兼容判据（源码事实）**：编辑算法调用 `available_range()` 时不传 `error_status`
（用默认 `nullptr`），错误被吞掉；随后用 `isEqual(available_range.duration().value(), 0.0)`
判断"没有可用范围信息"。也就是说 **空可用范围 = 无媒体边界 = 不做任何钳制**，而不是错误。
`Gap`、无媒体引用的 `Clip` 都走这条"无约束"路径。

### 1.2 源起点（source start）

`source_range.start_time()` 是片段内容在源媒体中的起点。注意测试用例
（`test_editAlgorithm.cpp:1625-1630`）中媒体可用范围起点为 **-15 帧**——源起点可以
是负值或非零时码，因此"钳制到 0"与"钳制到 available_range.start_time()"是两种不同的
约束，代码里两者都出现（见第 3 节）。

### 1.3 转场把手

- `Transition` 的时长为 `in_offset + out_offset`（`transition.cpp:52-56`），
  且 `Transition::overlapping()` 为真：在 `Track::range_of_child_at_index`
  （`track.cpp:71-91`）中，转场不增加轨道时长，其父级起点还要回退 `in_offset`。
  即转场覆盖在切点两侧：消耗前一片段**出点之后** `out_offset` 的尾部把手、
  后一片段**入点之前** `in_offset` 的头部把手。
- `Track::handles_of_child`（`track.cpp:150-165`）正式返回这对手把：
  前邻转场的 `in_offset` 为 head handle，后邻转场的 `out_offset` 为 tail handle。
- `Item::visible_range()`（`item.cpp:60-85`）= `trimmed_range` 向两端各扩展
  head/tail 把手——这是"转场期间片段实际需要提供媒体"的范围。
- Python 侧 `track_with_expanded_transitions()` / `_expand_transition()`
  （`track_algo.py:140-209`）用同一模型展开转场：前片段的 `source_range` 被改写为
  `[end - in_offset, end + out_offset)`，后片段被改写为
  `[start - in_offset, start + out_offset)`，直接消耗两侧片段的媒体把手。

## 2. 三类操作的语义与把手消耗

### 2.1 Slip（`editAlgorithm.cpp:582-611`）——消耗自身把手

```
|   A   |
 <----->        源窗口在媒体内滑动，时长不变
```

- 只改 `item` 的 `source_range.start_time += delta`，**时长不变**，不触碰邻居。
- 钳制（仅当可用范围非空）：
  - `start_time < available_range.start_time()` → 钳到可用起点；
  - `start_time + duration > available_range.end_time_exclusive()` → 回拉，
    使出点与可用末点对齐。
- 测试证实（`test_editAlgorithm.cpp:1646-1672`）：slip +20 帧被钳为 +12，
  slip -30 帧被钳为 -15（媒体范围 [-15, 48)，片段窗口 36 帧）。
- **同时保持所选片段时长与轨道总时长**——这是三者中唯一完全"无涟漪"的操作。

### 2.2 Slide（`editAlgorithm.cpp:613-659`）——消耗前一片段的把手

```
| A | B | C |  ->  | A     | B | C |
    *--->            （A 的出点伸缩，B 及下游整体平移）
```

- **不改 `item` 自己的 `source_range`**；通过修改**前一片段**的时长
  （`previous.duration += offset`）把 `item` 在轨道上平移。由于 Track 子项顺序
  紧密排布，`item` 之后的所有片段随之平移，**轨道总时长改变 offset**。
- 限制条件：
  - `item` 是第一个子项或 `delta == 0` → 直接返回（静默无操作，`editAlgorithm.cpp:625-628`）；
  - `delta < 0`：要求前一片段当前时长 `> |delta|`（`range.duration() <= -delta` 时
    直接返回，静默无操作）——消耗的是前一片段**已修剪出来的时长**，与媒体把手无关；
  - `delta > 0`：若前一片段可用范围非空，钳制
    `offset = available.duration - trimmed.duration`——消耗前一片段的**尾部媒体把手**。
- 测试证实（`test_editAlgorithm.cpp:1688-1718`）：右滑 +48 被钳到 +24
  （媒体 48 帧 - 已用 24 帧）；左滑 -24 等于前片段时长，判定非法，**轨道保持不变**。
- 注意：这与 NLE 经典 slide（同时消耗前后两个邻居的把手、轨道总长不变）**不同**——
  OTIO 的实现只动前邻居，后邻居被整体推走。**保持所选片段时长，但不保持轨道时长**。

### 2.3 Roll（`editAlgorithm.cpp:710-803`）——两侧不对称

```
|   A   |   B   |  ->  | A |  B      |
     <--*               （注释声称：前项起点不变、后项终点不变）
```

`delta_in`（动入点一侧，`editAlgorithm.cpp:737-768`）：

- `item.start_time += in_offset`，同时 `previous.duration += in_offset`：
  前一片段与选中片段此消彼长，**轨道总时长不变**。
- 钳制链：
  1. `in_offset` 先钳到使 `item` 新起点 ≥ 0（`-in_offset > start_time` →
     `in_offset = -start_time`）；
  2. 再钳到前一片段的当前时长（`previous.duration < -in_offset` 时缩减
     `in_offset`，保留前一片段至少 1 帧，见第 5 节的疑点）；
  3. 若 `item` 可用范围非空，最终起点钳到 `available_range.start_time()`。
- **没有**对照前一片段的 `available_range` 检查其延伸量——前一片段可以被
  roll 伸出自己的媒体把手之外。

`delta_out`（动出点一侧，`editAlgorithm.cpp:769-799`）：

- `item.end += out_offset`；`next.start_time += out_offset` 而 **`next` 时长不变**
  ——等于对下一片段做了一次 slip，并把下一片段（及下游）在轨道上整体推移
  `out_offset`，**轨道总时长改变**。
- 钳制：`next` 的新源起点不能小于 0；若 **`item` 自己**的可用范围非空，则改用
  `next` 的 `available_range.start_time()` 做下界（注意判断条件用的是 item 的
  可用范围、钳制值用的是 next 的，两者错位）。
- **没有**对 `item` 自身出点延伸做可用范围检查（对比 `ripple` 在
  `editAlgorithm.cpp:692-700` 有 `available_range` 钳制，`roll` 没有）。
- 测试证实不对称性（`test_editAlgorithm.cpp:1935-1947`，roll `delta_out=+10`）：
  轨道范围由 `[0,20][20,50)[50,70)` 变为 `[0,20][20,60)[60,80)`——
  **总时长 70 → 80**，下游被推移。这与头文件注释
  （`editAlgorithm.h:161-162`"End time in parent of Item after input item will
  never change"）**直接矛盾**：注释描述的是经典 roll（总长不变），实现与测试
  却是"出点侧 ripple"。

### 2.4 操作语义对照表（保持轨道时长 vs 保持所选片段时长）

| 操作 | 所选片段时长 | 轨道总时长 | 把手消耗对象 |
|---|---|---|---|
| `slip` | **保持** | **保持** | 自身两侧把手（钳制） |
| `slide` | **保持** | 改变 ±delta（下游平移） | 前邻居尾部把手（右）/ 前邻居已修剪时长（左） |
| `roll`（delta_in） | 改变 | **保持**（与前邻居互补） | 自身头部把手（钳到可用起点）；前邻居尾部**无钳制** |
| `roll`（delta_out） | 改变 | 改变（下游平移，非经典 roll） | 下一邻居头部源起点（钳到下界）；自身尾部**无钳制** |
| 参照 `trim` | 改变 | **保持**（缩短处补 Gap；伸向 Gap 时见 5.3） | 无可用范围检查 |
| 参照 `ripple` | 改变 | 改变（下游平移） | 自身尾部把手（钳制），头部钳到 ≥0 |

"保持轨道时长"在 OTIO 源码里有两种实现路径：**互补调整邻居**（roll 的 delta_in、
trim 的 delta_in）或**空洞填补**（trim 缩短时插入/扩大 Gap，
`editAlgorithm.cpp:448-473`）。"保持所选片段时长"则靠**只动邻居**（slide）或
**只动源起点**（slip）实现。

## 3. 超出素材边界时的行为与错误表达

### 3.1 三种越界结果

1. **静默钳制（结果仍是合法时间线，但位移量被缩减）**
   - `slip`：双向钳到 `available_range`（最严格）；
   - `slide` 右移：钳到前邻居可用时长；
   - `roll`：自身入点钳到 ≥0 及可用起点；下一邻居源起点钳到 ≥0 或其可用起点。
2. **静默无操作（原时间线完整保留）**
   - `slide`：首个子项、`delta == 0`、左移量 ≥ 前邻居时长——直接 `return`，
     轨道不变（测试 `test_editAlgorithm.cpp:1712-1718` 明确断言"No change"）；
   - `trim`：`delta_out > 0` 且下一项不是 Gap 时，出点侧不生效
     （测试注释 "no change due to clip"，`test_editAlgorithm.cpp:1759-1802`）。
3. **无检查越界（产生 source_range 超出 available_range 的时间线）**
   - `roll`：前邻居的延伸、自身出点的延伸都不对照可用范围；
   - `trim`：完全没有可用范围检查，`previous.duration += delta_in` 甚至可为负；
   - 无可用范围（空 duration）时所有钳制一律跳过——**这是源码规定的兼容判据**：
     `available_range().duration() == 0` ⟺ "媒体边界未知，一切放行"。

### 3.2 错误通道

- `slip` / `slide` **不接收 `error_status`**（`editAlgorithm.h:123,137`）：
  越界不可能以错误形式表达，只能体现为钳制或无操作。
- `roll` / `trim` / `ripple` 接收 `error_status`，但只报告结构性错误：
  `NOT_A_CHILD_OF`（item 无父级）、`NOT_AN_ITEM`（item 不在子列表中）。
  **没有任何"媒体把手耗尽"的错误码被使用**；`CANNOT_COMPUTE_AVAILABLE_RANGE`
  只出现在 `Clip::available_range` 自身，编辑算法把它吞掉。
- 转场相关的错误表达在别的操作里：
  - `slice`（`editAlgorithm.cpp:506-548`）：切点落在转场上时，
    `remove_transitions=true` 则删除转场，否则返回 `CANNOT_TRIM_TRANSITION`；
  - Python `track_trimmed_to_range`（`track_algo.py:46-49`）：修剪范围切到转场
    中间时抛 `CannotTrimTransitionsError`。
- **兼容判据（源码支持）**：一次编辑结果是否"媒体合法"，只能由调用方在事后检查
  每个被修改片段是否满足
  `available_range.start_time() ≤ source_range.start_time()` 且
  `source_range.end_time_exclusive() ≤ available_range.end_time_exclusive()`
  （即 `trimmed_range ⊆ available_range`）。库本身只在 slip/slide/roll 的局部
  钳制里部分强制这一不变式，trim/roll 的若干路径会静默违反它。

### 3.3 转场邻居：三类操作的盲区

`slide`（`editAlgorithm.cpp:631`）与 `roll`（`editAlgorithm.cpp:745,774`）用
`dynamic_retainer_cast<Item>(children[index ± 1])` 取邻居；`dynamic_retainer_cast`
在类型不符时返回**空 Retainer**（`serializableObject.h:735-740`），代码**没有判空**
就调用 `previous->trimmed_range()` / `next->trimmed_range()`。因此当相邻项是
`Transition` 时，roll/slide 既不消耗转场把手、也不报 `CANNOT_TRIM_TRANSITION`，
而是空指针解引用（未定义行为）。换言之：**这三类操作只在邻居是普通 Item
（Clip/Gap）时才是良定义的**；转场把手的消耗模型（第 1.3 节）完全没有进入
roll/slide/slip 的位移限制计算。这与 `slice`/`overwrite`/`insert` 显式查找并
删除/拒绝转场的做法形成鲜明对比。

## 4. 相邻素材可用范围对位移的限制汇总

| 限制来源 | slip | slide | roll |
|---|---|---|---|
| 自身 `available_range` 起点 | 钳制 | —（不改自身源范围） | delta_in 钳制 |
| 自身 `available_range` 末点 | 钳制 | — | **不钳制** |
| 前邻居 `available_range` | — | delta>0 钳制（按时长近似） | **不钳制**（延伸方向） |
| 前邻居当前时长 | — | delta<0 不足则无操作 | 钳制（保留 ≥1 帧，见 5.2 疑点） |
| 后邻居源起点/可用起点 | — | — | delta_out 钳制 |
| 源起点 ≥ 0 | —（用可用起点） | — | 钳制 |
| 转场把手（in/out_offset） | 不参与 | 不参与（空指针风险） | 不参与（空指针风险） |

## 5. 事实、推断与待确认

### 5.1 源码事实（可直接引用行号）

- slip/slide/roll 的实现、钳制逻辑、测试期望值：见第 0 节表格的行号。
- 空可用范围 = 无约束：`editAlgorithm.cpp:590,648,696,763,781` 的
  `isEqual(...duration().value(), 0.0)` 判断。
- roll 的 delta_out 改变轨道总时长、且下一片段是被 slip 而非被修剪：
  `editAlgorithm.cpp:794-797` 与测试 `test_editAlgorithm.cpp:1935-1961`。
- 头文件注释与实现矛盾：`editAlgorithm.h:156-176` vs `editAlgorithm.cpp:769-799`。
- 转场把手模型：`track.cpp:86-91,150-165`、`item.cpp:60-85`、
  `track_algo.py:140-209`。
- 邻居为转场时不判空：`editAlgorithm.cpp:631,745,774` +
  `serializableObject.h:735-740`。

### 5.2 对时间坐标的推断（读代码推得，未运行验证）

- **slide 右移钳制是近似的**：`editAlgorithm.cpp:649-651` 用
  `trimmed.duration + delta ≤ available.duration` 做判断，隐含假设
  `trimmed.start_time == available.start_time`。若前邻居的源起点已经大于可用
  起点（头部把手已消耗），真正剩余的尾部把手是
  `available.end - (start + duration)`，比该式允许的值小——此时 slide 可以把
  前邻居推出媒体末点。推断：在源起点对齐可用起点的常见情况下结果正确。
- **roll delta_in 对前邻居时长的钳制疑似符号错误**（`editAlgorithm.cpp:750-754`）：
  ```cpp
  if (duration < -in_offset) { duration -= 1帧; in_offset -= duration; }
  ```
  以 `in_offset = -10`、`previous.duration = 5` 代入：`duration` 变为 4，
  `in_offset` 变为 **-14**（更负），随后 `previous.duration + in_offset = -9`
  得到负时长。按语义应是把 `in_offset` 钳到 `-(duration-1) = -4`，即此处很可能
  应为 `in_offset += duration`。现有 roll 测试的前邻居都是 20 帧的 Gap 且
  |delta| = 10，**没有覆盖这条钳制路径**，无法从测试确认预期行为。
- **roll delta_out 的钳制条件错位**（`editAlgorithm.cpp:781-787`）：判断分支用的
  是 `item` 的可用范围是否为空，钳制值却取自 `next` 的可用起点。推断其意图是
  "若 next 有可用范围则钳到 next 的可用起点"，条件变量疑似写错；当 item 无可用
  范围而 next 有时，会落入 else 分支只钳到 0——对源起点为负或非零的媒体偏松/偏严。
- roll/slide 把 Gap 当作普通邻居：Gap 没有可用范围，向右 roll/slide 进 Gap 时
  延伸不受限——语义上合理（空洞可任意伸缩），但轨道时长会随之改变。

### 5.3 需要剪辑样例才能确认的部分

- **trim 与 Gap 相邻时的两个分支**（`editAlgorithm.cpp:444-473`）无测试覆盖：
  - `delta_out > 0` 且下一项是 Gap：item 伸入 Gap，但代码**不缩减 Gap 时长**，
    推断轨道总时长会凭空增加 delta_out；
  - `delta_out < 0` 且下一项是 Gap：`gap.duration += delta_out`（即 Gap 也缩短），
    与头文件注释 "existing Gap's duration will be augmented"（`editAlgorithm.h:90`）
    相反，推断为符号错误。两者都需要构造"Clip+Gap"样例实际运行才能定性。
- **邻居为 Transition 时 roll/slide 的实际后果**：静态阅读判定为空指针解引用，
  但具体表现（崩溃、断言、或在某些构建下"碰巧工作"）需要构造
  "Clip–Transition–Clip" 样例运行确认。
- **越界结果的下游表现**：roll/trim 造成 `source_range` 超出 `available_range`
  后，时间线仍可序列化（schema 不校验该不变式），但渲染/重定时/适配器导出
  （如 EDL、AAF）如何表达这种非法窗口，需要样例结合具体适配器确认。
- **slide 近似钳制的实际偏差量**：5.2 的推断需要用"源起点 ≠ 可用起点"的片段
  构造样例，验证右移是否会越过媒体末点以及越过量。

## 6. 结论

1. **只有 slip 完整实现了"消耗把手、越界钳制"的语义**；slide 只钳前邻居、
   roll 只钳部分方向，trim 完全不检查媒体边界。
2. **"保持轨道时长"与"保持所选片段时长"在源码中是两条独立路径**：slip 两者都
   保持；slide 保持片段时长但推移下游；roll 仅入点侧保持轨道时长，出点侧实为
   ripple（与自身注释矛盾）；trim 通过补 Gap 保持轨道时长。
3. **越界不会以错误形式表达**：要么静默钳制、要么静默无操作、要么静默产生
   越界的 `source_range`。源码提供的唯一兼容判据是
   `available_range().duration() == 0`（无媒体信息 → 不约束）加上调用方事后
   检查 `trimmed_range ⊆ available_range`。
4. **转场把手完全不参与这三类操作的限制计算**；邻居为转场时代码不判空，
   属于待确认的风险路径。需要严格的转场感知编辑时，应参考 `slice` 的
   `CANNOT_TRIM_TRANSITION` 错误通道或 Python 侧的
   `CannotTrimTransitionsError` 模式自行封装。
