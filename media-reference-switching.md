# 媒体版本切换下剪辑区间与标记的有效性分析

> 分析对象：OpenTimelineIO（本仓库，分支 `task/56`）
> 场景：同一剪辑（`Clip`）在代理素材与原素材等多个媒体版本（`MediaReference`）之间切换活动引用，而媒体版本之间的起始时间（`available_range.start_time`）或帧率（`RationalTime.rate` / `ImageSequenceReference.rate`）不同。
> 方法：仅基于仓库内 C++ 核心源码、Python 绑定、序列化/版本升级代码与现有测试得出结论；每条结论标注【源码事实】或【待验证】，并注明测试支持情况。

---

## 1. 结论速览

1. **切换活动素材引用本身只改"指针"，不改任何时间语义数据。** `Clip` 把多个媒体引用存在一个 map 中，用一个活动 key 选择当前引用；`source_range`、标记（`Marker`）、效果（含 `LinearTimeWarp`）、转场偏移（`Transition` 的 in/out offset）分别挂在 `Item` 与轨道上，切换时原样保留。【源码事实，见 §3.1】
2. **但"可用范围"和"图像边界"是每个媒体引用各自携带的属性**，切换后 `Clip.available_range()` 与 `Clip.available_image_bounds()` 立即改由新引用决定。因此旧的 `source_range`、转场把手、标记在新引用上是否仍指向有效媒体，核心库**不做任何静态校验**，只在具体查询时按路径报错或静默容忍。【源码事实，见 §4、§5】
3. **核心库不存在"两个媒体版本之间自动重映射时间"的机制。** 帧率换算由 `RationalTime` 的有理数缩放承担（按物理秒对齐）；起始时间原点不同的素材，切换后同一 `RationalTime` 会指向不同内容，OTIO 不补偿这个偏移。媒体重定时（变速播放）在数据模型里由 `LinearTimeWarp.time_scalar` 表达，但它**不参与核心时间计算**，仅作为下游播放器的声明数据。【源码事实，见 §3.3】
4. **非法切换是事务安全的**：key 不存在或为空串时写入被拒绝，活动 key 与原活动素材保持不变，C++ 经 `ErrorStatus` 返回错误，Python 抛 `ValueError`。【源码事实 + 双侧测试，见 §6】
5. **序列化往返后**，活动 key、全部媒体引用及其各自的 `available_range` / `available_image_bounds` / 帧率字段都持久化在 JSON 中，重新读入后可完整判定当前素材与有效范围；但反序列化路径**不执行** key 有效性校验，手写的悬空 key JSON 可被读入，要到查询时才暴露。【源码事实，见 §7】

---

## 2. 涉及的数据模型与代码入口

| 概念 | 类型 | 关键位置 |
|---|---|---|
| 多版本媒体容器与活动 key | `Clip` | `src/opentimelineio/clip.h:105-106`、`clip.cpp:30-133` |
| 可用范围 / 图像边界 | `MediaReference` | `src/opentimelineio/mediaReference.h:42-67,76-77` |
| 剪辑源范围、效果、标记 | `Item` | `src/opentimelineio/item.h:59-85,135-139`、`item.cpp:44-85` |
| 标记区间（所属 item 坐标系） | `Marker` | `src/opentimelineio/marker.h:14-17,72-74` |
| 转场把手 | `Transition` | `transition.h:58-70,99-101`、`transition.cpp:52-56` |
| 轨道上的把手计算 | `Track` | `track.cpp:52-92,150-165` |
| 序列帧自有帧率与帧映射 | `ImageSequenceReference` | `imageSequenceReference.h:53-66,144-157`、`imageSequenceReference.cpp:69-94` |
| 变速声明（不进核心时间数学） | `LinearTimeWarp` / `FreezeFrame` | `linearTimeWarp.h:30-42`、绑定文档 `otio_serializableObjects.cpp:1287-1293` |
| 有理数时间与跨帧率运算 | `RationalTime` / `TimeRange` | `rationalTime.h:232-234,286-339,381-385`、`timeRange.h:175-199` |
| 编辑算法对可用范围的钳制 | `algo::slip/slide/ripple/roll` | `algo/editAlgorithm.cpp:581-611,633-658,692-700` |
| 错误码与 Python 异常桥接 | `ErrorStatus` / handler | `errorStatus.h:18-49`、`otio_errorStatusHandler.cpp:41-89` |
| Clip.1→.2 / .2→.1 版本升降级 | `TypeRegistry` | `typeRegistry.cpp:159-177,220-238` |

