# 软件接入 API

## 创建任务

`POST /v1/videos`

```json
{
  "prompt": "即梦或普通中文视频提示词",
  "duration": 15,
  "aspect_ratio": "9:16",
  "preset": "balanced",
  "generation_mode": "ref2va",
  "prompt_mode": "jimeng",
  "style": "manhua",
  "seed": -1,
  "first_frame": null,
  "last_frame": null,
  "reference_images": [
    {"data": "data:image/png;base64,...", "role": "character", "name": "女主林晚"},
    {"data": "data:image/png;base64,...", "role": "scene", "name": "雨夜车站"}
  ],
  "reference_videos": [
    {"data": "data:video/mp4;base64,...", "name": "缓慢推镜", "use_audio": true}
  ],
  "reference_audios": [
    {"data": "data:audio/wav;base64,...", "name": "角色音色"}
  ],
  "reference_image_size": "match",
  "accepted_terms": true
}
```

`generation_mode` 支持五种取值：

| 模式 | 必需输入 | 提示词格式 |
| --- | --- | --- |
| `t2va` | 无参考素材 | H3 基础三段式 |
| `i2va` | `first_frame` | 首帧对齐说明 + 三段式 |
| `fl2va` | `first_frame`、`last_frame` | 首尾帧对齐说明 + 三段式 |
| `l2va` | `last_frame` | 尾帧对齐说明 + 三段式 |
| `ref2va` | 至少一个参考数组素材 | Ref2VA 六段式 |

不同模式的参考输入不能混用。省略 `generation_mode` 时，服务仍会按输入素材自动推断，
兼容旧版调用。Ref2VA 最多 9 张参考图、3 段参考视频和 3 条独立参考音频；`use_audio`
决定参考视频原声是否作为音频参考，标签顺序由服务自动构建。响应始终只有一个视频任务：

```json
{
  "id": "任务编号",
  "status": "queued",
  "requested_duration": 15,
  "output_count": 1
}
```

## 查询与下载

每 2-3 秒调用 `GET /v1/videos/{id}`。完成时响应包含 `content_url`，再请求该地址下载。

如果云端设置了 `H3_API_KEY`，所有 `/v1/videos` 请求都要带：

```http
Authorization: Bearer <H3_API_KEY>
```

软件必须在用户接受 MiniMax H3 使用条款后才发送 `accepted_terms: true`。请求 15 秒时
保持 `duration: 15`，不要由插件改写为 6 秒；同一分镜不要并行提交三次。
