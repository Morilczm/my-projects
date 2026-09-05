Page({
  data: {
    expandedId: ''
  },

  onLoad: function() {
    wx.setNavigationBarTitle({
      title: '常见问题'
    });
  },

  toggleFaq: function(e) {
    const id = e.currentTarget.dataset.id;
    if (this.data.expandedId === id) {
      this.setData({ expandedId: '' });
    } else {
      this.setData({ expandedId: id });
    }
  },

  contactService: function() {
    wx.setClipboardData({
      data: 'CampusLife_Service',
      success: function() {
        wx.showToast({
          title: '微信号已复制',
          icon: 'success'
        });
      }
    });
  },

  makePhoneCall: function() {
    wx.makePhoneCall({
      phoneNumber: '010-12345678'
    });
  }
});