---

## 3. 三层责任划分

题目要求区分三件事：**活动素材切换**、**剪辑时间变换**、**实际媒体重定时**。源码中三者的归属边界非常清晰。

### 3.1 活动素材切换：只负责"选哪个引用"

`Clip` 内部是一个 map 加一个 key（`clip.h:105-106`）：

```cpp
std::map<std::string, Retainer<MediaReference>> _media_references;
std::string                                     _active_media_reference_key;
```

- `media_reference()` 仅按活动 key 查表，查不到或值为空返回 `nullptr`（`clip.cpp:30-37`）。
- `set_active_media_reference_key()` 与 `set_media_references()` 在写入前调用
  `check_for_valid_media_reference_key()`（`clip.cpp:51-87`），校验：map 中不得含空串 key、活动 key 必须存在于 map 中。
- 校验失败时**直接 return，不修改任何成员**（`clip.cpp:95-102,124-131`），因此旧活动素材保持不变。
- 写入 map 时，空指针会被替换成占位 `MissingReference`（`clip.cpp:107,138-139`），所以正常构造路径下几乎不存在"活动引用为空"的状态（`clip.cpp:196-198` 的注释明确说明了这一点）。

【责任边界】这一层**只保证 key 引用关系合法**，完全不读取、不比较、不调整任何 `TimeRange` 或帧率。两个媒体版本的 `available_range` 是否兼容，不在它的职责内。

### 3.2 剪辑时间变换：属于 Item / Track，与活动素材解耦

- `source_range` 是 `Item` 的成员（`item.h:135`），其 setter 是无条件赋值，**不含任何与 `available_range` 的包含性校验**（`item.h:65-68`）。
- `trimmed_range()` = 有 `source_range` 用它，否则回退到 `available_range()`（`item.h:95-98`）；`duration()` 取 `trimmed_range().duration()`（`item.cpp:44-48`）。
- `transformed_time()` 在父子层级间换算时间时，使用的是 `trimmed_range()` 与父级 `range_of_child()`（`item.cpp:119-169`），整条链路不查询活动媒体引用。
- 转场的 `in_offset` / `out_offset` 是 `Transition` 自己的成员（`transition.h:99-101`），`duration = in_offset + out_offset`（`transition.cpp:52-56`）；轨道通过 `Track::handles_of_child()` 把相邻转场的偏移换算成 clip 的 head/tail 把手（`track.cpp:150-165`），`Item::visible_range()` 据此扩展 trimmed range（`item.cpp:60-85`）。这些计算只依赖轨道几何与 clip 时长，同样与活动素材无关。
- 标记的 `marked_range` 文档明确声明"位于所属 item 的时间坐标系中"（`marker.h:14-17`），随 `Item._markers` 持久化，切换引用时不被触碰。

【责任边界】切换素材不会移动时间线上的任何剪辑点、把手或标记；它们在 **clip 时间坐标系**内的数值始终有效。问题只可能出在"这些数值能否在新素材上解析出真实画面"。

### 3.3 实际媒体重定时：数据声明与核心计算分离

- `LinearTimeWarp` 只保存一个 `time_scalar`（`linearTimeWarp.h:36-42`），`FreezeFrame` 是其 `time_scalar=0` 的子类。全仓库核心 C++ 时间数学（`item.cpp`、`track.cpp`、`editAlgorithm.cpp`、`opentime`）**没有任何一处读取 `time_scalar`**；grep 可见其仅出现在构造、序列化与 Python 绑定中。
- Python 绑定的属性文档把这一约定写明（`otio_serializableObjects.cpp:1287-1293`）：

  > Note that adjusting the time_scalar of a LinearTimeWarp does not affect the duration of the item this effect is attached to. Instead it affects the speed of the media displayed within that item.

