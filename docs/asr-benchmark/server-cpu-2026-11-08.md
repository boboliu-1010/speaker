# 中文会议服务器 CPU 测试

2026-11-08 在 Intel Xeon Platinum 8488C 服务器上实测，系统可见 8 个逻辑 CPU，内存约 15 GiB。各模型设为 Torch 4 个计算线程、1 个调度线程，离线串行执行，每套配置测一轮。

公开测试共 11 段、780 秒。主集为 AISHELL-4 和 AliMeeting 各 5 段，每段 60 秒。补测取另一场 AliMeeting 的连续 180 秒。7 套转写流程和 5 种分区方案均完成这两组输入。MOSS 同时输出文字和分区。

600 秒主集上，Paraformer 组合最快，耗时 26.22 秒。MOSS 的联合字符错误率和分区错误率最低，分别为 8.96% 和 12.30%。仅比较独立分区时，Nemotron 3 的 DER 最低，为 13.56%，耗时 8.41 秒。

[本机基准与公开样本索引](README.md) · [完整指标词典](metrics.md)

## 公开主集完整转写

| 方案 | 完整覆盖 | cpCER ↓ | ASR 秒 | 完整流程秒 | 实时倍数 ↑ | 平均进程 CPU | 累计 CPU 秒 | ASR 采样峰值 RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3 ASR 0.6B + Nemotron 3 | 10/10 | 10.64% | 151.82 | 164.02 | 3.66 | 397.2% | 651.46 | 4.14 GiB |
| Qwen3 ASR 1.7B BF16 + Nemotron 3 | 10/10 | 11.20% | 267.81 | 280.01 | 2.14 | 399.2% | 1117.94 | 4.48 GiB |
| Fun-ASR-Nano HF + Nemotron 3 | 10/10 | 26.14% | 184.22 | 196.44 | 3.05 | 398.9% | 783.62 | 3.91 GiB |
| Paraformer-zh + CT-Punc + Nemotron 3 | 10/10 | 17.55% | 14.05 | 26.22 | 22.89 | 391.6% | 102.68 | 4.83 GiB |
| SenseVoiceSmall + CT-Punc + Nemotron 3 | 10/10 | 15.22% | 16.28 | 28.44 | 21.10 | 389.7% | 110.82 | 2.66 GiB |
| MOSS 0.9B | 10/10 | 8.96% | 470.07 | 476.85 | 1.26 | 399.8% | 1906.20 | 5.44 GiB |
| FireRedASR2-AED + CT-Punc + Nemotron 3 | 10/10 | 14.57% | 807.35 | 828.87 | 0.72 | 397.1% | 3291.10 | 5.13 GiB |

cpCER 为匿名说话人最优配对后的字符插入、删除、替换总数除以参考字符数。例如 MOSS 的 96 / 1071 对应 8.96%。评分仅用 5 段 AISHELL-4 中的 53 个完整参考区间、1071 个规范化参考字符。它同时反映文字和归属错误。AliMeeting 只评分区。覆盖为完成样本数 / 输入样本数。ASR 秒是识别阶段墙钟时间，单位为秒。完整流程时间为 ASR、适用的标点、对齐和分区阶段之和。共用的 Nemotron 3 每条只实际测一次，耗时与 CPU 成本计入使用它的每套方案。MOSS 原生输出分区，FireRed 单独计 CT-Punc，Paraformer 与 SenseVoice 的 ASR 列已经包含 CT-Punc。

实时倍数 = 音频秒 / 流程秒。平均进程 CPU = 累计 CPU 秒 / 流程秒 × 100%。单核满载为 100%，整机折算再除以 8。RSS 为服务器守护程序约每 2 秒采样的 ASR 进程峰值，覆盖该进程全部输入和加载，可能漏掉短暂峰值。加载与热身排除在推理耗时之外。未完整覆盖的组合不列合计成绩。

### 一分钟样本的 ASR 延迟范围

| 方案 | 最快秒 | 最慢秒 | 最慢样本 |
| --- | ---: | ---: | --- |
| Qwen3 ASR 0.6B + Nemotron 3 | 10.39 | 18.84 | `alimeeting_R8004_M8005_MS803` |
| Qwen3 ASR 1.7B BF16 + Nemotron 3 | 13.59 | 72.23 | `alimeeting_R8002_M8002_MS802` |
| Fun-ASR-Nano HF + Nemotron 3 | 8.00 | 46.25 | `alimeeting_R8004_M8005_MS803` |
| Paraformer-zh + CT-Punc + Nemotron 3 | 1.16 | 2.02 | `aishell4_L_R003S01C02` |
| SenseVoiceSmall + CT-Punc + Nemotron 3 | 1.51 | 1.68 | `alimeeting_R8002_M8002_MS802` |
| MOSS 0.9B | 24.93 | 74.91 | `alimeeting_R8005_M8007_MS806` |
| FireRedASR2-AED + CT-Punc + Nemotron 3 | 29.12 | 272.72 | `alimeeting_R8006_M8012_MS803` |

