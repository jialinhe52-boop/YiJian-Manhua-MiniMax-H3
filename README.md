# H3 漫剧云端工作流

这是一个面向 AutoDL.Art 应用实例的 MiniMax-H3 单卡工作流包。它把 ComfyUI
工作流封装成稳定的 HTTP API，供一键漫剧等软件直接调用。

首版目标：

- 文生、首帧、首尾帧、尾帧和多参全能参考共用一套接口，并通过生成模式自动切换。
- 多参支持最多 9 张角色、场景、物品或画风参考图。
- 全能参考支持最多 9 图、3 段参考视频和 3 条独立参考音频，并可复用视频原声。
- 严格按调用方传入的 4-15 秒生成，不擅自改成 6 秒。
- 每次请求只生成一个视频。
- 内置 `draft`、`balanced`、`quality` 三档参数。
- 接受普通中文、即梦式自然语言和 H3 结构化提示词。
- API 异步返回任务 ID，软件可轮询状态并下载视频。

## 目录

```text
config/presets.json       三档速度和画质参数
gateway/                  H3 API 网关
scripts/                  AU 实例安装、模型下载和启动脚本
tests/                    不依赖显卡的接口和工作流测试
workflows/upstream/       官方 ComfyUI 工作流原件
workflows/generated/      生成后的漫剧工作流
```

RunningHub 创作者版由 `scripts/build_runninghub_creator_workflow.py` 生成，输出为
`workflows/generated/RunningHub_YiJianManJu_H3_Director_Studio_v1.json`。它以官方
H3 Ref2VA 执行链为上游，重新设计了漫剧教学控制面、9 图 3 视频 6 音轨参考区、
5-15 秒时长换算、4/8 步速度档位和原创提示词框架。发布范围与署名要求见
`docs/RUNNINGHUB_CREATOR_RELEASE.md`。

## API

创建视频：

```http
POST /v1/videos
Content-Type: application/json

{
  "prompt": "古装少女回头看向镜头，衣摆随风摆动，镜头缓慢推近",
  "duration": 15,
  "aspect_ratio": "9:16",
  "preset": "balanced",
  "generation_mode": "i2va",
  "prompt_mode": "jimeng",
  "first_frame": "data:image/png;base64,..."
}
```

查询任务和下载视频：

```http
GET /v1/videos/{job_id}
GET /v1/videos/{job_id}/content
```

响应中的 `requested_duration` 永远保留调用方请求值。由于 H3 潜空间帧数必须落在
固定网格，实际帧长可能相差不到一帧网格，但网关不会替用户改成其他时长。

## AU 部署顺序

1. 在一台空白的 AU 应用实例内上传本目录。
2. 运行 `bash scripts/install.sh`。
3. 运行 `bash scripts/download_models.sh all`。
4. 运行 `bash scripts/start.sh`。
5. 用 `bash scripts/smoke_test.sh` 验证 API。
6. 实机生成 4 秒、8 秒、15 秒各一条，记录耗时和显存。
7. 保存为自己的镜像，再提交应用实例广场。

完整应用同时预装 FL2VA 与 Ref2VA。文生、首帧、首尾帧和尾帧分别对应 T2VA、I2VA、
FL2VA、L2VA；选择多参全能参考时切到 Ref2VA。两套扩散权重不能互相替代。
参考模式按官方标签顺序自动生成 `<Picture n>`、`<Video n>` 和 `<Audio n>`，软件
调用方无需自行编号。

即梦提示词可以直接使用。Ref2VA 模式使用官方六段结构；T2VA、I2VA、FL2VA、L2VA
使用官方三段结构，并在首帧/尾帧模式加入精确时间锚点。不同模型对抽象词、
复杂运镜和角色一致性的理解仍有差异，首帧/尾帧约束通常比只写文字更稳定。

普通用户直接访问 `6006` 端口即可看到生成网页；软件接入使用同一端口下的
`/v1/videos` 接口。应用默认队列上限是 4，且每个请求只有一个输出。

## 上游与署名

- MiniMax-H3 模型与算法：MiniMax-AI。
- ComfyUI 及官方 H3 节点、工作流：Comfy-Org。
- Turbo LoRA：配置文件中标注的对应 Hugging Face 仓库。
- 本仓库原创部分：API 网关、参数校验、任务持久化、提示词整理和 AU 部署脚本。

发布应用和填写创作激励时，应如实填写“算法非原创、封装代码原创”，并附上游地址。
