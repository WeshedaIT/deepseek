# SellFox API Explorer · 赛狐开放平台接口浏览器

把赛狐（SellFox）开放平台的 **523 个接口**做成可搜索、可浏览的树形浏览器。
两种用法：**双击 `index.html` 直接看**（离线、零依赖），或**跑 Python 服务**顺便在线调接口。

---

## 一、直接打开（推荐先试这个）

```
双击 index.html
```

就这样。不需要 Python、不需要本地服务器、不需要联网、不需要构建。

打开后可以：

- 左侧浏览 **17 个业务模块 / 110 个分组 / 523 个接口**
- 点击模块展开或折叠子分组
- 点击接口查看详情：请求方法、完整路径、公共参数、请求体示例、签名算法
- 顶部搜索框按**接口名称或路径**过滤（按 `/` 键快速聚焦）
- 按 `POST` / `GET` 过滤
- `↑` `↓` 键在接口间快速切换
- 一键复制接口路径、切换深浅色主题

> 这个文件是**自包含**的：所有 HTML、CSS、JavaScript 和 523 条接口数据都内联在 `index.html` 里，
> 打开时只读取本地文件本身，不发出任何网络请求。

---

## 二、跑起来调真实接口

静态页只能浏览，不能发请求——浏览器同源策略会挡住对 `openapi.sellfox.com` 的直接调用。
需要真正调接口时，用仓库里的 Python 服务，它内置本地代理和签名：

```bash
python3 sellfox_explorer.py
```

```
SellFox API Explorer 已启动: http://127.0.0.1:8765/
  接口 523 个 / 模块 17 个
  上游 https://openapi.sellfox.com
```

然后浏览器打开 `http://127.0.0.1:8765/`。

零第三方依赖，只要有 Python 3.8+ 就能跑。

### 它会提供什么

| 路由 | 用途 |
| --- | --- |
| `GET /` | 返回 `index.html`——**和双击打开的是同一个文件**，不是另一份页面 |
| `GET /api/tree` | 返回完整的接口树 JSON（`data/api_tree.json` 的内容） |
| `GET /api/health` | 健康检查，返回接口数、模块数与上游地址 |
| `POST /api/proxy` | 带签名转发到 `openapi.sellfox.com`，绕过 CORS |

`POST /api/proxy` 请求体格式：

```json
{
  "path": "/api/commodity/create.json",
  "access_token": "你的 access_token",
  "client_id": "你的 client_id",
  "app_secret": "你的 app_secret",
  "body": { "任意业务参数": "..." }
}
```

代理会自动补齐并签名公共参数：`access_token`、`client_id`、`timestamp`（13 位毫秒）、
`nonce`（每次唯一）、`sign`（MD5）。响应里会带回上游状态码、耗时、实际发出的参数（已隐去 token）和上游返回体。

---

## 三、数据从哪来 / 怎么更新

**唯一数据源是 `data/api_tree.json`。** 页面上显示的接口树、Python 服务校验接口是否存在、
以及统计数字，全部来自这一个文件——不存在第二份手抄的接口清单。

```
data/api_tree.json   ←  唯一数据源（523 接口 / 110 分组 / 17 模块）
        │
        ├── build.py 内联 ──→  index.html      （自包含静态页）
        └── 直接读取 ──────→  sellfox_explorer.py （Python 服务）
```

### 修改后重新生成

改完 `data/api_tree.json` 后：

```bash
python3 build.py
```

```
已生成 index.html  (124.8 KB)
    523 API / 110 分组 / 14 文档 / 17 模块
    build d9969e564c611458
```

### 检查有没有忘记重新生成

```bash
python3 build.py --check          # 页面是否与数据源同步
python3 test_consistency.py       # 完整一致性校验（10 项）
```

`build.py` 会把数据源的 SHA-256 指纹写进 `index.html` 的 `<meta name="data-build-hash">`。
如果数据改了但没重新构建，`--check` 会直接报出来：

```
FAIL: index.html 已过期 (页面 d9969e564c611458 != 数据 8a3f1c02...)
      请运行 python3 build.py
```

`test_consistency.py` 校验得更细：内联树与数据源**逐节点比对**、静态页/数据源/Python 服务
三方接口数必须相等、页面不能残留占位符、不能有外部资源依赖。

### 数据格式

```json
{
  "source": "https://sellfoxapi.apifox.cn/",
  "tree": [
    {
      "name": "商品",
      "type": "apiDetailFolder",
      "id": 12345,
      "children": [
        { "name": "创建SKU", "type": "apiDetail", "id": 67890,
          "method": "POST", "path": "/api/commodity/create.json" }
      ]
    }
  ]
}
```

`type` 有三种：`apiDetailFolder`（分组，含 `children`）、`apiDetail`（接口，含 `method` + `path`）、
`doc`（开发指南文档）。统计数字由树结构推导，不信任文件里可能过期的 `stats` 字段。

---

## 四、项目结构

```
.
├── index.html              # 自包含静态页 —— 双击即可用（由 build.py 生成，勿手改）
├── build.py                # 模板 + 数据 → index.html
├── src/explorer.html       # 页面模板，含 __API_TREE_DATA__ 占位符
├── data/api_tree.json      # 唯一数据源：523 个接口的完整树
├── sellfox_explorer.py     # Python 服务：静态页 + 代理 + 签名
└── test_consistency.py     # 三方一致性测试
```

`index.html` 是**构建产物**，不要直接编辑——下次 `build.py` 会覆盖它。
要改页面样式或交互，改 `src/explorer.html`，然后重新构建：

```bash
python3 build.py
```

---

## 五、签名规则

所有请求都要带公共参数，服务端会校验：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `access_token` | string | 卖家授权后获得的访问令牌 |
| `client_id` | string | 开放平台分配的应用 ID |
| `timestamp` | long | 13 位毫秒时间戳，与服务器相差需在 ±15 分钟内 |
| `nonce` | int | 随机整数，每次请求唯一，用于防重放 |
| `sign` | string | MD5 签名 |

签名算法：

1. 取所有请求参数（含公共参数，**不含 `sign` 本身**）
2. 按参数名 ASCII 升序排列，拼成 `key=value&key=value`
3. 末尾追加 `&key=你的AppSecret`
4. 对整串做 MD5，取 32 位小写十六进制

`sellfox_explorer.py` 的 `md5_sign()` 就是这个实现，代理会自动调用。

---

## 六、已知限制

- 静态页**只能浏览，不能发请求**——受浏览器同源策略限制，必须通过 Python 代理才能调接口。
  页面的「在线调试」区块会明确提示这一点，不会让人误以为双击打开就能直接调用。
- 接口树来自赛狐开放平台文档站的人工提取，文档更新后需要重新抓取并重建。
- 同一接口路径可能同时出现在多个分组下（例如「获取其他入库自定义类型」同时在
  「其他入库」和「其他出库」里），此时接口计数按文档条目算，`523` 是条目数。
