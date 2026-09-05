const { callCampusApi } = require("../../utils/cloudApi");

const formatTime = (value) => {
  if (!value) return "";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";

  const month = date.getMonth() + 1;
  const day = date.getDate();
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");

  return `${month}/${day} ${hour}:${minute}`;
};

Page({
  data: {
    role: 'student', // 默认显示学生端
    orders: [],
    dashboard: {
      totalOrders: 0,
      activeOrders: 0,
      feedbacks: 0,
      unitCost: 0.7,
      peakCompletionRate: 92,
      avgDeliveryTime: 8.7,
      exceptionLoss: 210,
    },
    loadingOrders: false,
    loadingDashboard: false,
  },

  onLoad: function () {
    this.loadOrders();
    this.loadDashboard();
  },

  onShow: function () {
    this.loadOrders();
  },

  // 处理身份切换
  switchRole(e) {
    const selectedRole = e.currentTarget.dataset.role;
    if (this.data.role !== selectedRole) {
      this.setData({ role: selectedRole });
      wx.vibrateShort();

      if (selectedRole === "merchant") {
        this.loadDashboard();
        this.loadOrders("merchant");
      } else {
        this.loadOrders("student");
      }
    }
  },

  loadOrders(role = this.data.role) {
    this.setData({ loadingOrders: true });

    callCampusApi("listOrders", { role }).then((data) => {
      const orders = (data.orders || []).map((order) => ({
        ...order,
        createdText: formatTime(order.createdAt),
        routeText: `${order.startPoint} → ${order.endPoint}`,
      }));

      this.setData({ orders });
    }).catch((err) => {
      wx.showToast({
        title: err.message || '订单加载失败',
        icon: 'none'
      });
    }).finally(() => {
      this.setData({ loadingOrders: false });
    });
  },

  loadDashboard() {
    this.setData({ loadingDashboard: true });

    callCampusApi("getDashboard").then((dashboard) => {
      this.setData({ dashboard });
    }).catch((err) => {
      wx.showToast({
        title: err.message || '大屏数据加载失败',
        icon: 'none'
      });
    }).finally(() => {
      this.setData({ loadingDashboard: false });
    });
  }
});
