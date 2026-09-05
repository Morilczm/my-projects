# Campus Life Server

这是给 Campus Life 小程序新增的独立服务端，用于处理和分发客户端信息。它保留了小程序现有云函数的 `type + data` 调用模型，也提供 REST 接口和 SSE 事件流，便于后续接入运营端、管理后台或真实数据库。

## 启动

```bash
cd server
npm start
```

默认地址：

```text
http://localhost:3000
```

健康检查：

```bash
curl http://localhost:3000/health
```

## 小程序接入

编辑 `miniprogram/utils/apiConfig.js`：

```js
module.exports = {
  apiMode: "http",
  baseUrl: "http://127.0.0.1:3000",
};
```

上线时把 `baseUrl` 改成 HTTPS 域名，并在微信公众平台后台配置 request 合法域名。

## 兼容接口

统一入口：

```http
POST /api/campus
Content-Type: application/json

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

已支持的 `type`：

- `createOrder`：创建订单
- `listOrders`：查询订单
- `updateOrderStatus`：更新订单状态
- `submitFeedback`：提交反馈
- `getDashboard`：运营看板
- `getVehicleStatus`：无人车状态
- `updateVehicleStatus`：更新无人车状态
- `createMessage`：创建待分发消息
- `listMessages`：查询消息

## REST 接口

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

`/api/events` 是 Server-Sent Events 事件流。创建订单、提交反馈、更新车辆状态、创建消息时，服务端会推送事件，方便运营端实时刷新。

## 数据存储

当前为了方便课程项目演示，数据落在：

```text
server/data/campuslife.json
```

这个文件已被 `.gitignore` 忽略。后续可以把 `server/src/store.js` 替换成 MySQL、MongoDB、PostgreSQL 或微信云数据库实现，业务处理层不用大改。
