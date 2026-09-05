const cloud = require("wx-server-sdk");

cloud.init({
  env: cloud.DYNAMIC_CURRENT_ENV,
});

const db = cloud.database();

const COLLECTIONS = {
  orders: "campus_orders",
  feedbacks: "campus_feedbacks",
  vehicles: "campus_vehicles",
  sales: "sales",
};

const ok = (data = {}) => ({
  success: true,
  data,
});

const fail = (err) => ({
  success: false,
  errMsg: err && err.message ? err.message : String(err),
});

const ensureCollection = async (name) => {
  try {
    await db.createCollection(name);
  } catch (err) {
    const message = err && err.message ? err.message : "";
    const errCode = err && err.errCode ? String(err.errCode) : "";
    const exists =
      message.includes("exists") ||
      message.includes("already") ||
      message.includes("已存在") ||
      errCode.includes("COLLECTION_ALREADY_EXISTS");

    if (!exists) {
      throw err;
    }
  }
};

const getOpenId = async () => {
  const wxContext = cloud.getWXContext();
  return ok({
    openid: wxContext.OPENID,
    appid: wxContext.APPID,
    unionid: wxContext.UNIONID,
  });
};

const getMiniProgramCode = async () => {
  const resp = await cloud.openapi.wxacode.get({
    path: "pages/index/index",
  });
  const upload = await cloud.uploadFile({
    cloudPath: "code.png",
    fileContent: resp.buffer,
  });
  return ok({
    fileID: upload.fileID,
  });
};

const makeOrderNo = () => {
  const tail = Math.random().toString(36).slice(2, 7).toUpperCase();
  return `CL${Date.now()}${tail}`;
};

const getVehicleSnapshot = (occupancy = 36) => ({
  vehicleId: "CY-01",
  vehicleName: "雏雁一号",
  battery: 88,
  latency: 78,
  occupancy,
  status: occupancy > 80 ? "busy" : "idle",
});

const createOrder = async (event) => {
  await ensureCollection(COLLECTIONS.orders);

  const data = event.data || {};
  const wxContext = cloud.getWXContext();
  const requiredFields = ["bizType", "startPoint", "endPoint", "senderName", "receiverName", "phone"];

  for (let i = 0; i < requiredFields.length; i += 1) {
    const field = requiredFields[i];
    if (!data[field]) {
      throw new Error(`缺少必要字段: ${field}`);
    }
  }

  if (!/^1\d{10}$/.test(String(data.phone))) {
    throw new Error("手机号格式不正确");
  }

  const estTime = Number(data.estTime || 8.7);
  const occupancy = Number(data.occupancy || 36);
  const order = {
    openid: wxContext.OPENID,
    orderNo: makeOrderNo(),
    bizType: data.bizType,
    bizTypeText: data.bizType === "send" ? "寄件预订" : "跑腿代取",
    startPoint: data.startPoint,
    endPoint: data.endPoint,
    senderName: data.senderName,
    receiverName: data.receiverName,
    phone: String(data.phone),
    estTime,
    occupancy,
    vehicle: getVehicleSnapshot(occupancy),
    status: "delivering",
    statusText: "配送中",
    statusLogs: [
      { key: "picked", text: "驿站揽件", done: true },
      { key: "planned", text: "AI规划", done: true },
      { key: "delivering", text: "无人车运送", done: true },
    ],
    createdAt: db.serverDate(),
    updatedAt: db.serverDate(),
  };

  const addResult = await db.collection(COLLECTIONS.orders).add({
    data: order,
  });

  return ok({
    _id: addResult._id,
    orderNo: order.orderNo,
    status: order.status,
    statusText: order.statusText,
    estTime: order.estTime,
  });
};

const listOrders = async (event) => {
  await ensureCollection(COLLECTIONS.orders);

  const data = event.data || {};
  const wxContext = cloud.getWXContext();
  let query = db.collection(COLLECTIONS.orders);

  if (data.role !== "merchant") {
    query = query.where({
      openid: wxContext.OPENID,
    });
  }

  const result = await query.orderBy("createdAt", "desc").limit(30).get();
  return ok({
    orders: result.data,
  });
};

