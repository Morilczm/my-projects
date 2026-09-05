const http = require("http");
const { URL } = require("url");
const { addClient, removeClient } = require("./events");
const { dispatch, ok, fail } = require("./handlers");

const PORT = Number(process.env.PORT || 3000);
const HOST = process.env.HOST || "0.0.0.0";

const setCorsHeaders = (res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type,X-Openid");
};

const sendJson = (res, statusCode, payload) => {
  setCorsHeaders(res);
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
  });
  res.end(JSON.stringify(payload));
};

const readJsonBody = (req) => new Promise((resolve, reject) => {
  let raw = "";

  req.on("data", (chunk) => {
    raw += chunk;
    if (raw.length > 1024 * 1024) {
      reject(new Error("请求体过大"));
      req.destroy();
    }
  });

  req.on("end", () => {
    if (!raw) {
      resolve({});
      return;
    }

    try {
      resolve(JSON.parse(raw));
    } catch (err) {
      reject(new Error("请求体不是合法 JSON"));
    }
  });

  req.on("error", reject);
});

const buildContext = (req) => ({
  openid: req.headers["x-openid"] || "",
});

const routeRequest = async (req, res) => {
  setCorsHeaders(res);

  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }

  const url = new URL(req.url, `http://${req.headers.host}`);

  if (req.method === "GET" && url.pathname === "/health") {
    sendJson(res, 200, ok({
      service: "campuslife-server",
      status: "ok",
      time: new Date().toISOString(),
    }));
    return;
  }

  if (req.method === "GET" && url.pathname === "/api/events") {
    setCorsHeaders(res);
    res.writeHead(200, {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });
    addClient(res);
    req.on("close", () => removeClient(res));
    return;
  }

  try {
    if (req.method === "POST" && url.pathname === "/api/campus") {
      const body = await readJsonBody(req);
      if (!body.type) {
        throw new Error("缺少接口类型 type");
      }
      sendJson(res, 200, ok(dispatch(body.type, body.data || {}, buildContext(req))));
      return;
    }

    const restRoutes = {
      "GET /api/orders": ["listOrders", "merchant"],
      "POST /api/orders": ["createOrder"],
      "POST /api/feedbacks": ["submitFeedback"],
      "GET /api/dashboard": ["getDashboard"],
      "GET /api/vehicle": ["getVehicleStatus"],
      "PUT /api/vehicle": ["updateVehicleStatus"],
      "GET /api/messages": ["listMessages"],
      "POST /api/messages": ["createMessage"],
    };

    const route = restRoutes[`${req.method} ${url.pathname}`];
    if (route) {
      const body = req.method === "GET" ? {} : await readJsonBody(req);
      const data = route[1] ? { ...body, role: route[1] } : body;
      sendJson(res, 200, ok(dispatch(route[0], data, buildContext(req))));
      return;
    }

    if (req.method === "PUT" && url.pathname.startsWith("/api/orders/")) {
      const body = await readJsonBody(req);
      const orderId = decodeURIComponent(url.pathname.replace("/api/orders/", ""));
      sendJson(res, 200, ok(dispatch("updateOrderStatus", {
        ...body,
        orderId,
      }, buildContext(req))));
      return;
    }

    sendJson(res, 404, fail(new Error("接口不存在")));
  } catch (err) {
    sendJson(res, 400, fail(err));
  }
};

const server = http.createServer(routeRequest);

server.listen(PORT, HOST, () => {
  console.log(`Campus Life server listening on http://${HOST}:${PORT}`);
});
