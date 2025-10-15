# JUST A PLAN

## Complete Solution

个功能实现需要**跨主机数据传输、图像识别、LLM 决策、硬件键鼠模拟**四个核心模块联动，整体技术路线可拆解为 “视频流传输→图像解析→智能决策→硬件控制” 的闭环流程，以下是具体实现方案。

### 一、核心模块拆解与实现方案

#### 1. 第一步：B 主机视频流→A 主机传输（低延迟优先）

核心目标是将 B 主机的 CSGO 画面实时传递给 A 主机，**延迟需控制在 100ms 内**（避免影响游戏操作），推荐两种主流方案：

| 方案类型   | 实现工具 / 硬件                      | 优势                          | 劣势                                                     |
| ---------- | ------------------------------------ | ----------------------------- | -------------------------------------------------------- |
| 硬件采集卡 | 圆刚 GC553、美乐威 USB 采集卡        | 延迟极低（20-50ms），画质无损 | 需额外采购硬件（300-1000 元），需 B 主机有 HDMI 输出接口 |
| 软件流媒体 | OBS（B 主机推流）+ VLC（A 主机拉流） | 零成本，无需额外硬件          | 延迟较高（80-150ms），需稳定局域网，画质可能压缩         |

**操作步骤**：

1. 硬件方案：B 主机 HDMI 接采集卡，采集卡 USB 接 A 主机，安装采集卡驱动（如圆刚官方软件），A 主机实时预览 B 主机画面。
2. 软件方案：B 主机打开 OBS，添加 “显示器捕获”（选择 CSGO 窗口），设置推流地址为 A 主机局域网 IP（如 rtmp://192.168.1.100:1935/live）；A 主机打开 VLC，输入该地址拉流，调整画质参数降低延迟。

#### 2. 第二步：A 主机图像识别（提取敌人 / 自身坐标）

核心是从 A 主机接收的视频流中，定位**敌人位置（像素坐标）** 和**自身坐标（游戏内 UI 提取）**，推荐基于 “目标检测模型 + 固定 UI 区域识别” 实现：

- **工具选择**：Python（OpenCV+PyTorch）、YOLOv8 模型（轻量且实时性强）
- 实现步骤
  1. 数据集标注：截图 CSGO 游戏画面，标注 “敌人”（人物轮廓）、“自身坐标”（游戏内左下角 / 右上角数字区域），生成 VOC/COCO 格式数据集。
  2. 模型训练：用 YOLOv8 训练自定义数据集，重点优化 “烟雾 / 障碍物遮挡” 场景的识别精度，训练后导出为 onnx 格式（方便 Python 调用）。
  3. 实时解析：A 主机用 OpenCV 读取视频流帧，调用训练好的 YOLOv8 模型，输出：
     - 敌人信息：每个敌人的像素坐标（x1,y1,x2,y2）、置信度（过滤误识别）。
     - 自身坐标：识别固定 UI 区域的数字（用 Tesseract-OCR 提取文本，转换为游戏内坐标如 “(123, 456)”）。

#### 3. 第三步：LLM 决策（生成键鼠操作指令）

通过 Agent 协调图像识别结果，遵循 MCP（大模型上下文协议）调用 LLM，输出 “前进 / 后退 / 开枪” 等具体操作，核心是**明确 prompt 格式 + 上下文管理**：

- **工具选择**：

  - LLM：GPT-4o-mini（低延迟）、本地化模型（如 Llama 3-8B，需 A 主机有 GPU）。
  - Agent 框架：LangChain（负责上下文管理）、MCP 协议（用 JSON 格式封装上下文）。
  - 通信方式：LLM API 调用（如 OpenAI API）或本地化模型的 Python SDK。

- **实现步骤**：

  1. MCP 上下文定义：用 JSON 封装 “当前场景信息”，确保 LLM 理解游戏逻辑，示例：

     ```json
     {
       "context": [
         {"step": 1, "info": "自身坐标：(123, 456)，当前武器：AK-47"},
         {"step": 2, "info": "敌人1：像素坐标(300,200)-(350,300)，位于自身正前方50米"},
         {"step": 3, "info": "无障碍物，敌人未发现自身"}
       ],
       "user_requirement": "基于CSGO规则，输出下一步键鼠操作（格式：键盘[W/S/A/D/空格/鼠标左键]，鼠标移动[X像素,Y像素]）"
     }
     ```

  2. Agent 逻辑：

     - 输入：接收图像识别模块的敌人 / 自身坐标，更新 MCP 上下文。
     - 调用：将 MCP 格式的 prompt 传给 LLM，设置 “响应格式约束”（如 “仅输出操作指令，不额外解释”）。
     - 输出：解析 LLM 返回结果，转换为标准化指令（如 “键盘 [W]，鼠标移动 [50,0]，延迟 100ms 后键盘 [鼠标左键]”）。

#### 4. 第四步：CH9329 芯片组（A→B 主机键鼠控制）

CH9329 是 USB-HID 协议芯片，可将 A 主机的指令转换为 “物理键鼠信号” 发送给 B 主机，实现 “无软件注入”（降低反作弊风险）：

