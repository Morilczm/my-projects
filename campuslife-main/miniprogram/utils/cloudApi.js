const callCampusApi = (type, data = {}) => {
  const app = getApp();

  if (!wx.cloud || !app.globalData.cloudReady) {
    return Promise.reject(new Error("云开发尚未初始化"));
  }

  return wx.cloud
    .callFunction({
      name: "quickstartFunctions",
      data: {
        type,
        data,
      },
    })
    .then((res) => {
      const result = res.result || {};
      if (!result.success) {
        throw new Error(result.errMsg || "云函数调用失败");
      }
      return result.data;
    });
};

module.exports = {
  callCampusApi,
};