- 真正承担"帧率不同"这一事实的是 `opentime`：`RationalTime` 是 `(value, rate)` 二元组，加减运算按物理秒互相缩放（`rationalTime.h:286-339`），相等比较也先缩放再比值（`rationalTime.h:381-385`）；`TimeRange.contains()` 在秒域加 epsilon 比较（`timeRange.h:189-199`）。
- 媒体版本特有的重定时信息位于具体引用内，典型是 `ImageSequenceReference` 自带的 `rate`、`start_frame`、`frame_step`（`imageSequenceReference.h:53-66`），其 `frame_for_time()` 用引用自身的 rate 与 `available_range` 做帧号映射（`imageSequenceReference.cpp:69-94`）。

【责任边界】OTIO 核心负责"时间值的有理数换算"和"保存变速声明"，但**不负责在两个媒体版本之间建立内容对应关系**。代理与原素材若时间原点不同，需要库外逻辑（或在引用的 `available_range` 起点中编码偏移）解决。

---

## 4. 切换后各剪辑区间与标记的有效性判定

设原素材 A 为切换前活动引用，代理 B 为切换后活动引用，二者 `available_range` 起点或帧率不同。

| 数据 / 查询 | 切换后结构上是否保留 | 语义有效性条件 | 失效时的表现 |
|---|---|---|---|
| `Clip.source_range`（含起点、时长） | 保留，数值不变【源码事实：`Item._source_range` 不在切换路径上】 | B 的 `available_range` 在物理秒上包含该区间；且两版本时间原点一致 | 核心库不报错；文档明确允许 source_range 超出可用媒体（`docs/tutorials/time-ranges.md:46-50`）；下游取帧时才失败（见 `ImageSequenceReference` 行） |
| `Clip.trimmed_range()` / `duration()` | 保留；只要 `source_range` 已设置，结果与切换前逐值相同【源码事实：`item.h:95-98`、`item.cpp:44-48`】 | 同上 | 若 `source_range=None`，回退到 B 的 `available_range()`，**时长会随切换改变** |
| `Clip.available_range()` | 不保留旧值，改返回 B 的 `available_range`【源码事实：`clip.cpp:160-189`】 | B 必须设置 `available_range` | B 未设置 → `CANNOT_COMPUTE_AVAILABLE_RANGE`，详情 "No available_range set on media reference on clip"（`clip.cpp:176-186`）；Python 抛 `CannotComputeAvailableRangeError` |
| `Clip.available_image_bounds()` | 同上，改取 B 的边界【源码事实：`clip.cpp:191-225`】 | B 必须设置 `available_image_bounds` | 未设置 → `CANNOT_COMPUTE_BOUNDS`（`clip.cpp:211-222`）；Python 侧为 `ValueError` 族异常 |
| `Marker.marked_range` | 标记对象与区间数值原样保留【源码事实：`Item._markers`，坐标系声明见 `marker.h:14-17`】 | 标记所指的 clip 时间点在 B 上仍对应预期画面（取决于原点/帧率兼容性） | 核心库无标记级校验，**不会报错**；标记可能静默指向 B 的不同内容 |
| `Transition.in_offset/out_offset` 与 `visible_range()` 把手 | 数值与轨道几何不变【源码事实：`transition.cpp:52-56`、`track.cpp:150-165`、`item.cpp:60-85`】 | B 在 trimmed range 之外还要有足够余量覆盖把手所需媒体 | OTIO 不阻止把手超出媒体可用范围，文档明确声明此行为（`docs/tutorials/otio-timeline-structure.md:110-113`）；播放端行为未定义 |
| `LinearTimeWarp.time_scalar` / `FreezeFrame` | 保留【源码事实：`Item._effects` 仅序列化存储】 | 由下游播放器解释 | 对核心时长/区间零影响（绑定文档 `otio_serializableObjects.cpp:1291`） |
| `ImageSequenceReference.frame_for_time(t)` | 引用整体可切换，但帧映射按 B 自身 rate/起点重算【源码事实：`imageSequenceReference.cpp:84-93`】 | `t` 必须落在 B 的 `available_range` 内（`contains` 判定，`imageSequenceReference.cpp:74-76`） | 越界或无 available_range → `INVALID_TIME_RANGE`（`imageSequenceReference.cpp:77-81`）；Python 抛 `ValueError`，已有测试 `test_image_sequence_reference.py::test_frame_for_time_out_of_range` |
| `algo::slip/slide/ripple/roll` 的钳制行为 | 函数可用，但钳制基准换成 B 的 available_range【源码事实：`editAlgorithm.cpp:589,633,692-700`】 | B 的 available_range 已设置且覆盖期望滑动空间 | B 无 available_range 时 `Clip::available_range()` 返回默认空 `TimeRange()`，`isEqual(duration,0)` 分支使钳制失效（`editAlgorithm.cpp:590`），滑动不再受媒体边界约束 |
| `Track.available_image_bounds()` | 随各 clip 切换后的边界聚合【源码事实：`track.cpp:273-304`】 | 轨道内所有 clip 的活动引用都带边界 | 任一 clip 报错即整体返回空并带错误状态 |

