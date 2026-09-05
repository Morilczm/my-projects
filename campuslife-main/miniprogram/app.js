// app.js
const { envList } = require("./envList");

App({
  onLaunch: function () {
    this.globalData = {
      env: envList[0] && envList[0].envId ? envList[0].envId : "",
      cloudReady: false,
    };

    if (!wx.cloud) {
      console.error("请使用 2.2.3 或以上的基础库以使用云能力");
    } else {
      const cloudConfig = {
        traceUser: true,
      };

      if (this.globalData.env) {
        cloudConfig.env = this.globalData.env;
      }

      wx.cloud.init(cloudConfig);
      this.globalData.cloudReady = true;
    }
  },
});