范围来自十个不同输入的一次测试，不能当作重复运行的 P95。MOSS 含原生分区，Paraformer 与 SenseVoice 含标点。

## 说话人分区

| 模型 | 主集覆盖 | 主集 DER ↓ | 主集墙钟秒 | 主集平均进程 CPU | 连续 3 分钟 DER ↓ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Nemotron 3 | 10/10 | 13.56% | 8.41 | 397.8% | 19.05% |
| Sortformer v1 | 10/10 | 27.30% | 7.57 | 370.1% | 25.19% |
| Sortformer v2.1 | 10/10 | 14.30% | 10.58 | 380.5% | 20.64% |
| DiariZen Large v2 | 10/10 | 13.83% | 345.54 | 399.8% | 19.21% |
| MOSS 0.9B（含 ASR） | 10/10 | 12.30% | 470.07 | 399.9% | 10.63% |

DER =（漏检 + 误报 + 说话人混淆的说话人秒）/ 参考说话人秒。计入重叠，零边界宽容（说话边界附近豁免 0 秒）。模型编号通过最优配对，不是识别真实身份。MOSS 的分区耗时含识别，其他四个是分区 API。部分 API 包含内部读音频。

### 两个公开语料的零边界宽容 DER

| 分区模型 | AISHELL-4（5 段） | AliMeeting（5 段） |
| --- | ---: | ---: |
| Nemotron 3 | 6.15% | 18.56% |
| Sortformer v1 | 8.09% | 40.28% |
| Sortformer v2.1 | 6.91% | 19.30% |
| DiariZen Large v2 | 10.07% | 16.37% |
| MOSS 0.9B（含 ASR） | 10.14% | 13.76% |

整体 DER 用参考说话人秒加权。举例，100 个参考说话人秒里有 3 秒漏检、2 秒误报和 5 秒混淆，DER 为 10%。

## 公开连续三分钟补测

| 方案 | 公开 180 秒覆盖 | 公开 180 秒流程耗时 | 平均进程 CPU | 实时倍数 |
| --- | ---: | ---: | ---: | ---: |
| Qwen3 ASR 0.6B + Nemotron 3 | 1/1 | 48.03 | 397.2% | 3.75 |
| Qwen3 ASR 1.7B BF16 + Nemotron 3 | 1/1 | 65.49 | 399.1% | 2.75 |
| Fun-ASR-Nano HF + Nemotron 3 | 1/1 | 69.18 | 399.1% | 2.60 |
| Paraformer-zh + CT-Punc + Nemotron 3 | 1/1 | 8.54 | 392.9% | 21.07 |
| SenseVoiceSmall + CT-Punc + Nemotron 3 | 1/1 | 9.49 | 392.7% | 18.96 |
| MOSS 0.9B | 1/1 | 251.45 | 399.6% | 0.72 |
| FireRedASR2-AED + CT-Punc + Nemotron 3 | 1/1 | 237.25 | 397.0% | 0.76 |

覆盖表示完成样本数 / 输入样本数。耗时单位为秒，CPU 和实时倍数采用主集同一口径。该片段来自 AliMeeting，质量评估使用上节的 DER。


## 同一公开主集的历史本机对照

| 流程 | 本机秒 | 服务器秒 | 服务器耗时 / 本机耗时 | 本机 cpCER | 服务器 cpCER |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3 ASR 0.6B + Nemotron 3 | 87.85 | 164.02 | 1.87 | 10.64 | 10.64 |
| Qwen3 ASR 1.7B BF16 + Nemotron 3 | 490.45 | 280.01 | 0.57 | 11.11 | 11.20 |
| Fun-ASR-Nano HF + Nemotron 3 | 100.67 | 196.44 | 1.95 | 26.14 | 26.14 |
| Paraformer-zh + CT-Punc + Nemotron 3 | 38.41 | 26.22 | 0.68 | 17.55 | 17.55 |
| SenseVoiceSmall + CT-Punc + Nemotron 3 | 36.43 | 28.44 | 0.78 | 15.41 | 15.22 |
| MOSS 0.9B | 251.83 | 476.85 | 1.89 | 8.96 | 8.96 |
| FireRedASR2-AED + CT-Punc + Nemotron 3 | 1127.97 | 828.87 | — | 17.09 | 14.57 |

