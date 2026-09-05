const { readState, updateState } = require("./store");
const { broadcast } = require("./events");

const ok = (data = {}) => ({
  success: true,
  data,
});

const fail = (err) => ({
  success: false,
  errMsg: err && err.message ? err.message : String(err),
});

const makeId = (prefix) => `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

const makeOrderNo = () => {
  const tail = Math.random().toString(36).slice(2, 7).toUpperCase();
  return `CL${Date.now()}${tail}`;
};

const getVehicleSnapshot = (occupancy = 36) => {
  const state = readState();
  return {
    ...state.vehicle,
    occupancy,
    status: occupancy > 80 ? "busy" : state.vehicle.status || "idle",
    updatedAt: new Date().toISOString(),
  };
};

const assertText = (data, field, label = field) => {
  if (!data[field] || !String(data[field]).trim()) {
    throw new Error(`缺少必要字段: ${label}`);
  }
};

const createOrder = (data = {}, context = {}) => {
  ["bizType", "startPoint", "endPoint", "senderName", "receiverName", "phone"].forEach((field) => {
    assertText(data, field);
  });

  if (data.startPoint === data.endPoint) {
    throw new Error("起点和终点不能相同");
  }

  if (!/^1\d{10}$/.test(String(data.phone))) {
    throw new Error("手机号格式不正确");
  }

  const now = new Date().toISOString();
  const occupancy = Number(data.occupancy || 36);
  const order = {
    _id: makeId("order"),
    openid: context.openid || data.openid || "anonymous",
    orderNo: makeOrderNo(),
    bizType: data.bizType,
    bizTypeText: data.bizType === "send" ? "寄件预约" : "跑腿代取",
    startPoint: data.startPoint,
    endPoint: data.endPoint,
    senderName: data.senderName,
    receiverName: data.receiverName,
    phone: String(data.phone),
    cargoWeight: data.cargoWeight || "",
    cargoType: data.cargoType || "",
    cargoRequire: data.cargoRequire || "",
    cargoRemark: data.cargoRemark || "",
    estTime: Number(data.estTime || 8.7),
    occupancy,
    vehicle: getVehicleSnapshot(occupancy),
    status: "delivering",
    statusText: "配送中",
    statusLogs: [
      { key: "picked", text: "驿站揽件", done: true },
      { key: "planned", text: "AI规划", done: true },
      { key: "delivering", text: "无人车运送", done: true },
    ],
    createdAt: now,
    updatedAt: now,
  };

  updateState((state) => {
    state.orders.unshift(order);
    return state;
  });

  broadcast("order.created", order);

  return {
    _id: order._id,
    orderNo: order.orderNo,
    status: order.status,
    statusText: order.statusText,
    estTime: order.estTime,
  };
};

const listOrders = (data = {}, context = {}) => {
  const state = readState();
  let orders = state.orders;

  if (data.role !== "merchant") {
    const openid = context.openid || data.openid || "anonymous";
    orders = orders.filter((order) => order.openid === openid);
  }

  return {
    orders: orders.slice(0, 30),
  };
};

const updateOrderStatus = (data = {}) => {
  assertText(data, "orderId", "订单 ID");
  assertText(data, "status", "订单状态");
  assertText(data, "statusText", "订单状态文案");

  let updatedOrder = null;
  updateState((state) => {
    state.orders = state.orders.map((order) => {
      if (order._id !== data.orderId && order.orderNo !== data.orderId) {
        return order;
      }

      updatedOrder = {
        ...order,
        status: data.status,
        statusText: data.statusText,
        updatedAt: new Date().toISOString(),
      };
      return updatedOrder;
    });
    return state;
  });

  if (!updatedOrder) {
    throw new Error("订单不存在");
  }

  broadcast("order.updated", updatedOrder);

  return {
    orderId: updatedOrder._id,
    status: updatedOrder.status,
    statusText: updatedOrder.statusText,
  };
};

const submitFeedback = (data = {}, context = {}) => {
  if (!data.tag && !data.content) {
    throw new Error("反馈类型和内容不能同时为空");
  }

  const feedback = {
    _id: makeId("feedback"),
    openid: context.openid || data.openid || "anonymous",
    tag: data.tag || "其他问题",
    content: data.content || "",
    keywords: Array.isArray(data.keywords) ? data.keywords : [],
    status: "pending",
    statusText: "待处理",
    createdAt: new Date().toISOString(),
  };

  updateState((state) => {
    state.feedbacks.unshift(feedback);
    return state;
  });

  broadcast("feedback.created", feedback);

  return {
    _id: feedback._id,
    statusText: feedback.statusText,
  };
};

const getDashboard = () => {
  const state = readState();
  const activeOrders = state.orders.filter((order) => order.status === "delivering");

  return {
    totalOrders: state.orders.length,
    activeOrders: activeOrders.length,
    feedbacks: state.feedbacks.length,
    unitCost: 0.7,
    peakCompletionRate: 92,
    avgDeliveryTime: 8.7,
    exceptionLoss: 210,
  };
};

const getVehicleStatus = () => getVehicleSnapshot();

const updateVehicleStatus = (data = {}) => {
  const now = new Date().toISOString();
  const vehicle = {
    ...getVehicleSnapshot(data.occupancy),
    ...data,
    updatedAt: now,
  };

  updateState((state) => {
    state.vehicle = vehicle;
    return state;
  });

  broadcast("vehicle.updated", vehicle);
  return vehicle;
};

const createMessage = (data = {}, context = {}) => {
  assertText(data, "title", "消息标题");
  assertText(data, "content", "消息内容");

  const message = {
    _id: makeId("message"),
    openid: context.openid || data.openid || "",
    audience: data.audience || "all",
    channel: data.channel || "system",
    title: String(data.title).trim(),
    content: String(data.content).trim(),
    level: data.level || "info",
    read: false,
    createdAt: new Date().toISOString(),
  };

  updateState((state) => {
    state.messages.unshift(message);
    return state;
  });

  broadcast("message.created", message);
  return message;
};

const listMessages = (data = {}, context = {}) => {
  const state = readState();
  const openid = context.openid || data.openid || "anonymous";

  const messages = state.messages.filter((message) => (
    message.audience === "all" || message.openid === openid || data.role === "merchant"
  ));

  return {
    messages: messages.slice(0, 50),
  };
};

const dispatch = (type, data, context = {}) => {
  switch (type) {
    case "createOrder":
      return createOrder(data, context);
    case "listOrders":
      return listOrders(data, context);
    case "updateOrderStatus":
      return updateOrderStatus(data, context);
    case "submitFeedback":
      return submitFeedback(data, context);
    case "getDashboard":
      return getDashboard(data, context);
    case "getVehicleStatus":
      return getVehicleStatus(data, context);
    case "updateVehicleStatus":
      return updateVehicleStatus(data, context);
    case "createMessage":
      return createMessage(data, context);
    case "listMessages":
      return listMessages(data, context);
    default:
      throw new Error(`未知接口类型: ${type}`);
  }
};

module.exports = {
  ok,
  fail,
  dispatch,
};
