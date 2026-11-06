# 数据来源和样本版本

[返回测试总览](README.md)

本次公开的是评测说明与模型生成转写，未上传音频、人工参考全文或模型权重。

## 原始数据署名

- **AISHELL-4**，由 AISHELL 团队提供。[原始发布与许可](https://www.openslr.org/111/)，[所用镜像](https://huggingface.co/datasets/AISHELL/AISHELL-4)。固定 revision：`aada72727856313b19d4a030383c426364931dbf`。使用 test 音频与人工 TextGrid 的文字、说话人活动标注。
- **AliMeeting**，由 AliMeeting 团队提供。[原始发布与许可](https://www.openslr.org/119/)，[所用镜像](https://huggingface.co/datasets/ggfox00000/dia-alimeeting-test)。固定 revision：`cef2837c4a1a0762074522c1bbbbb90eb4d1acf5`。使用 test 远场音频与人工标注衍生 RTTM；该镜像无人工文字，不评文字错误率。

原始 OpenSLR 页面均标示 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)。这里的语料衍生转写保留相同署名与相同方式共享要求；改动为音频裁剪、模型自动转写、时间对齐、匿名说话人归属及逐句排版，未人工听校。此说明仅针对本目录语料衍生内容，不改变仓库其他文件的许可。

镜像元数据存在差异：AliMeeting 镜像标为 CC BY-NC 4.0，AISHELL 镜像标为 Apache 2.0。记录此差异，不以镜像标签替换原始上游声明；原音频未在此仓库再分发。

## 处理与选择

原录音为多通道远场会议，固定选阵列第 1 通道，转为 16 kHz 单声道 PCM16。主比较每场 60 秒，候选起点 60–240 秒、步长 15 秒，优先说话人数、其次区间数量、再次最早起点；因此属于多人场景压力片段，不是随机语料统计。连续补测来自另一场会议 60–240 秒。

片段时间与本地音频 SHA-256 见下表。完整源文件未全部下载，故没有把上游 LFS 哈希描述为本地整文件校验。

| 样本 | 原始区间 秒 | 本地 PCM16 WAV SHA-256 |
| --- | ---: | --- |
| aishell4_L_R003S01C02 | 150–210 | `5552aeccc2f81c81f967a6d6f9caabe8858557d64ceb5128048a5f682bc08a17` |
| aishell4_L_R004S01C01 | 180–240 | `2f265cd02a578ee9927f5482f5961fc69692b91f7bc47b03a6f839d7c5b43c1d` |
| aishell4_M_R003S01C01 | 150–210 | `afaa426ff84df80ac8f73a5a96929c143c8947e3de8f7a98eb39639ce29c6ef3` |
| aishell4_S_R003S01C01 | 120–180 | `a9ffe6dd78a9609350bd5f973debbe1b8c8c17ef402967805e4b6a57acabbf10` |
| aishell4_S_R004S01C01 | 225–285 | `3fdeae2f01b12b092d3616f23f2ea136ae0389cc0adcbc0f9bd1f88b914aafd3` |
| alimeeting_R8002_M8002_MS802 | 60–120 | `496a7a758a5bd39998f06b87c0db98a147cd0cbb39cb21962e5f7e09e9b37151` |
| alimeeting_R8004_M8005_MS803 | 210–270 | `8974d9d0836acacb4acf9cd775b340b854f5018d215fb19a98571501e085fb23` |
| alimeeting_R8005_M8007_MS806 | 120–180 | `349891bb739c6870dd706c1f234a178b457f46fdb6286551d3f4a162b61cd99e` |
| alimeeting_R8006_M8012_MS803 | 120–180 | `cb4750c27403e4caaa589ee791c3fcdc7d79a8e9e30871bf8a0f06e11ed73797` |
| alimeeting_R8008_M8014_MS807 | 180–240 | `914975b0b27e75fc2764569db0bd8a51fbd068d9c7e63886c47aa8da12794929` |
| alimeeting_R8002_M8003_MS803_long180 | 60–240 | `27ce0e039b031b6d123cd22d6b437e3ae253ed402e7392734c48ad9387f509ce` |
