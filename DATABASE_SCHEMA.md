# 当前数据库结构说明

当前项目使用统一的 SQLite 数据库文件：

- `data/posts.db`

它现在承担两类数据：

- 所有帖子的正文内容
- 所有帖子的轻量元数据

## 表结构

### `posts`

用途：存帖子正文。

```sql
CREATE TABLE IF NOT EXISTS posts (
    post_no TEXT PRIMARY KEY,
    content TEXT NOT NULL
);
```

字段：

- `post_no`: 帖子编号，如 `No.67561250`
- `content`: 帖子正文

### `post_meta`

用途：存帖子轻量元数据，供阅读页分页、图片判断、跨线程引用和时间显示使用。

```sql
CREATE TABLE IF NOT EXISTS post_meta (
    post_no TEXT PRIMARY KEY,
    folder TEXT NOT NULL,
    user_id TEXT NOT NULL,
    po INTEGER NOT NULL,
    image_ext TEXT NOT NULL,
    ts INTEGER NOT NULL DEFAULT 0
);
```

字段：

- `post_no`: 帖子编号
- `folder`: 所属线程文件夹
- `user_id`: 发帖用户 ID
- `po`: 是否 PO，`1` 是，`0` 否
- `image_ext`: 图片扩展名，没有图时为空字符串
- `ts`: 发帖时间戳，Unix timestamp，秒级；没有时为 `0`

## 页面读取链路

正常阅读当前线程时：

1. 先读线程目录下的 `thread.json` 和 `meta/*.json`
2. `meta/*.json` 里拿到当前页有哪些 `post_no / user_id / po / image_ext / ts`
3. 再去 `posts` 表里批量查正文
4. 服务端把 `ts` 格式化成页面显示的时间字符串

跨线程 `>>No.xxx / >>Po.xxx` 跳转时：

1. 先标准化引用目标
2. 从 `post_meta` 查 `folder / user_id / po / image_ext / ts`
3. 从 `posts` 查正文
4. 拼成完整帖子对象返回前端

## 当前不在数据库中的内容

下面这些仍然来自文件，而不是 SQLite：

- 线程标题
- `tags`
- `series`
- `installment`
- `genre`
- `status`
- `updated_at`
- 线程总帖子数
- 线程总图片数
- 分片信息

对应文件：

- `info.json`
- `thread.json`
- `meta/*.json`

## 代码位置

- 建表与写入： [consolidate_data.py]
- 线程分片生成： [Concate.py]
- 服务端读取与格式化时间： [thread_reader_server.py]
