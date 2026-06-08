# NMB-LocalReader
可部署于服务器的本地数据阅读器

## 1. 使用说明

### A. 下载数据

#### ver1.0.0

目前下载数据的程序有两个：`NMBGet.py` 和 `BOGGet.py`，分别对应抓取 X岛 和 Bog。（`BOGGet.py` 程序版本较旧，需要手动创建部分文件。一般用不上，(　ﾟ 3ﾟ)就这样吧）
需要在文件顶部需要设置`THREAD_URL`（连接）`THREAD_TITLE`（标题）、`TAGS`（标签）、`SERIES`（系列）、`INSTALLMENT`（卷）、`GENRE`（类型）、`STATUS`（状态）。
- `THREAD_TITLE`必填并且需要与下载时的文件夹名相同。
- `TAGS`可以自己随便设置，后续用于检索，没有就填`[]`。
- `SERIES`建议是同一个世界观下的系列，比如大洛山宇宙，没有就填`其他`。
- `INSTALLMENT`建议是同一个系列下的顺序，可以填整数或小数；没有就填`None`。
- `GENRE`是板块或者文档类型，比如`规则怪谈`、`都市传说`、`跑团`、`小说`之类的。
- `STATUS`是文档状态，比如`连载`、`完结`、`痛`之类的，不知道就`其他`。
另外如果发现下载失败或者从第100页开始都是重复的数据，那么请根据自己登陆饼干之后的cookie修改文件开头的`HEADERS`中的cookie。
程序中设置了每两页的获取间隔，不建议修改，减少点服务器压力。
`NMBGet.py`设置了已下载内容检查，如果发现下载失败，那么请重新运行，程序会自动跳过已经下载的页面和图片，继续下载未下载的页面。

下载后的文件在`original_pages`文件夹下，`pages`里是网页的json数据，图片是对应串号内的图片。`thread_meta.json`储存标签信息。`concate_pending.json`是用于后续处理的flag。

#### ver1.1.0

新增了AWD的数据下载程序，50页以内的串，直接修改`AWDGet.py`中的内容然后运行就行。50页以上的需要先运行`AWDLogin.py`获取登陆状态，然后运行`AWDGet.py`下载数据。

由于AWD的串信息不会直接显示绝对时间，所以时间以年为准，设置成了该年的一月一日。

增加了批量下载的程序`BatchDownload.py`，在`TASK`中按照格式填入信息，运行时即可顺序下载。

### B. 整理单个串数据

#### ver1.0.0

整理数据程序为`Concate.py`，
可修改`META_CHUNK_SIZE`（单个文件串数）
- `META_CHUNK_SIZE`是单个文件串数，主要影响页面加载速度，太大的话会半天加载不出来。默认是1000，只建议减小不建议增大。

程序会扫描`original_pages`文件夹下的各个文件夹，如果有`concate_pending.json`文件，那么会执行整理，否则会自动跳过。
运行后数据会整理到`data`下对应名称的文件夹下。`meta`文件夹下的json文件是串号、饼干、时间等信息，用于检索。`info.json`是文档概览信息，包括串数、标签等等。`posts.db`是储存了当前串内各个回复具体内容的数据库文件。`thread.json`是整合了部分meta和info的信息。（按理说这里可以在再整理一下但是，能跑，(　ﾟ 3ﾟ)就这样吧）

#### ver1.0.1

增加了`JSONtoMD.py`，用于将整理后的串数据转换为Markdown格式，方便应用于其他程序。 ﾟ∀ﾟ)σ比如>>No.66161736
程序会扫描`original_pages`文件夹下的各个文件夹，如果有`concate_pending.json`文件，那么会执行整理，否则会自动跳过。
这个程序不会删掉`concate_pending.json`文件，因此建议两种类型都需要时先运行`JSONtoMD.py`再运行`Concate.py`，或者也可以将`REQUIRE_PENDING_MARKER`设置为`False`，这样程序会无视`concate_pending.json`文件的存在。
运行完之后数据生成在`md_pages`文件夹下，每个串对应一个文件夹（不论是否分页都有）。
此外可以通过`SPLIT_OUTPUT`和`PER_FILE`设置是否分页和页内串数。

