const { callCampusApi } = require("../../utils/cloudApi");

Page({
  data: {
    bizType: 'receive', // 默认取件
    locations: ['菜鸟驿站', '外卖柜', '雁南园S6', '雁北园', '教学楼中区'],
    startPoint: '',
    endPoint: '',
    senderName: '',
    receiverName: '',
    phone: '',

    // 货物信息
    cargoWeight: '',
    cargoType: '',
    cargoRequire: '',
    cargoRemark: '',

    // AI 推演状态
    isCalculating: false,
    estTime: 0,
    occupancy: 0,
    submitting: false
  },

  // 处理丝滑滑动切换
  switchType(e) {
    const type = e.currentTarget.dataset.type;
    if (this.data.bizType !== type) {
      this.setData({ bizType: type });
      wx.vibrateShort(); // 添加轻微震动反馈
    }
  },

  // 起始点选择
  onStartChange(e) {
    this.setData({ startPoint: this.data.locations[e.detail.value] });
    this.checkAndCalculate();
  },

  // 终点选择
  onEndChange(e) {
    this.setData({ endPoint: this.data.locations[e.detail.value] });
    this.checkAndCalculate();
  },

  // 动态触发 AI 计算动画
  checkAndCalculate() {
    if (this.data.startPoint && this.data.endPoint) {
      if (this.data.startPoint === this.data.endPoint) {
        wx.showToast({ title: '起点和终点不能相同', icon: 'none' });
        return;
      }

      // 开启计算状态，显示加载动画
      this.setData({ isCalculating: true });

      // 模拟 1.2 秒的大模型算法推演时间
      setTimeout(() => {
        this.setData({
          isCalculating: false,
          estTime: 8.7, // 恢复你立项书中的核心降本提速数据
          occupancy: Math.floor(Math.random() * 20) + 30 // 随机模拟 30%-50% 的占用率
        });
      }, 1200);
    }
  },

  inputS(e) {
    this.setData({ senderName: e.detail.value.trim() });
  },

  inputR(e) {
    this.setData({ receiverName: e.detail.value.trim() });
  },

  inputP(e) {
    this.setData({ phone: e.detail.value.trim() });
  },

  onCargoWeightChange(e) {
    this.setData({ cargoWeight: e.detail.value.trim() });
  },

  onCargoTypeChange(e) {
    this.setData({ cargoType: e.detail.value.trim() });
  },

  onCargoRequireChange(e) {
    this.setData({ cargoRequire: e.detail.value.trim() });
  },

  onCargoRemarkChange(e) {
    this.setData({ cargoRemark: e.detail.value.trim() });
  },

  // 提交预约
  submitBooking() {
    const {
      bizType,
      startPoint,
      endPoint,
      senderName,
      receiverName,
      phone,
      cargoWeight,
      cargoType,
      estTime,
      occupancy,
      submitting
    } = this.data;

    if (submitting) return;

    if (!startPoint || !endPoint) {
      wx.showToast({ title: '请先选择路线', icon: 'none' });
      return;
    }

    if (startPoint === endPoint) {
      wx.showToast({ title: '起点和终点不能相同', icon: 'none' });
      return;
    }

    if (!senderName || !receiverName || !phone) {
      wx.showToast({ title: '请完善联系人信息', icon: 'none' });
      return;
    }

    if (!/^1\d{10}$/.test(phone)) {
      wx.showToast({ title: '请输入正确手机号', icon: 'none' });
      return;
    }

    if (!cargoWeight || !cargoType) {
      wx.showToast({ title: '请填写货物信息', icon: 'none' });
      return;
    }

    this.setData({ submitting: true });
    wx.showLoading({ title: '发送指令中...' });

    callCampusApi("createOrder", {
      bizType,
      startPoint,
      endPoint,
      senderName,
      receiverName,
      phone,
      cargoWeight,
      cargoType,
      cargoRequire: this.data.cargoRequire,
      cargoRemark: this.data.cargoRemark,
      estTime: estTime || 8.7,
      occupancy: occupancy || 36,
    }).then((order) => {
      wx.hideLoading();
      wx.showModal({
        title: '智能调度成功',
        content: `订单 ${order.orderNo} 已创建。无人车将在 ${order.estTime} 分钟内抵达。`,
        showCancel: false,
        success: () => {
          wx.navigateTo({
            url: '/pages/orders/orders'
          });
        }
      });
    }).catch((err) => {
      wx.hideLoading();
      wx.showToast({
        title: err.message || '提交失败',
        icon: 'none'
      });
    }).finally(() => {
      this.setData({ submitting: false });
    });
  }
});