本机列来自此前 M5 Pro 4 线程的同一批 600 秒公开录音。这是历史结果对照。FireRed 的 beam 配置不同，故不计算其速度比。它的 cpCER 差异也不能只归因于硬件。Linux 和 macOS 的运行时、算子及后台负载不同，耗时比表示这两套实际运行环境的差异。比例大于 1 表示服务器用时更长。

### 本机与服务器 CPU 占用

| 完整流程 | 本机平均进程 CPU | 服务器平均进程 CPU | 本机累计 CPU 秒 | 服务器累计 CPU 秒 |
| --- | ---: | ---: | ---: | ---: |
| Qwen3 ASR 0.6B + Nemotron 3 | 177.5% | 397.2% | 155.9 | 651.46 |
| MOSS 0.9B | 153.1% | 399.8% | 385.5 | 1906.20 |
| FireRedASR2-AED + CT-Punc + Nemotron 3 | 124.3% | 397.1% | 1402.4 | 3291.10 |

本机有同批逐阶段 CPU 实测的流程为上面三套，均采用 FP32。CPU 秒为各线程消耗的用户态与内核态 CPU 时间之和。平均进程 CPU 按整个流程加权计算。Qwen 在服务器的 397.2% 表示平均占用约 3.97 个逻辑核，按 8 核折算约 49.7%。本机用 15 核折算，177.5% 对应约 11.8%。折算值只计测试进程。跨机比较同时看墙钟时间和累计 CPU 秒。

[本机 CPU 测量方法与原始记录](cpu-method.md)

## 公开主集输出异常

| 方案  |  主集生成长度标记  |  主集长重复块  |  主集对齐失败 |
| ---  |  ---:  |  ---:  |  ---: |
| Qwen3 ASR 0.6B + Nemotron 3  |  0/20  |  0/20  |  0/20 |
| Qwen3 ASR 1.7B BF16 + Nemotron 3  |  1/20  |  0/20  |  0/20 |
| Fun-ASR-Nano HF + Nemotron 3  |  2/20  |  0/20  |  2/20 |
| Paraformer-zh + CT-Punc + Nemotron 3  |  0/20  |  0/20  |  0/20 |
| SenseVoiceSmall + CT-Punc + Nemotron 3  |  0/20  |  0/20  |  0/20 |
| MOSS 0.9B  |  0/10  |  0/180  |  0/179 |
| FireRedASR2-AED + CT-Punc + Nemotron 3  |  1/20  |  6/20  |  0/20 |

每格为触发次数 / 检查单位数。生成长度标记表示最终输出达到解码上限，以一次解码为单位。长重复块指去掉标点后同一字符连续出现至少 8 次的识别块，MOSS 按原生说话段计。对齐失败以非空文字块或原生说话段为单位，失败项仍保留文本和粗略时间。比如 FireRed 的 6/20 表示 20 个检查块中有 6 个触发重复检查。

## 模型加载开销

| 转写方案 | 模型加载秒 | 测量范围 |
| --- | ---: | --- |
| Qwen3 ASR 0.6B + Nemotron 3 | 4.22 | ASR 模型 |
| Qwen3 ASR 1.7B BF16 + Nemotron 3 | 0.24 | ASR 模型 |
| Fun-ASR-Nano HF + Nemotron 3 | 0.69 | ASR 模型 |
| Paraformer-zh + CT-Punc + Nemotron 3 | 7.29 | ASR 与标点模型 |
| SenseVoiceSmall + CT-Punc + Nemotron 3 | 4.79 | ASR 与标点模型 |
| MOSS 0.9B | 1.18 | MOSS 权重与处理器 |
| FireRedASR2-AED + CT-Punc + Nemotron 3 | 5.88 | ASR 模型 |

这是各 runner 单独记录的加载阶段时间，不是完整冷启动延迟。不同 runner 对处理器初始化的包络略有差别。上面的正式推理时间不包含这些值。

## 运行配置与重试

服务器 Qwen 1.7B 使用 BF16，其余转写流程使用 FP32。FireRed 的服务器配置为 beam=1，本机为 beam=3，分别保留 1 个和 3 个搜索候选。DiariZen 在 Python 3.11 与 Torch/torchaudio 2.1.1 CPU 环境运行。FireRed 首次加载触发 8 GiB 进程 RSS 上限，重试将该模型的进程上限调至 11 GiB，并保留整机可用内存低于 2 GiB 的停止条件。重试完成了识别、标点与对齐。GiB 为二进制内存单位，1 GiB 等于 1,073,741,824 字节。
