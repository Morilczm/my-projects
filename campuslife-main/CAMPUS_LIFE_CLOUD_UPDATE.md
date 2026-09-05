# Campus Life 本次云端接入说明

## 本次新增内容

本次为 Campus Life 小程序补齐了数据库和云函数接口，让原本偏展示型的原型具备基础业务闭环。

## 新增和修改的核心文件

- `miniprogram/app.js`
  - 开启微信云开发初始化。
  - 支持从 `envList.js` 读取云环境 ID。

- `miniprogram/envList.js`
  - 增加云开发环境配置入口。
  - 使用前需要把微信云开发环境 ID 填入 `envId`。

- `miniprogram/utils/cloudApi.js`
  - 新增前端统一云函数调用封装。
  - 页面统一通过 `callCampusApi(type, data)` 调用云函数。

- `cloudfunctions/quickstartFunctions/index.js`
  - 新增 Campus Life 业务接口。
  - 保留原微信云开发 quickstart 示例接口兼容。

- `miniprogram/pages/booking/booking.js`
  - 配送预约页接入真实云函数。
  - 提交预约后创建订单，并写入云数据库。
  - 增加姓名、联系人、手机号、路线等基础校验。

- `miniprogram/pages/orders/orders.js`
  - 订单页从云数据库读取订单。
  - 运营数据大屏从云函数读取统计数据。

- `miniprogram/pages/feedback/feedback.js`
  - 反馈页提交后写入云数据库。
  - 保留原有 AI 关键词模拟分析效果。

## 云函数接口

云函数名称：`quickstartFunctions`

已新增接口：

- `createOrder`
  - 创建校园配送订单。
  - 写入集合：`campus_orders`

- `listOrders`
  - 查询订单列表。
  - 学生端默认只查询当前用户订单。
  - 运营端可查询订单列表。

- `updateOrderStatus`
  - 更新订单状态。

- `submitFeedback`
  - 提交用户反馈。
  - 写入集合：`campus_feedbacks`

- `getDashboard`
  - 获取运营数据大屏统计。
  - 包括累计订单、配送中订单、反馈数量、配送成本、完成率等。

- `getVehicleStatus`
  - 获取无人车状态快照。

## 云数据库集合

首次调用云函数时会自动尝试创建以下集合：

- `campus_orders`
  - 存储配送预约订单。

- `campus_feedbacks`
  - 存储用户反馈。

- `sales`
  - 保留原 quickstart 示例集合。

## 使用前需要做的事

1. 用微信开发者工具打开项目：
   `C:\Users\Lenovo\WeChatProjects\miniprogram-2`

2. 开通或选择一个微信云开发环境。

3. 打开文件：
   `miniprogram/envList.js`

4. 把云环境 ID 填入：

   ```js
   envId: "你的云环境ID"
   ```

5. 在微信开发者工具中右键：
   `cloudfunctions/quickstartFunctions`

6. 选择：
   “上传并部署：云端安装依赖”

7. 重新编译小程序，测试流程：
   - 进入配送预订页。
   - 选择起点和终点。
   - 填写姓名、对方姓名、手机号。
   - 提交预约。
   - 进入订单页查看新订单。
   - 进入反馈页提交反馈。
   - 切换订单页运营数据大屏查看统计。

## 当前实现状态

已经完成：

- 预约创建订单
- 订单云端存储
- 订单列表读取
- 反馈云端提交
- 运营数据统计
- 基础表单校验
- 云函数统一入口

仍可继续完善：

- 用户登录和角色权限
- 真实地图路线
- 订单取消、完成、异常处理
- 微信订阅消息通知
- 运营端订单管理操作
- 真实无人车状态接口
- 手机号授权和隐私协议