const updateOrderStatus = async (event) => {
  await ensureCollection(COLLECTIONS.orders);

  const data = event.data || {};
  if (!data.orderId || !data.status || !data.statusText) {
    throw new Error("缺少订单状态更新参数");
  }

  await db.collection(COLLECTIONS.orders).doc(data.orderId).update({
    data: {
      status: data.status,
      statusText: data.statusText,
      updatedAt: db.serverDate(),
    },
  });

  return ok({
    orderId: data.orderId,
    status: data.status,
    statusText: data.statusText,
  });
};

const submitFeedback = async (event) => {
  await ensureCollection(COLLECTIONS.feedbacks);

  const data = event.data || {};
  const wxContext = cloud.getWXContext();

  if (!data.tag && !data.content) {
    throw new Error("反馈类型和内容不能同时为空");
  }

  const feedback = {
    openid: wxContext.OPENID,
    tag: data.tag || "其他问题",
    content: data.content || "",
    keywords: data.keywords || [],
    status: "pending",
    statusText: "待处理",
    createdAt: db.serverDate(),
  };

  const addResult = await db.collection(COLLECTIONS.feedbacks).add({
    data: feedback,
  });

  return ok({
    _id: addResult._id,
    statusText: feedback.statusText,
  });
};

const getDashboard = async () => {
  await ensureCollection(COLLECTIONS.orders);
  await ensureCollection(COLLECTIONS.feedbacks);

  const ordersCount = await db.collection(COLLECTIONS.orders).count();
  const feedbacksCount = await db.collection(COLLECTIONS.feedbacks).count();
  const activeOrders = await db
    .collection(COLLECTIONS.orders)
    .where({
      status: "delivering",
    })
    .count();

  return ok({
    totalOrders: ordersCount.total,
    activeOrders: activeOrders.total,
    feedbacks: feedbacksCount.total,
    unitCost: 0.7,
    peakCompletionRate: 92,
    avgDeliveryTime: 8.7,
    exceptionLoss: 210,
  });
};

const getVehicleStatus = async () => {
  return ok(getVehicleSnapshot());
};

const createCollection = async () => {
  await ensureCollection(COLLECTIONS.sales);
  const result = await db.collection(COLLECTIONS.sales).limit(1).get();

  if (result.data.length === 0) {
    const samples = [
      { region: "华东", city: "上海", sales: 11 },
      { region: "华东", city: "南京", sales: 11 },
      { region: "华南", city: "广州", sales: 22 },
      { region: "华南", city: "深圳", sales: 22 },
    ];

    for (let i = 0; i < samples.length; i += 1) {
      await db.collection(COLLECTIONS.sales).add({
        data: samples[i],
      });
    }
  }

  return ok({
    message: "create collection success",
  });
};

const selectRecord = async () => {
  await ensureCollection(COLLECTIONS.sales);
  const result = await db.collection(COLLECTIONS.sales).get();
  return ok(result);
};

const updateRecord = async (event) => {
  const data = event.data || [];
  for (let i = 0; i < data.length; i += 1) {
    await db.collection(COLLECTIONS.sales).doc(data[i]._id).update({
      data: {
        sales: data[i].sales,
      },
    });
  }
  return ok(data);
};

const insertRecord = async (event) => {
  const insertData = event.data || {};
  await ensureCollection(COLLECTIONS.sales);
  await db.collection(COLLECTIONS.sales).add({
    data: {
      region: insertData.region,
      city: insertData.city,
      sales: Number(insertData.sales),
    },
  });
  return ok(insertData);
};

const deleteRecord = async (event) => {
  const data = event.data || {};
  await db.collection(COLLECTIONS.sales).doc(data._id).remove();
  return ok();
};

exports.main = async (event) => {
  try {
    switch (event.type) {
      case "getOpenId":
        return await getOpenId();
      case "getMiniProgramCode":
        return await getMiniProgramCode();
      case "createOrder":
        return await createOrder(event);
      case "listOrders":
        return await listOrders(event);
      case "updateOrderStatus":
        return await updateOrderStatus(event);
      case "submitFeedback":
        return await submitFeedback(event);
      case "getDashboard":
        return await getDashboard();
      case "getVehicleStatus":
        return await getVehicleStatus();
      case "createCollection":
        return await createCollection();
      case "selectRecord":
        return await selectRecord();
      case "updateRecord":
        return await updateRecord(event);
      case "insertRecord":
        return await insertRecord(event);
      case "deleteRecord":
        return await deleteRecord(event);
      default:
        throw new Error(`未知接口类型: ${event.type}`);
    }
  } catch (err) {
    return fail(err);
  }
};