- 硬件连接
  - CH9329 模块（如淘宝 “CH9329 USB 转串口” 模块）的 USB_HOST 口接 B 主机（模拟键鼠），USB_DEVICE 口接 A 主机（A 主机控制模块）。
- 软件实现
  1. 驱动安装：A 主机安装 CH9329 驱动（官方提供 Windows/Linux 版本），通过串口工具（如 PySerial）与模块通信。
  2. 指令编码：根据 CH9329 datasheet，将 LLM 输出的操作转换为芯片识别的 HID 报告：
     - 键盘指令：如 “W 键按下” 对应扫描码 0x1A，通过串口发送指令`0x00,0x00,0x1A,0x00,0x00,0x00,0x00,0x00`。
     - 鼠标指令：如 “向右移动 50 像素” 对应`0x00,0x32,0x00,0x00,0x00`（第一个字节为按键状态，后两字节为 X/Y 偏移）。
  3. 实时发送：A 主机将编码后的指令通过串口发送给 CH9329，模块自动转换为 USB 键鼠信号，B 主机接收并执行操作。

### 二、关键风险与优化点

1. **反作弊风险**：CSGO 的 VAC 反作弊会检测 “第三方键鼠模拟工具”，CH9329 虽为硬件模拟，但仍有被封禁可能，建议仅在非竞技模式测试。
2. 延迟优化:各模块延迟需叠加（视频传输 50ms + 图像识别 30ms+LLM 决策 100ms+CH9329 20ms），总延迟需控制在 200ms 内，可通过：
   - 降低 YOLOv8 模型分辨率（如 640×640）。
   - 使用本地化 LLM（如 Llama 3-8B 部署在 A 主机 GPU，响应时间 < 50ms）。
3. **识别精度**：针对 CSGO 的 “夜间 / 烟雾” 场景，可在图像预处理阶段增加 “对比度增强”（OpenCV 的 equalizeHist 函数），提升模型识别率。



## Keyboard and mouse control

首先将b主机的视频输出数据传递给a主机，a主机使用图像识别技术识别csgo的游戏界面，得到敌人信息的界面像素点和自己的坐标，然后通过agent和mcp(大模型上下文协议)去调用llm得出我下一步需要操作的键位鼠标的信息（例如前进后退左右开枪什么的），通过ch9329芯片组，输出对应的键盘鼠标信息给b主机



### CH9329芯片

> tips： 使用串口输出数据即可



### Keyboard and mouse data

> tips：键盘鼠标的流量信息并且鼠标移动不能直接定位过去，得有一段路线，而且不能是直线，得使用rand函数



## Image Recognition

### yolo v7

> tips： 实现某一个帧的定位





### 接线方式

> tips：从b主机的视频输出接口获取数据到a主机



## Large Model or agent

### Agent





### Mcp

MCP（Model Context Protocol，模型上下文协议） ，2024年11月底，由 Anthropic 推出的一种开放标准，旨在统一大模型与外部数据源和工具之间的通信协议。MCP 的主要目的在于解决当前 AI 模型因数据孤岛限制而无法充分发挥潜力的难题，MCP 使得 AI 应用能够安全地访问和操作本地及远程数据，为 AI 应用提供了连接万物的接口。

> Function Calling是AI模型调用函数的机制，MCP是一个标准协议，使大模型与API无缝交互，而AI Agent是一个自主运行的智能系统，利用Function Calling和MCP来分析和执行任务，实现特定目标。

#### 工作原理

MCP 协议采用了一种独特的架构设计，它将 LLM 与资源之间的通信划分为三个主要部分：客户端、服务器和资源。

客户端负责发送请求给 MCP 服务器，服务器则将这些请求转发给相应的资源。这种分层的设计使得 MCP 协议能够更好地控制访问权限，确保只有经过授权的用户才能访问特定的资源。

以下是 MCP 的基本工作流程：

- 初始化连接：客户端向服务器发送连接请求，建立通信通道。
- 发送请求：客户端根据需求构建请求消息，并发送给服务器。
- 处理请求：服务器接收到请求后，解析请求内容，执行相应的操作（如查询数据库、读取文件等）。
- 返回结果：服务器将处理结果封装成响应消息，发送回客户端。
- 断开连接：任务完成后，客户端可以主动关闭连接或等待服务器超时关闭。

![img](picture/JUST A PLAN/v2-bb82edf5b8651051be151c279e7679e1_1440w.jpg)



#### MCP 核心架构

MCP 遵循客户端-服务器架构（client-server），其中包含以下几个核心概念：

- MCP 主机（MCP Hosts）：发起请求的 LLM 应用程序（例如其他AI 工具）。
- MCP 客户端（MCP Clients）：在主机程序内部，与 MCP server 保持 1:1 的连接。
- MCP 服务器（MCP Servers）：为 MCP client 提供上下文、工具和 prompt 信息。
- 本地资源（Local Resources）：本地计算机中可供 MCP server 安全访问的资源（例如文件、数据库）。
- 远程资源（Remote Resources）：MCP server 可以连接到的远程资源（例如通过 API）。

#### MCP Server 的工作原理