### 4.1 帧率不同的特殊语义

- `RationalTime` 的跨 rate 比较以物理秒为准（`rationalTime.h:381-385`，`TimeRange::contains` 用 `to_seconds()` 加 epsilon，`timeRange.h:193-198`）。因此 24fps 与 48fps 两个版本只要**时间原点相同**，同一 `source_range` 在秒域上仍对齐，核心区间判定保持一致。
- 但帧级映射存在截断：`to_frames(rate)` 直接 `int(value_rescaled_to(rate))`（`rationalTime.h:232-234`），非整数比帧率（如 24→30）在 `frame_for_time` 等取整路径上会丢亚帧精度。【源码事实】
- `ImageSequenceReference` 另有独立 `rate` 字段，与其 `available_range` 内嵌的 rate 是两份数据；`frame_for_time` 用 `_rate` 而 `end_frame`/`number_of_images_in_sequence` 用 `available_range.duration().to_frames(...)`（`imageSequenceReference.cpp:48-66,86`），两者不一致时帧计数会分叉。【源码事实；现有测试只覆盖自洽数据，未覆盖二者不一致，见 §8】

### 4.2 起始时间不同的特殊语义

- `source_range.start_time` 是绝对值，不带"相对于某引用起点"的间接层。若 A 的时间码原点是 `01:00:00:00` 而 B 从 0 起，切换后同一源时间在 B 上指向完全不同的画面，核心库不提供偏移补偿。【源码事实：全仓库无媒体版本间时间映射组件】
- `frame_for_time` 内部先减去 B 的 `available_range.start_time` 再转帧（`imageSequenceReference.cpp:84-86`），说明引用只对"落在自己 available_range 内的绝对时间"自洽，超出即报错，不会借用 A 的原点。

---

## 5. 保持旧时间线可解释性的兼容条件

综合 §3、§4，仅切换引用而不重写剪辑数据时，需要同时满足：

1. **包含性条件**：每个候选媒体版本的 `available_range` 都必须在物理秒上包含 clip 的 `trimmed_range()`，以及转场把手扩展后的 `visible_range()` 所需区间。判定可直接用 `TimeRange::contains()`（秒域 epsilon 语义，`timeRange.h:189-199`）。
2. **同源点条件**：各版本表达同一画面时必须使用相同的绝对时间原点。若代理素材重置了时间码起点，必须在切换前由库外逻辑把偏移编码进代理引用的 `available_range`（或同步改写 `source_range` / 标记 / 转场偏移），OTIO 不会自动完成。
3. **帧率相容条件**：优先选用整数倍关系帧率（24/48、30/60 等），此时有理数换算在秒域精确；非整数比帧率需接受 `to_frames` 截断带来的帧级偏差，并避免依赖 `ImageSequenceReference.frame_for_time` 的亚帧正确性。
4. **source_range 显式化条件**：不要依赖 `source_range=None` 的回退语义——回退会让 `trimmed_range()` 随活动引用的 `available_range` 改变（`item.h:95-98`），切换即改变 clip 时长。要保持时间线几何不变，所有版本共存期间 clip 应显式持有 `source_range`。
5. **边界完备条件**：若下游会查询 `available_image_bounds()`（含 `Track` 聚合路径），每个引用都必须填写该字段，否则切换后触发 `CANNOT_COMPUTE_BOUNDS`。
6. **序列帧自洽条件**：`ImageSequenceReference` 的 `rate`、`start_frame`、`frame_step` 必须与其 `available_range` 自洽，否则 `frame_for_time` / `number_of_images_in_sequence` 的结果不可靠。
7. **标记与把手复核条件**：标记与转场偏移不会被核心库校验，切换流程应在应用层增加一次"标记点/把手区间是否被新 available_range 包含"的显式检查，否则失效是静默的。

