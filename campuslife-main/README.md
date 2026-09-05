# Campus Life

Campus Life 是一个面向校园场景的微信小程序原型，围绕校园无人车配送、跑腿代取、订单追踪和用户反馈构建基础业务闭环。

项目当前已接入微信云开发，支持预约创建订单、订单云端存储、订单列表读取、反馈提交和运营数据统计。

## 功能模块

- 首页看板
  - 展示 Campus Life 入口、系统延迟、大模型预测、无人车实时路径监控等信息。

- 配送预订
  - 支持寄件预订和跑腿代取两种业务。
  - 可选择起点、终点，填写联系人信息。
  - 提交后通过云函数创建订单并写入云数据库。

- 订单查询
  - 学生视图读取当前用户订单。
  - 运营视图展示订单数量、配送中订单、用户反馈和核心效益数据。

- 需求反馈
  - 支持选择反馈类型、填写反馈内容。
  - 前端模拟 AI 关键词提取。
  - 提交后写入云数据库。

## 项目结构

```text
cloudfunctions/
  quickstartFunctions/   # 云函数统一入口

miniprogram/
  pages/
    index/               # 首页
    booking/             # 配送预订
    orders/              # 订单查询和运营数据
    feedback/            # 用户反馈
  utils/
    cloudApi.js          # 前端云函数调用封装
  envList.js             # 云开发环境配置
```

## 云函数接口

云函数名称：`quickstartFunctions`

已实现接口：

- `createOrder`：创建校园配送订单，写入 `campus_orders`
- `listOrders`：读取学生订单或运营端订单列表
- `updateOrderStatus`：更新订单状态
- `submitFeedback`：提交用户反馈，写入 `campus_feedbacks`
- `getDashboard`：读取运营数据大屏统计
- `getVehicleStatus`：读取无人车状态快照

## 云数据库集合

首次调用云函数时会自动尝试创建：

- `campus_orders`
- `campus_feedbacks`
- `sales`

## 使用方式

1. 使用微信开发者工具打开本项目。
2. 开通或选择微信云开发环境。
3. 在 `miniprogram/envList.js` 中填写云环境 ID：

   ```js
   envId: "你的云环境ID"
   ```

4. 在微信开发者工具中右键 `cloudfunctions/quickstartFunctions`。
5. 选择“上传并部署：云端安装依赖”。
6. 重新编译小程序。

## 本次云端接入说明

详细变更见：

[CAMPUS_LIFE_CLOUD_UPDATE.md](./CAMPUS_LIFE_CLOUD_UPDATE.md)

## 当前状态

已完成：

- 微信云开发初始化
- 云函数统一接口
- 预约创建订单
- 订单云端存储和读取
- 用户反馈云端提交
- 运营数据统计
- 基础表单校验

可继续完善：

- 用户登录和角色权限
- 真实地图路线
- 订单取消、完成、异常处理
- 微信订阅消息通知
- 运营端订单管理
- 真实无人车状态接口
- 手机号授权和隐私协议
