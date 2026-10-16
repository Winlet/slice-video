# xmlslice

根据 XML 弹幕密度，从 MP4 里切出高能片段。

支持弹幕姬 / DanmakuFactory 这类录播 XML：每条弹幕是 `<d p="秒数,...">`，第一段就是相对视频开头的秒数。礼物、醒目留言和上船记录不计入密度。

## 环境

- Python 3.9+
- ffmpeg

macOS 安装 ffmpeg：

```bash
brew install ffmpeg
```

## 使用

在本目录执行，不需要额外安装依赖：

```bash
python3 -m xmlslice \
  -x "弹幕.xml" \
  -v "录像.mp4" \
  -d 60 \
  -n 3 \
  --overlap 30 \
  --step 1
```

| 参数 | 含义 | 默认 |
|---|---|---|
| `-x` | XML 弹幕 | 必填 |
| `-v` | MP4 视频 | 必填 |
| `-d` | 每段时长（秒） | 60 |
| `-n` | 切几段 | 1 |
| `--overlap` | 片段之间允许的最大重叠（秒） | 30 |
| `--step` | 滑动窗口步长（秒） | 1 |
| `-o` | 输出目录 | 与视频同一目录 |

输出文件名形如 `123s_原视频名.mp4`，`123` 是片段在原视频中的起始秒数。切片使用 ffmpeg 流复制，不重新编码，起点会对齐到前一个关键帧，所以实际开头可能比计算时间略早。

## 测试

```bash
python3 -m unittest discover -s tests
```
