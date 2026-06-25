window.handleZhengPianClick = async function(payload) {
  // 走后端同源代理，避免浏览器 CORS 拦截 AWS
  const api = (window.API_BASE || '') + '/api/zheng-pian';
  const viewerUrl = "viewer_host.html";

  if (typeof convertTraditionalToSimplified === "function") {
    payload = convertTraditionalToSimplified(payload);
  }

  console.log("📨 发送到后端的 message（简体）:", payload);

  const newTab = window.open(viewerUrl, "_blank");

  if (!newTab) {
    alert("⚠️ 浏览器拦截了弹窗，请启用弹窗");
    return;
  }

  window._zheng_pian_tab_context = {
    targetWindow: newTab,
    content: null
  };

  function deliverContent(content) {
    window._zheng_pian_tab_context.content = content;
    const win = window._zheng_pian_tab_context.targetWindow;
    if (win && !win.closed) {
      try {
        win.postMessage({ type: "zheng-pian-content", content }, "*");
      } catch (e) {
        console.warn("postMessage to viewer failed", e);
      }
    }
  }

  try {
    const response = await fetch(api, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: payload })
    });

    const raw = await response.text();
    let content = raw;

    try {
      const parsed = JSON.parse(raw);

      if (parsed?.error) {
        content = `<div style="text-align:center; padding:2rem; font-size:1.2rem; color:#888;">
          抱歉，暂时未找到本篇信息。
        </div>`;
      } else if (parsed?.data?.response) {
        content = parsed.data.response;
        if (typeof content === "string" && content.startsWith('"') && content.endsWith('"')) {
          content = content.slice(1, -1);
        }
      }
    } catch {
      console.warn("⚠️ JSON 解析失败，使用原始响应");
    }

    deliverContent(content);

  } catch (err) {
    console.error("❌ 请求失败", err);
    deliverContent(`<div style="text-align:center; padding:2rem; font-size:1.2rem; color:#888;">
      网络请求失败，请检查后端是否已启动。
    </div>`);
  }
};
