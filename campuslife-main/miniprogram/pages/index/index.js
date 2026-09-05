Page({
  data: {
    latency: 78,
    battery: 88,
    speed: 5,
    direction: '静止',
    eta: 8.7,
    progressPercent: 0,
    timer: null,
    currentLocationName: '南门',
    startPoint: '南门',
    endPoint: '风味餐厅',

    scrollLeft: 0,
    scrollTop: 0,
    mapScale: 1.5,

    mapWidth: 750,
    mapHeight: 500,

    carPosition: {
      x: 58,
      y: 85
    },
    carRotation: 0,

    routePoints: [
      { x: 58, y: 85, name: '南门' },
      { x: 58, y: 68, name: '公共教学楼' },
      { x: 58, y: 52, name: '鸿雁路' },
      { x: 45, y: 52, name: '学生活动中心' },
      { x: 35, y: 52, name: '学生公寓C' },
      { x: 35, y: 42, name: '学生公寓B' },
      { x: 35, y: 32, name: '学生公寓D' },
      { x: 45, y: 32, name: '风味餐厅' }
    ],

    currentRouteIndex: 0,
    targetRouteIndex: 1,

    moveTimer: null,
    interpolationSteps: 25,
    currentStep: 0,

    startX: 58,
    startY: 85,
    endX: 58,
    endY: 68,

    movePhase: 'horizontal',
    targetX: 58,
    targetY: 68,

    routeLineWidth: 0,
    routeLineHeight: 0,
    routeLineLeft: 58,
    routeLineTop: 68,

    isUserScrolling: false,
    scrollLockTimer: null,

    showDeliveryToast: false,
    deliveryTime: '',

    weatherIcon: '☀️',
    weatherText: '晴 26°C',
    speedStatus: '适中',

    cargoWeight: '2.5kg',
    cargoType: '快递包裹',
    cargoRequire: '轻拿轻放',
    cargoRemark: '请放至宿舍门口置物架上',

    pickupCode: ''
  },

  onLoad: function () {
    this.generatePickupCode();
    this.centerMapOnCar();
    this.startLiveSimulation();
  },

  onUnload: function () {
    if (this.data.timer) {
      clearInterval(this.data.timer);
    }
    if (this.data.moveTimer) {
      clearInterval(this.data.moveTimer);
    }
    if (this.data.scrollLockTimer) {
      clearTimeout(this.data.scrollLockTimer);
    }
  },

  centerMapOnCar: function () {
    const carX = this.data.carPosition.x;
    const carY = this.data.carPosition.y;
    const containerWidth = 375;
    const containerHeight = 250;
    const mapWidth = this.data.mapWidth * this.data.mapScale;
    const mapHeight = this.data.mapHeight * this.data.mapScale;

    const carPixelX = (carX / 100) * mapWidth;
    const carPixelY = (carY / 100) * mapHeight;

    let newScrollLeft = carPixelX - containerWidth / 2;
    let newScrollTop = carPixelY - containerHeight / 2;

    newScrollLeft = Math.max(0, Math.min(newScrollLeft, mapWidth - containerWidth));
    newScrollTop = Math.max(0, Math.min(newScrollTop, mapHeight - containerHeight));

    this.setData({
      scrollLeft: newScrollLeft,
      scrollTop: newScrollTop
    });
  },

  startLiveSimulation: function () {
    const firstPoint = this.data.routePoints[0];
    const secondPoint = this.data.routePoints[1];

    this.setData({
      startX: firstPoint.x,
      startY: firstPoint.y,
      endX: secondPoint.x,
      endY: secondPoint.y,
      carPosition: { x: firstPoint.x, y: firstPoint.y }
    });

    this.updateRouteLine();
    this.startInterpolation();

    const timer = setInterval(() => {
      this.simulateDataUpdate();
    }, 3000);

    this.setData({ timer: timer });
  },

  simulateDataUpdate: function () {
    let newLatency = Math.floor(Math.random() * 40) + 60;
    let newBattery = this.data.battery - (Math.random() * 2 + 1);
    let newEta = this.data.eta - 0.5;
    let newProgress = this.data.progressPercent + 12.5;

    if (newBattery < 20) newBattery = 100;
    if (newEta < 0) newEta = 8.7;
    if (newProgress > 100) newProgress = 0;

    this.setData({
      latency: newLatency,
      battery: Math.floor(newBattery),
      eta: newEta.toFixed(1),
      progressPercent: newProgress
    });
  },

  startInterpolation: function () {
    if (this.data.moveTimer) {
      clearInterval(this.data.moveTimer);
    }

    const startX = this.data.startX;
    const startY = this.data.startY;
    const endX = this.data.endX;
    const endY = this.data.endY;
    const steps = this.data.interpolationSteps;

    const isHorizontalFirst = Math.abs(endX - startX) > Math.abs(endY - startY);

    let currentStep = 0;
    let direction = '';

    if (isHorizontalFirst) {
      if (endX > startX) direction = '向东';
      else if (endX < startX) direction = '向西';
      this.setData({
        targetX: endX,
        targetY: startY,
        movePhase: 'horizontal',
        direction: direction
      });
    } else {
      if (endY > startY) direction = '向南';
      else if (endY < startY) direction = '向北';
      this.setData({
        targetX: startX,
        targetY: endY,
        movePhase: 'vertical',
        direction: direction
      });
    }

    const moveTimer = setInterval(() => {
      currentStep++;

      let currentX, currentY, progress;

      if (isHorizontalFirst) {
        if (currentStep <= steps) {
          progress = currentStep / steps;
          currentX = startX + (this.data.targetX - startX) * this.easeInOutQuad(progress);
          currentY = startY;
        } else {
          const remainingSteps = currentStep - steps;
          const phase2Steps = steps;
          progress = remainingSteps / phase2Steps;
          currentX = this.data.targetX;
          currentY = this.data.targetY + (endY - this.data.targetY) * this.easeInOutQuad(progress);

          if (remainingSteps >= phase2Steps) {
            this.setData({ direction: (endY > this.data.targetY) ? '向南' : '向北' });
          }
        }
      } else {
        if (currentStep <= steps) {
          progress = currentStep / steps;
          currentX = startX;
          currentY = startY + (this.data.targetY - startY) * this.easeInOutQuad(progress);
        } else {
          const remainingSteps = currentStep - steps;
          const phase2Steps = steps;
          progress = remainingSteps / phase2Steps;
          currentX = this.data.targetX + (endX - this.data.targetX) * this.easeInOutQuad(progress);
          currentY = this.data.targetY;

          if (remainingSteps >= phase2Steps) {
            this.setData({ direction: (endX > this.data.targetX) ? '向东' : '向西' });
          }
        }
      }

      this.setData({
        carPosition: { x: currentX, y: currentY },
        currentStep: currentStep
      });

      if (currentStep >= steps * 2) {
        clearInterval(moveTimer);
        this.setData({ moveTimer: null });
        this.moveToNextPoint();
      }
    }, 120);

    this.setData({ moveTimer: moveTimer });
  },

  easeInOutQuad: function (t) {
    return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
  },

  moveToNextPoint: function () {
    let nextIndex = this.data.targetRouteIndex + 1;

    if (nextIndex >= this.data.routePoints.length) {
      nextIndex = 0;
      this.setData({ progressPercent: 0 });
      this.showDeliveryNotification();
    }

    const currentPoint = this.data.routePoints[this.data.targetRouteIndex];
    const nextPoint = this.data.routePoints[nextIndex];

    const newSpeed = Math.floor(Math.random() * 3 + 5);
    let speedStatus = '适中';
    if (newSpeed >= 7) speedStatus = '良好';
    else if (newSpeed <= 4) speedStatus = '较慢';

    this.setData({
      currentRouteIndex: this.data.targetRouteIndex,
      targetRouteIndex: nextIndex,
      startX: currentPoint.x,
      startY: currentPoint.y,
      endX: nextPoint.x,
      endY: nextPoint.y,
      currentLocationName: nextPoint.name,
      speed: newSpeed,
      speedStatus: speedStatus
    });

    this.updateRouteLine();
    this.startInterpolation();

    if (!this.data.isUserScrolling) {
      this.centerMapOnCar();
    }
  },

  generatePickupCode: function () {
    const code = Math.floor(100000 + Math.random() * 900000).toString();
    this.setData({ pickupCode: code });
  },

  showDeliveryNotification: function () {
    this.generatePickupCode();

    const now = new Date();
    const hours = now.getHours().toString().padStart(2, '0');
    const minutes = now.getMinutes().toString().padStart(2, '0');
    const seconds = now.getSeconds().toString().padStart(2, '0');
    const timeStr = `${hours}:${minutes}:${seconds}`;

    this.setData({
      showDeliveryToast: true,
      deliveryTime: timeStr
    });

    setTimeout(() => {
      this.setData({ showDeliveryToast: false });
    }, 5000);
  },

  hideDeliveryToast: function () {
    this.setData({ showDeliveryToast: false });
  },

  updateRouteLine: function () {
    const points = this.data.routePoints;
    let minX = 100, maxX = 0, minY = 100, maxY = 0;

    for (let i = this.data.currentRouteIndex; i <= this.data.targetRouteIndex; i++) {
      const p = points[i];
      minX = Math.min(minX, p.x);
      maxX = Math.max(maxX, p.x);
      minY = Math.min(minY, p.y);
      maxY = Math.max(maxY, p.y);
    }

    let width = maxX - minX;
    let height = maxY - minY;

    if (width < 2) width = 2;
    if (height < 2) height = 2;

    this.setData({
      routeLineLeft: minX,
      routeLineTop: minY,
      routeLineWidth: width,
      routeLineHeight: height
    });
  },

  onMapScroll: function (e) {
    if (e.detail.scrollLeft !== this.data.scrollLeft || e.detail.scrollTop !== this.data.scrollTop) {
      this.setData({
        scrollLeft: e.detail.scrollLeft,
        scrollTop: e.detail.scrollTop,
        isUserScrolling: true
      });

      if (this.data.scrollLockTimer) {
        clearTimeout(this.data.scrollLockTimer);
      }

      const timer = setTimeout(() => {
        this.setData({
          isUserScrolling: false,
          scrollLockTimer: null
        });
      }, 5000);

      this.setData({ scrollLockTimer: timer });
    }
  },

  navTo: function (e) {
    const url = e.currentTarget.dataset.url;
    wx.navigateTo({
      url: url
    });
  },

  copyWechat: function () {
    wx.setClipboardData({
      data: 'CampusLife_Service',
      success: function () {
        wx.showToast({
          title: '微信号已复制',
          icon: 'success'
        });
      }
    });
  },

  makePhoneCall: function () {
    wx.makePhoneCall({
      phoneNumber: '010-12345678'
    });
  },

  showFAQ: function () {
    wx.navigateTo({
      url: '/pages/faq/faq'
    });
  },

  showServiceTime: function () {
    wx.showModal({
      title: '服务时间',
      content: '工作日：08:00 - 22:00\n周末：09:00 - 21:00\n节假日：10:00 - 20:00\n\n紧急情况请拨打客服电话',
      showCancel: false,
      confirmText: '我知道了'
    });
  }
});