---

## 6. 引用无效或缺少可用范围时的错误行为与一致性

### 6.1 切换路径（key 级错误）——原活动素材保持一致

| 触发方式 | C++ 行为 | Python 行为 | 原活动素材是否保留 |
|---|---|---|---|
| `set_active_media_reference_key("不存在")` | `ErrorStatus::MEDIA_REFERENCES_DO_NOT_CONTAIN_ACTIVE_KEY`，函数提前返回（`clip.cpp:73-85,124-131`） | `ValueError("The media references do not contain the active key")`（`otio_errorStatusHandler.cpp:82-84`） | 是。C++ 测试断言失败后 `media_reference()` 仍返回原引用（`tests/test_clip.cpp:204-210`）；Python 测试断言 key 仍为旧值（`tests/test_clip.py:248-256`） |
| `set_media_references(...)` 活动 key 不在新 map 中 | 同上错误码，**旧 map 整体保留**（`clip.cpp:95-102`） | `ValueError`（`test_clip.py:259-270`） | 是 |
| map 含空串 key | `MEDIA_REFERENCES_CONTAIN_EMPTY_KEY`（`clip.cpp:59-71`） | `ValueError("The media references contain an empty key")`（handler:85-86） | 是（`test_clip.py:273-284`、`test_clip.cpp:229-235`） |
| 传入 `nullptr` 引用 | 不报错，落库为 `MissingReference` 占位（`clip.cpp:107,138-139`） | 同 | 不适用；`test_clip.py::test_ref_default` 覆盖 |

【结论】所有可经公开 setter 触发的非法切换都是"全有或全无"：错误返回后活动 key、map 内容与切换前完全一致。

### 6.2 查询路径（范围/边界级错误）——与具体活动引用绑定，无"回退到旧素材"语义

- 活动引用存在但未设 `available_range`：`Clip::available_range()` 返回 `CANNOT_COMPUTE_AVAILABLE_RANGE` 与默认空 `TimeRange()`（`clip.cpp:176-188`），Python 抛 `CannotComputeAvailableRangeError`（handler:76-77；`test_clip.py:174-177` 覆盖同类边界错误路径）。
- 活动引用存在但未设图像边界：`CANNOT_COMPUTE_BOUNDS`（`clip.cpp:211-222`），C++ 测试 `test_clip.cpp:256-301` 覆盖（含 `error_status=nullptr` 时静默返回空 optional 的分支）。
- 活动引用在 map 中缺失（仅可能来自反序列化，见 §7.2）：`media_reference()` 返回 `nullptr`，随后报 "No media reference set on clip" 的 `CANNOT_COMPUTE_AVAILABLE_RANGE`（`clip.cpp:163-174`）。
- 序列帧时间越界：`INVALID_TIME_RANGE`，Python 侧落入 handler 的 default 分支抛 `ValueError`（`otio_errorStatusHandler.cpp:87-88`；测试 `test_frame_for_time_out_of_range`）。

【关键差异】setter 级错误保证原活动素材不变；但**切换成功之后**新引用自身的数据缺失不会触发任何回退——核心库不会"记住上一个好引用"，错误完全由当前活动引用的状态决定。

---

## 7. 序列化往返后的可判定性

### 7.1 持久化内容（可判定当前素材与有效范围）

