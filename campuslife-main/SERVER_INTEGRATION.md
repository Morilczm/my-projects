# Campus Life 服务端接入说明

项目已新增 `server/` 目录，用于处理和分发客户端信息。它可以独立于微信云开发运行，适合课程项目演示、运营端联调，以及后续迁移到真实数据库。

## 启动服务端

```bash
cd server
npm start
```

默认地址：

```text
http://localhost:3000
```

健康检查：

```text
GET /health
```

## 小程序切换方式

默认仍使用微信云函数，不影响现有小程序运行。

如需切换到独立服务端，编辑：

```text
miniprogram/utils/apiConfig.js
```

改成：

```js
module.exports = {
  apiMode: "http",
  baseUrl: "http://127.0.0.1:3000",
};
```

上线时把 `baseUrl` 改为 HTTPS 域名，并在微信公众平台后台配置 request 合法域名。

## 统一接口

小程序现有 `callCampusApi(type, data)` 调用保持不变。独立服务端对应接口：

```text
POST /api/campus
```

请求示例：

```json
{
  "type": "createOrder",
  "data": {
    "bizType": "receive",
    "startPoint": "菜鸟驿站",
    "endPoint": "雁南园S6",
    "senderName": "张三",
    "receiverName": "李四",
    "phone": "13800138000",
    "cargoWeight": "2kg",
    "cargoType": "快递"
  }
}
```

## 已支持能力

- `createOrder`：创建校园配送订单
- `listOrders`：查询订单列表
- `updateOrderStatus`：更新订单状态并推送事件
- `submitFeedback`：提交用户反馈并推送事件
- `getDashboard`：返回运营看板统计
- `getVehicleStatus`：返回无人车状态
- `updateVehicleStatus`：更新无人车状态并推送事件
- `createMessage`：创建系统消息并分发
- `listMessages`：查询消息列表

## REST 与事件流

服务端也提供 REST 接口：

```text
GET    /api/orders
POST   /api/orders
PUT    /api/orders/:orderId
POST   /api/feedbacks
GET    /api/dashboard
GET    /api/vehicle
PUT    /api/vehicle
GET    /api/messages
POST   /api/messages
GET    /api/events
```

`GET /api/events` 是 SSE 事件流。订单、反馈、车辆状态、消息变化时会推送事件，方便后续做运营后台实时刷新。

## 数据存储

当前数据保存到：

```text
server/data/campuslife.json
```

该文件已加入忽略规则，不会提交到仓库。后续要接 MySQL、MongoDB、PostgreSQL 或微信云数据库时，优先替换 `server/src/store.js`。