#### ver1.2.0
增加了AWD的数据之后，发现之前的程序忽略了AWD也有新串，会导致超过50000000的串号跟XD串号有冲突。主要体现在狼患跟大洛山冲突，所以修改了`Concate.py`，增加了AWD的串号检查，如果发现超过50000000的串号，会在前面加个90。希望这个修改不会是个坑|ー` )。

### C. 合并数据

#### ver1.0.0

合并数据程序为`consolidate_data.py`，没啥好改设置的，注意一下DEFAULT_CHUNK_SIZE和DB_BATCH_SIZE就行。

运行后数据会整合到`data`下的`posts.db`和`index.json`中，`posts.db`是整合了所有串的数据库文件，`index.json`是整合了所有串的目录索引。图片会统一到`images`文件夹下。

### D. 生成目录索引

#### ver1.0.0

如果严格按照上面的步骤进行，不需要这一步。但如果手动修改了`data`下的`info.json`或者`thread.json`，那么需要运行`build_index.py`重新生成目录索引。

### E. 账户管理

#### ver1.0.0

默认用户名和密码都是admin，如果想部署到服务器，建议修改。修改方法：
- 第一次修改的话，建议直接删除`auth_users.json`。
- 修改`manage_users.py`中的`TARGET_USERNAME`和`TARGET_PASSWORD`字段，添加新的用户名和密码。
- 运行`manage_users.py`，会自动生成`auth_users.json`文件。
- 如果需要删除用户，请修改`auth_users.json`文件，删除对应的用户名和密码。
- 如果需要添加用户，请修改`manage_users.py`文件并运行，添加新的用户名和密码。

书签和已阅读标签都是跟着账户走的。

#### ver1.2.0

增加了自主注册功能，用户名限制为 3-32 位，只允许字母、数字、_、-，密码大于6位就行
注册时必须提供邀请码。邀请码在`invite_codes.json`中管理，参数如下：
- `code`: 邀请码文本
- `enabled`: 是否启用
- `max_uses`: 最大可用次数，0 表示不限次数
- `used_count`: 已使用次数，注册成功会自动累加
- `expires_at`: 过期时间戳，0 表示不过期
- `note`: 备注

如果注册时报错Permission Denied，需检查threadreader的权限，可以考虑直接给threadreader文件夹777权限。

### F. 部署nginx

本地的话就无所谓了。
如果需要部署到服务器，可以参考`deploy/`目录下的`DEPLOY_SERVER.md`文件。
不部署nginx也可以通过`ip:端口号`访问。

### G. 启动

运行`thread_reader_server.py`即可启动服务。默认使用4567端口，如果需要修改，请修改`thread_reader_server.py`中的`PORT`变量。
默认情款下使用浏览器访问http://127.0.0.1:4567 即可访问登陆页。

## 2. 顶层结构概览

当前顶层主要分为 5 类内容：

### A. 服务端与网站运行核心文件

- `thread_reader_server.py`
- `index.html`
- `server_home.html`
- `post_reader_server.html`
- `server_portal.css`
- `server_auth.js`
- `server_login.js`
- `server_home.js`
- `post_reader_server.css`
- `post_reader_server.js`
- `auth_users.json`
- `server_layout.json`
- `manage_users.py`
- `invite_codes.json`

这部分组成当前网站版阅读器的核心运行结构：

- `thread_reader_server.py` 负责 HTTP 服务、登录校验、目录接口、阅读接口、图片访问、书签与已读状态
- `index.html` + `server_login.js` 是登录入口
- `server_home.*` + `server_portal.css` 是目录页
- `post_reader_server.*` 是服务器阅读页
- `server_auth.js` 是前端鉴权辅助脚本
- `auth_users.json` 存放账号信息
- `manage_users.py` 是管理用户脚本
- `invite_codes.json` 保存邀请码信息

### B. 本地阅读器文件

- `post_reader.html`
- `post_reader.css`
- `post_reader.js`

这部分是本地直接读取文件的阅读器版本，不依赖当前网站后端接口。

### C. 抓取与整理脚本

- `NMBGet.py`
- `BOGGet.py`
- `AWDGet.py`
- `Concate.py`
- `consolidate_data.py`
- `build_index.py`

这部分对应完整的数据处理链路：

- 抓取帖子与图片
- 合并/整理线程数据
- 生成目录索引
- 本地或服务器侧整合


### D. 说明与结构文档

- `DATABASE_SCHEMA.md`
- `README.md`

其中：

- `DATABASE_SCHEMA.md` 说明数据库结构
- `README.md` 是当前说明文档

### E. 部署配置目录

目录：`deploy/`

包含：

- `DEPLOY_SERVER.md`
- `nginx-thread-reader.conf`
- `thread-reader.env`
- `thread-reader.env.example`
- `thread-reader.service`

用途分别是：

- 部署说明
- nginx 反向代理配置
- 服务环境变量文件
- 环境变量示例
- systemd 服务配置

如果是本地阅读这部分可以忽略，但如果是部署到服务器，则建议配置。
