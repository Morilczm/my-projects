const { callCampusApi } = require("../../utils/cloudApi");

Page({
  data: {
    tags: ['📦 配送延迟', '🛡️ 包装破损', '🤖 无人车路线', '💡 功能建议', '其他问题'],
    activeTag: '',
    content: '',
    charCount: 0,
    isFocused: false,
    aiKeywords: [], // 模拟 AI 提取的关键词
    submitting: false
  },

  // 1. 标签选择逻辑
  selectTag(e) {
    const selected = e.currentTarget.dataset.tag;
    this.setData({
      activeTag: selected
    });
    wx.vibrateShort(); // 触觉反馈
  },

  // 2. 输入框焦点处理 (用于控制边框发光)
  onFocus() {
    this.setData({ isFocused: true });
  },
  onBlur() {
    this.setData({ isFocused: false });
  },

  // 3. 实时输入监听与 AI 模拟
  onInput(e) {
    const text = e.detail.value;
    
    // 更新字数
    this.setData({
      content: text,
      charCount: text.length
    });

    // 模拟大模型语义分析 (防抖处理，避免频繁触发)
    if (this.timer) clearTimeout(this.timer);
    
    this.timer = setTimeout(() => {
      this.simulateAIAnalysis(text);
    }, 500);
  },

  // 模拟 AI 关键词提取算法
  simulateAIAnalysis(text) {
    let keywords = [];
    if (text.includes('慢') || text.includes('时间') || text.includes('没到')) keywords.push('时效异常');
    if (text.includes('破') || text.includes('坏') || text.includes('湿')) keywords.push('包装破损');
    if (text.includes('雨') || text.includes('雪') || text.includes('天气')) keywords.push('气象应对');
    if (text.includes('赞') || text.includes('好') || text.includes('方便')) keywords.push('正向反馈');

    this.setData({ aiKeywords: keywords });
  },

  // 4. 提交表单
  submitFeedback() {
    if (this.data.submitting) return;

    if (!this.data.activeTag && this.data.content.length === 0) {
      wx.showToast({ title: '请完善反馈内容', icon: 'none' });
      return;
    }

    this.setData({ submitting: true });
    wx.showLoading({ title: '加密上传中...' });

    callCampusApi("submitFeedback", {
      tag: this.data.activeTag,
      content: this.data.content,
      keywords: this.data.aiKeywords
    }).then(() => {
      wx.hideLoading();
      wx.showModal({
        title: '反馈已接收',
        content: '感谢您的建议！数据已同步至雏雁调度中心，我们将持续优化校园物流体验。',
        showCancel: false,
        success: () => {
          // 清空表单
          this.setData({
            activeTag: '',
            content: '',
            charCount: 0,
            aiKeywords: []
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