- `Clip::write_to` 写出完整 `media_references` map 与 `active_media_reference_key`（`clip.cpp:152-158`）；基线文件 `tests/baselines/empty_clip.json:9-15` 与 `tests/test_serialization.cpp:60-78` 给出实际 JSON 形状。
- 每个引用各自的 `available_range`、`available_image_bounds` 由 `MediaReference` 基类读写（`mediaReference.h` 对应字段；`ImageSequenceReference` 另持久化 `rate/start_frame/frame_step/...`，`imageSequenceReference.cpp:239-270`）。
- 因此重新读入后，无需外部信息即可判定：当前活动素材是哪一个（key）、它的可用范围与图像边界是什么、其余备选版本及其范围是什么。
- 打包路径（otioz）同样保留多引用与活动 key：`bundle.cpp:287-289` 用原 key 回写，`tests/test_bundle.cpp:331-360` 覆盖往返一致性。
- 旧版 Clip.1（单一 `media_reference` 字段）读入时由升级函数包装到 `DEFAULT_MEDIA` key 下并设为活动（`typeRegistry.cpp:159-177`），测试 `test_clip.cpp:76-145` 覆盖（含 null → MissingReference）。反向降级 2→1 只保留活动引用、丢弃其余版本（`typeRegistry.cpp:220-238`）。

### 7.2 反序列化不做 key 校验（不对称点）

- `Clip::read_from` 直接读取 map 与 key，不调用 `check_for_valid_media_reference_key`（`clip.cpp:142-150`）。因此一份手写的、活动 key 不在 map 中的 JSON 可以成功读入；要等到调用 `media_reference()`/`available_range()` 时才以 §6.2 的方式暴露。
- 现有测试未覆盖该悬空 key 读入场景。【源码事实 + 测试缺口】

### 7.3 往返不改变时间语义数据

`source_range`、`markers[].marked_range`、`effects[]`、`enabled`、`color` 均由 `Item::write_to/read_from` 原样持久化（`item.cpp:182-202`），转场偏移由 `Transition` 自行持久化（`transition.cpp:32-50`）。JSON 往返不引入任何帧率归一化或起点平移——各 `RationalTime` 的 value/rate 按原值保存。【源码事实；`test_clip.py::test_cons`、`test_marker.py` 序列化用例、`test_transition.py::test_serialize` 覆盖往返等价性】

---

## 8. 源码事实与测试支持对照

| 结论 | 源码依据 | 已有测试支持 |
|---|---|---|
| 切换只改活动 key，不动时间数据 | `clip.cpp:30-37,119-133`；`item.h:135` | `test_clip.py::test_multi_ref`、`test_clip.cpp::test_clip_media_representation` |
| 非法 key/空 key 被拒且状态不变 | `clip.cpp:51-87`；handler `:82-86` | `test_clip.py:248-284`、`test_clip.cpp:202-235` |
| 空引用落为 MissingReference | `clip.cpp:107,135-140` | `test_clip.py::test_ref_default`、`test_clip.cpp::test_clip_v1_to_v2_null` |
| available_range/bounds 委托活动引用 | `clip.cpp:160-225` | `test_clip.py::test_ranges`、`test_available_image_bounds`；`test_clip.cpp:256-301` |
| source_range 无包含性校验、可超出媒体 | `item.h:65-68,95-98`；文档 `time-ranges.md:46-50` | 无直接测试（文档明示为有意设计） |
| 标记位于 item 坐标系且切换不触碰 | `marker.h:14-17`；`item.cpp:182-202` | `test_marker.py`（构造/升级/序列化）；**无切换后标记有效性测试** |
| 转场把手不查媒体可用性 | `track.cpp:150-165`；文档 `otio-timeline-structure.md:110-113` | `test_item.py::test_visible_range`、`test_transition.py`；**无跨媒体版本把手测试** |
| time_scalar 不影响核心时长 | 全仓库无核心引用；绑定文档 `:1287-1293` | `test_effect.py:87-105`（仅存取/序列化） |
| 跨帧率按物理秒换算、取整截断 | `rationalTime.h:232-234,286-339,381-385` | `test_opentime.py`（rescale/异速率加减，如 `:676-693`） |
| 序列帧越界报 INVALID_TIME_RANGE | `imageSequenceReference.cpp:69-94` | `test_image_sequence_reference.py::test_frame_for_time_out_of_range`、`..._out_of_available_image_bounds` |
| 编辑算法按活动引用 available_range 钳制 | `editAlgorithm.cpp:581-611,633-658` | `test_editAlgorithm.cpp:226-276`（slip/slide；**未切换引用对比**） |
| JSON 持久化活动 key 与全部引用 | `clip.cpp:142-158`；`typeRegistry.cpp:159-177` | `test_serialization.cpp:60-78`、`baselines/empty_clip.json`、`test_clip.cpp:76-145`、`test_bundle.cpp:331-360` |
| 反序列化不校验活动 key | `clip.cpp:142-150`（无校验调用） | **无测试** |

