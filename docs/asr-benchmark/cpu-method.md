# CPU 测量与本轮运行配置

[返回总览](README.md#firered-追加测试和-cpu-占用) · [逐项数值释义](metrics.md)

## CPU 占用口径

使用 Python `resource.getrusage(RUSAGE_SELF)` 的进程用户 CPU 时间与内核 CPU 时间，在每个正式推理阶段前后取差。进程全部线程计入，不测其他应用和下载进程；这些模型不使用子进程进行推理。墙钟采用 `time.perf_counter()`。加载、热身、读音频不计入 CPU 与推理耗时；逐样本写结果也在测量范围外。

`平均进程 CPU = 100 × ΣCPU 秒 / Σ墙钟秒`。不是逐样本百分比的算术平均。`整机比例 = 平均进程 CPU / 15`。`平均占用核数 = 平均进程 CPU / 100`。这是完成该任务时的平均占用，不是瞬时峰值；没有采样最大 CPU 百分比。它与处理速度和累计 CPU 秒应一起阅读，不可单靠低占用判定效率更好。

完整流程逐阶段串行测量：FireRed 的 ASR + CT-Punc + fa-zh/归属 + Nemotron 3；Qwen 的 ASR + fa-zh/归属 + Nemotron 3；MOSS 的原生 ASR/分人 + fa-zh。独立 Nemotron 3 同一次推理结果供 FireRed/Qwen 使用，两者均计入相同的阶段耗时和 CPU 时间，体现各自完整流程成本。没有同时执行两套模型推理；下载可在后台进行。未关闭用户其他应用，故墙钟和 CPU 占用是当前主机环境的一次测量，不是隔离服务器上的多次统计。

逐样本逐阶段记录：[CSV](cpu-by-sample-stage.csv)。主比较固定十场，600 秒；连续补测另一场 180 秒。ASR 与对齐在第一场前 5 秒音频上热身；CT-Punc 以固定短句热身。所有三套模型均 FP32、CPU；Torch intraop=4、interop=1，batch=1。数值没有用线程配置或旧耗时推算。

峰值内存采用进程生命周期的最大 RSS，包括模型加载阶段；同一进程处理 11 段，故主集和补测表引用的是该 ASR 进程共同峰值。此值不代表推理常驻内存。

## 运行时版本

| 阶段 | Torch | 其他主要依赖 |
| --- | --- | --- |
| FireRed ASR | 2.10.0 | Transformers 5.1.0、kaldi-native-fbank 1.23.0 |
| Qwen ASR | 2.10.0 | Transformers 5.17.0 |
| MOSS 与 Nemotron 3 | 2.15.0 | Transformers 5.22.1 |
| CT-Punc 与 fa-zh | 2.14.1 | FunASR 1.4.16 |

各模型保留已验证的兼容环境，未升级旧环境。结果反映各自运行时下的完整 CPU 路径性能；每个环境都固定 4 个 intraop 和 1 个 interop 线程。

## FireRed 官方模型与代码

- [官方模型](https://huggingface.co/FireRedTeam/FireRedASR2-AED)，revision `2304afed56eacfee6256dee5937ed22ffa0b64ec`。
- [官方代码](https://github.com/FireRedTeam/FireRedASR2S/tree/4e7d9aaf4482a47cec1724807026b9b151926eb5)，commit `4e7d9aaf4482a47cec1724807026b9b151926eb5`。
- 参数：1,152,521,275；CPU FP32；Torch 2.10.0。
- 主权重：4,731,558,506 字节；本地完整 SHA-256 `4677cbd30988d63ed3e777f6a42a1e5260a3865317f6e15e488bef40954f7054`，与官方 LFS 声明一致。
- beam=3、nbest=1、softmax smoothing=1.25、length penalty=0.6、eos penalty=1.0；不使用外部语言模型，官方默认自动解码长度上限。
- 30 秒无重叠固定分块，与 Qwen 相同。主测试每场 2 块，连续补测 6 块；MOSS 为原生整段识别，短片生成上限 2048、长片 4096。
- 使用官方特征提取与 beam search，不启用官方 CTC 时间戳；以共同 fa-zh 对齐生成字级时间与说话人归属。补标点时核对规范化文字完全不变。
- 权重使用 `torch.load(mmap=True)` 加载以减轻载入压力；不改推理图或参数，加载不计时。加载权重 missing/unexpected keys 均为空；模型参数 device=CPU、dtype=FP32 已检查。推理时禁止网络访问。

## 指标与限制

沿用此前的参考区间、音频哈希、文字规范化、最优匿名标签匹配与 DER 配置。cpCER 仍只使用五场 AISHELL-4、53 个完整区间、1071 个规范化参考字符；它是文字、对齐与归属的联合错误。AliMeeting 没有本地人工文字，不评 cpCER。分区重叠计入，同人时间自重叠取并集，官方 pyannote 与精确积分交叉核对。未人工听校、未测人工句界正确率。原始文本不润色，待确认不自动删除。

## 证据文件

[CPU 测量函数](evidence/cpu_usage.py) · [FireRed 运行环境](evidence/firered-requirements-lock.txt) · [产物校验结果](evidence/verification.json) · [权重版本与完整哈希](evidence/firered-checkpoint-verification.json)

## 配置数值怎么读

| 配置 | 含义 |
| --- | --- |
| 4 intraop / 1 interop、15 核 | 前者是 Torch 并行设置，后者是主机核数和整机折算分母；不保证四核满载。 |
| batch=1、beam=3、nbest=1 | 每次一个输入，搜索保留三个候选，返回一个最佳候选；不是三位说话人，也不是只计算返回的候选。 |
| smoothing=1.25 | logits 除以 1.25 后再求概率，是解码参数，不是性能倍数。 |
| length penalty=0.6 | 候选长度归一化指数，将候选累积分数除以 `((5 + 长度)/6)^0.6`。 |
| eos penalty=1.0 | 结束符分数乘数；1.0 为不额外缩放，不表示结束概率 100%。 |
| 30 秒、2/6 块 | FireRed/Qwen 对每个 60 秒主样本切 2 块，对 180 秒补测切 6 块；不代表一句话长度。 |
| 2048/4096 token | MOSS 短片/长片的输出长度限制，含其时间和说话人控制标记；不能当作汉字数。 |
| FP32、GiB、参数和文件字节 | 分别表示计算精度、驻留内存单位、参数元素数量和磁盘文件大小；是不同维度。详见[指标说明](metrics.md#内存-参数与数值精度)。 |
| 版本号、revision、SHA-256 | 定位软件与文件的标识，不是质量或性能得分。 |

[CSV 和 JSON 全部数值字段](metrics.md#csv-和-json-字段对照)解释逐行阶段记录、六条分组汇总、检查次数和历史保护日志的不同统计范围。