我们先来看一个简单的例子，假设我们想让 AI Agent 完成自动搜索 GitHub Repository，接着搜索 Issue，然后再判断是否是一个已知的 bug，最后决定是否需要提交一个新的 Issue 的功能。

那么我们就需要创建一个 Github MCP Server，这个 Server 需要提供查找 Repository、搜索 Issues 和创建 Issue 三种能力。

我们直接来看看代码：

```json
const server = new Server(
  {
    name: "github-mcp-server",
    version: VERSION,
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "search_repositories",
        description: "Search for GitHub repositories",
        inputSchema: zodToJsonSchema(repository.SearchRepositoriesSchema),
      },
      {
        name: "create_issue",
        description: "Create a new issue in a GitHub repository",
        inputSchema: zodToJsonSchema(issues.CreateIssueSchema),
      },
      {
        name: "search_issues",
        description: "Search for issues and pull requests across GitHub repositories",
        inputSchema: zodToJsonSchema(search.SearchIssuesSchema),
      }
    ],
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  try {
    if (!request.params.arguments) {
      throw new Error("Arguments are required");
    }

    switch (request.params.name) {
      case "search_repositories": {
        const args = repository.SearchRepositoriesSchema.parse(request.params.arguments);
        const results = await repository.searchRepositories(
          args.query,
          args.page,
          args.perPage
        );
        return {
          content: [{ type: "text", text: JSON.stringify(results, null, 2) }],
        };
      }

      case "create_issue": {
        const args = issues.CreateIssueSchema.parse(request.params.arguments);
        const { owner, repo, ...options } = args;
        const issue = await issues.createIssue(owner, repo, options);
        return {
          content: [{ type: "text", text: JSON.stringify(issue, null, 2) }],
        };
      }

      case "search_issues": {
        const args = search.SearchIssuesSchema.parse(request.params.arguments);
        const results = await search.searchIssues(args);
        return {
          content: [{ type: "text", text: JSON.stringify(results, null, 2) }],
        };
      }

      default:
        throw new Error(`Unknown tool: ${request.params.name}`);
    }
  } catch (error) {}
});

async function runServer() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("GitHub MCP Server running on stdio");
}

runServer().catch((error) => {
  console.error("Fatal error in main():", error);
  process.exit(1);
});
```

上面的代码中，我们通过 `server.setRequestHandler` 来告诉 Client 端我们提供了哪些能力，通过 `description` 字段来描述这个能力的作用，通过 `inputSchema` 来描述完成这个能力需要的输入参数。

我们再来看看具体的实现代码：

```json
export const SearchOptions = z.object({
  q: z.string(),
  order: z.enum(["asc", "desc"]).optional(),
  page: z.number().min(1).optional(),
  per_page: z.number().min(1).max(100).optional(),
});

export const SearchIssuesOptions = SearchOptions.extend({
  sort: z.enum([
    "comments",
    ...
  ]).optional(),
});

export async function searchUsers(params: z.infer<typeof SearchUsersSchema>) {
  return githubRequest(buildUrl("https://api.github.com/search/users", params));
}

export const SearchRepositoriesSchema = z.object({
  query: z.string().describe("Search query (see GitHub search syntax)"),
  page: z.number().optional().describe("Page number for pagination (default: 1)"),
  perPage: z.number().optional().describe("Number of results per page (default: 30, max: 100)"),
});

export async function searchRepositories(
  query: string,
  page: number = 1,
  perPage: number = 30
) {
  const url = new URL("https://api.github.com/search/repositories");
  url.searchParams.append("q", query);
  url.searchParams.append("page", page.toString());
  url.searchParams.append("per_page", perPage.toString());

  const response = await githubRequest(url.toString());
  return GitHubSearchResponseSchema.parse(response);
}
```

可以很清晰的看到，我们最终实现是通过了 `https://api.github.com` 的 API 来实现和 Github 交互的，我们通过 `githubRequest` 函数来调用 GitHub 的 API，最后返回结果。

在调用 Github 官方的 API 之前，MCP 的主要工作是描述 Server 提供了哪些能力(给 LLM 提供)，需要哪些参数(参数具体的功能是什么)，最后返回的结果是什么。

所以 MCP Server 并不是一个新颖的、高深的东西，它只是一个具有共识的协议。

如果我们想要实现一个更强大的 AI Agent，例如我们想让 AI Agent 自动的根据本地错误日志，自动搜索相关的 GitHub Repository，然后搜索 Issue，最后将结果发送到 Slack。

那么我们可能需要创建三个不同的 MCP Server，一个是 Local Log Server，用来查询本地日志；一个是 GitHub Server，用来搜索 Issue；还有一个是 Slack Server，用来发送消息。

AI Agent 在用户输入 `我需要查询本地错误日志，将相关的 Issue 发送到 Slack` 指令后，自行判断需要调用哪些 MCP Server，并决定调用顺序，最终根据不同 MCP Server 的返回结果来决定是否需要调用下一个 Server，以此来完成整个任务。

### LLM

> tips：应该能对输入结果进行快速反应得到结果



### Observation

> tips：建立一个合适的反馈机制，实现LLM的调优和快速输出