---

## 9. 待验证事项

以下结论由源码推断但仓库内无直接测试或运行环境佐证，建议在可构建环境中补测：

1. **【待验证】悬空活动 key 的读入行为**：手工构造 `active_media_reference_key` 不在 `media_references` 中的 `.otio` JSON，确认读入成功且首次 `available_range()` 调用报 `CANNOT_COMPUTE_AVAILABLE_RANGE`（源码路径见 §7.2，本环境未构建 OTIO，未实跑）。
2. **【待验证】异帧率切换后端到端区间判定**：构造 24fps 原素材与 48fps 代理（同原点）与 30fps 代理（非整数比）各一，验证 `TimeRange.contains` 在秒域的判定结果及 `frame_for_time` 在 24→30 下的截断偏差是否与 §4.1 推断一致。
3. **【待验证】异起点切换的静默错位**：构造 available_range 起点不同的两个引用，验证标记与 `source_range` 数值不变但 `frame_for_time` 解析出的帧号/URL 不同，且全程无核心异常。
4. **【待验证】`source_range=None` 切换的时长漂移**：验证 trimmed_range 回退路径下 clip duration 随活动引用改变，并连带 `Track::range_of_child` 重排后续 clip 位置。
5. **【待验证】`ImageSequenceReference.rate` 与其 `available_range` rate 不一致时** `end_frame`/`number_of_images_in_sequence`/`frame_for_time` 的分叉表现（§4.1）。
6. **【待验证】转场把手超出新引用 available_range 时**各适配器/播放器的实际表现——核心库只声明"不阻止、不定义"（文档 `otio-timeline-structure.md:110-113`），下游行为超出本仓库保证范围。
7. **【待验证】编辑算法在新引用无 available_range 时的钳制失效**：`slip/slide` 中空 TimeRange 分支（`editAlgorithm.cpp:590`）的实际效果仅有间接测试，未在"切换后缺失范围"场景下验证。

---

## 10. 关键代码位置索引

```
src/opentimelineio/clip.cpp
  30-37   media_reference() 活动 key 查表
  51-87   check_for_valid_media_reference_key() 唯一的 key 合法性校验
  89-111  set_media_references() 原子替换 map+key
 119-133  set_active_media_reference_key()
 135-140  set_media_reference() 空指针→MissingReference
 142-150  read_from() 不做 key 校验
 160-189  available_range() 委托活动引用
 191-225  available_image_bounds() 委托活动引用
src/opentimelineio/item.h
  65-68   set_source_range() 无校验赋值
  95-98   trimmed_range() source_range 优先、否则回退 available_range
src/opentimelineio/item.cpp
  60-85   visible_range() 转场把手扩展
 119-169  transformed_time() 层级时间换算（不查媒体引用）
src/opentimelineio/track.cpp
 150-165  handles_of_child() 转场偏移→clip 把手
src/opentimelineio/transition.cpp
  52-56   duration = in_offset + out_offset
src/opentimelineio/imageSequenceReference.cpp
  69-94   frame_for_time() 越界→INVALID_TIME_RANGE
src/opentimelineio/algo/editAlgorithm.cpp
 581-611  slip() 按 available_range 钳制
src/opentimelineio/typeRegistry.cpp
 159-177  Clip.1→.2 升级（DEFAULT_MEDIA 包装）
 220-238  Clip.2→.1 降级（仅保留活动引用）
src/py-opentimelineio/opentimelineio-bindings/otio_errorStatusHandler.cpp
 76-88    媒体 key/范围错误→Python 异常映射
src/py-opentimelineio/opentimelineio-bindings/otio_serializableObjects.cpp
 1287-1293 time_scalar 不影响 item 时长的明示约定
src/opentime/rationalTime.h
 232-234  to_frames() 整数截断
 286-339  异速率加减（物理秒缩放）
 381-385  相等比较先缩放
src/opentime/timeRange.h
 175-199  contains() 秒域 epsilon 比较
```
