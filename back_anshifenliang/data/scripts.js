// ✅ scripts.js — 完整融合版（关键词识别 + 模糊匹配 + 原有功能）
// 📌 原始功能 + sendMessage 插入关键词判断逻辑：
// ✅ 完整版 scripts.js，含禁用发送按钮逻辑、语音识别、多语言、loading 动画等功能

// ✅ 全局语言翻译映射（必须放在顶层）
const translations = {
    "zh-CN": {
        "title": "按时分粮",
        "welcome": "您好！请问有什么可以帮助您的？",
        "input-placeholder": "输入你的问题......",
        "copy": "📋 复制",
        "copied": "✅ 已复制",
        "more": "🔄 更多",
        "view-full": "查看全文",
        "close": "关闭",
        "read": "🔊 朗读", // ✅ 新增
        "loginTitle": "登录",
        "usernamePlaceholder": "用户名",
        "passwordPlaceholder": "密码",
        "loginButton": "登录"
    },
    "zh-TW": {
        "title": "按時分糧",
        "welcome": "您好！請問有什麼可以幫助您的？",
        "input-placeholder": "輸入你的問題……",
        "copy": "📋 複製",
        "copied": "✅ 已複製",
        "more": "🔄 更多",
        "view-full": "查看全文",
        "close": "關閉",
        "read": "🔊 朗讀", // ✅ 新增
        "loginTitle": "登入",
        "usernamePlaceholder": "使用者名稱",
        "passwordPlaceholder": "密碼",
        "loginButton": "登入"     
    }
};

// ✅ 全局语言识别
const userLang = navigator.language || navigator.userLanguage;
const isTraditional = userLang.startsWith("zh-TW") || userLang.startsWith("zh-HK") || userLang.startsWith("zh-MO");
const selectedLang = isTraditional ? "zh-TW" : (translations[userLang] ? userLang : "zh-CN");
window.selectedLang = selectedLang;

/** 检测文本是否含繁体（与转简体后不同即视为繁体输入） */
function isTraditionalText(text) {
    if (!text || typeof text !== 'string') return false;
    if (typeof convertTraditionalToSimplified !== 'function') return false;
    return convertTraditionalToSimplified(text) !== text;
}

/** 是否应以繁体展示结果：用户输入繁体 / 界面语言繁体 */
function shouldDisplayTraditional() {
    if (window.userInputWasTraditional) return true;
    const lang = window.selectedLang || '';
    if (lang === 'zh-TW' || lang.startsWith('zh-HK') || lang.startsWith('zh-MO')) return true;
    const userLang = navigator.language || navigator.userLanguage || '';
    return userLang.startsWith('zh-TW') || userLang.startsWith('zh-HK') || userLang.startsWith('zh-MO');
}

function maybeToTraditional(text) {
    if (!text || !shouldDisplayTraditional()) return text;
    if (typeof convertToTraditional === 'function') return convertToTraditional(text);
    return text;
}

/** 在词典 value 正文中匹配（库内为简体，query 已转简体） */
function matchKeysByValue(keys, getValue, query, expandedQueries, isExcludedFn) {
    const minLen = 2;
    const hits = [];
    const seen = new Set();
    for (const k of keys) {
        if (seen.has(k)) continue;
        const raw = getValue(k);
        const text = typeof raw === 'string' ? raw : (raw && raw.content != null ? String(raw.content) : '');
        if (!text) continue;
        const matched = expandedQueries.some((q) => q.length >= minLen && text.includes(q));
        if (!matched) continue;
        if (isExcludedFn && isExcludedFn(query, k, raw)) continue;
        seen.add(k);
        hits.push(k);
    }
    return hits;
}

/** jing_jie_zhu_shi 目录词（新约/旧约/圣经/目录等）精确匹配 */
function lookupJingJieZhuShiCatalog(query, expandedQueries) {
    const data = window.jing_jie_zhu_shi;
    if (!data || typeof data !== 'object') return null;
    const candidates = [...new Set([query, ...(expandedQueries || [])])].filter(Boolean);
    for (const q of candidates) {
        const content = data[q];
        if (typeof content === 'string' && content.trim()) {
            return { key: q, value: content };
        }
    }
    return null;
}

const history = document.getElementById('history');
const voiceButton = document.getElementById('voice-button');
const userInput = document.getElementById('user-input');
const sendButton = document.getElementById('send-button');

const punctuationMap = {
    ",": "，", ".": "。", "?": "？", "!": "！", ":": "：", ";": "；"
};
const chineseNumbers = "〇一二三四五六七八九十百千万两";

let isUserScrolling = false;

// 监听滚动事件，检测用户手动滚动
const chatHistory = document.querySelector('.history');
chatHistory.addEventListener('scroll', () => {
    // 判断是否接近底部（容差 50px）
    const nearBottom = chatHistory.scrollHeight - chatHistory.scrollTop - chatHistory.clientHeight < 50;
    isUserScrolling = !nearBottom;  // 用户只要不在底部，就是手动滚动了
});

function scrollToBottom(targetMessageDiv = null) {
    const chatHistory = document.querySelector('.history');

    // 如果用户手动滚动了，就不再自动滚动
    if (isUserScrolling) return;

    setTimeout(() => {
        if (targetMessageDiv) {
            // 滚动到当前消息（AI 打字模式）
            const offsetTop = targetMessageDiv.offsetTop + targetMessageDiv.offsetHeight;
            chatHistory.scrollTop = Math.max(offsetTop - chatHistory.clientHeight + 50, 0);
        } else {
            // 否则滚动到底部
            chatHistory.scrollTop = chatHistory.scrollHeight;
        }
    }, 10);
}

let isLoading = true;
let bookTimer = null;

function showLoading() {
    isLoading = true;

    const loadingDiv = document.createElement("div");
    loadingDiv.className = "message bot loading";
    loadingDiv.setAttribute("id", "loading-message");

    loadingDiv.innerHTML = `<div class="avatar">B</div><div class="content"><span class="dots">思考中，请稍等<span class="book-inline"></span></span></div>`;
    history.appendChild(loadingDiv);
    scrollToBottom();

    startBookAnimation();
}

function startBookAnimation() {
    const container = document.querySelector("#loading-message .book-inline");
    if (!container) return;

    container.innerHTML = ""; // 初始清空
    let count = 0;

    if (bookTimer) clearInterval(bookTimer);

    bookTimer = setInterval(() => {
        if (!isLoading) {
            clearInterval(bookTimer);
            return;
        }

        // 超过 7 本书时清空并重置
        if (count >= 7) {
            container.innerHTML = "";
            count = 0;
        }

        const book = document.createElement("span");
        book.className = "book";
        book.textContent = "📖";
        container.appendChild(book);
        count++;
    }, 3000); // 每 3 秒添加一本
}

function removeLoading() {
    isLoading = false;
    clearInterval(bookTimer);
    const loadingDiv = document.getElementById("loading-message");
    if (loadingDiv) history.removeChild(loadingDiv);
}




function wrapChineseQuotesWithFont(message) {
  let quoteIndex = 0;
  let singleQuoteIndex = 0;

  // 内部函数：返回带宋体字体的引号
  function quoteSpan(char) {
    return `<span style="font-family: SimSun;">${char}</span>`;
  }

  message = message
    .replace(/["“”]/g, () => {
      const char = quoteIndex++ % 2 === 0 ? '“' : '”';
      return quoteSpan(char);
    })
    .replace(/['‘’]/g, (match, offset) => {
      const before = message[offset - 1];
      const after = message[offset + 1];
      if (/[A-Za-z0-9]/.test(before) && /[A-Za-z0-9]/.test(after)) {
        return "'"; // 英文缩写保留
      }
      const char = singleQuoteIndex++ % 2 === 0 ? '‘' : '’';
      return quoteSpan(char);
    });

  return message;
}

function arabicToCustomChinese(num) {
    const digitMap = ['〇', '一', '二', '三', '四', '五', '六', '七', '八', '九'];
    
    if (num >= 10 && num < 20) {
        // 10~19
        return '十' + (num % 10 === 0 ? '' : digitMap[num % 10]);
    }

    if (num % 10 === 0 && num < 100) {
        // 整十（20、30...90）
        return digitMap[Math.floor(num / 10)] + '十';
    }

    // 其他按逐位
    return String(num).split('').map(d => digitMap[parseInt(d, 10)]).join('');
}

function cleanFirstLineExtraChar(text) {
    // 检查首行是否只有一个字符并且紧跟换行符
    if (/^[^\n]{1}\n/.test(text)) {
        return text.replace(/^([^\n])\n/, '');
    }

    // 检查首行是否是单个字符后跟HTML标记（如 <p>），可扩展正则
    if (/^[^\n]{1}(<[^>]+>)/.test(text)) {
        return text.replace(/^([^\n])(<[^>]+>)/, '$2');
    }

    return text;
}

function formatMessage(message) {

    const debug = true; // ✅ 放在最上面！
    message = message.replace(/^(.+?)\[目录\]$/gm, (match, bookTitle) => {
        const cleanTitle = bookTitle.trim();
        return `<span class="data-title_2">${cleanTitle}</span><button class="view-original show-catalog-btn"data-source="catalog"data-book-key="${cleanTitle}"style="margin-left:10px; color:white; border:none; border-radius:3px; cursor:pointer; font-size:12px;">目录</button>`;
    });    
    const punctuationMap = {
        ",": "，",
        ".": "。",
        "?": "？",
        "!": "！",
        ":": "：",
        ";": "；"
        // 不包含引号，这里单独处理
    };

    const chineseNumbers = "〇一二三四五六七八九十百千万两";

    // === Step 1: 合并 ### 段为逻辑段落 ===
    message = message.split("###").join("\n");

    // Step 2: 引号统一替换为宋体样式
    // message = wrapChineseQuotesWithFont(message); // 暂时关闭中文引号美化

    // === Step 2: 合并第一、第二行 ===
    // let lines = message.split("\n");
    // if (lines.length >= 2) {
    //     lines[0] = lines[0] + lines[1];
    //     lines.splice(1, 1);
    //     message = lines.join("\n");
    // }

    // === Step 4.5: 删除括号中的特定内容（纯数字、数字.数字、源自等） ===
    const parenCleanRules = [
    {
        name: '纯数字括号',
        regex: /[（(](\d+)[）)]/g,
        check: (m) => true
    },
    {
        name: '数字+标点+数字',
        regex: /[（(](\d+(?:\s*(?:~~|[\.\．\-–、,，：:])\s*\d+)*)[）)]/g,
        check: (m) => true
    },
    {
        name: '源自开头',
        regex: /[（(](源自[^）)\n]{1,20})[）)]/g,
        check: (m) => true
    },
    {
        name: '来源开头',
        regex: /[（(](来源[^）)\n]{1,20})[）)]/g,
        check: (m) => true
    },
    {
        name: '源开头',
        regex: /[（(](源[^）)\n]{1,20})[）)]/g,
        check: (m) => true
    },
    {
        name: '参考开头',
        regex: /[（(](参考来源[^）)\n]{1,20})[）)]/g,
    },
    {
        name: '纯文本 source 标签',
        regex: /<source>([^<>]*?)<\/source>/g,
        check: (m) => true
    },
    {
        name: '参考信息来源',
        regex: /[（(](参考信息来源[\d、,，\s]{1,30})[）)]/g,
        check: (m) => true
    },
    {
        name: '参数字',
        regex: /[（(](参[\d、,，\s]{1,20})[）)]/g,
        check: (m) => true
    }
    ];

    for (const rule of parenCleanRules) {
    message = message.replace(rule.regex, (_, match) => {
        if (debug) console.log(`🧹 删除（${rule.name}）内容: ${match}`);
        return '';
    });
    }

    // === Step 5: 替换英文标点为中文标点（不包括引号） ===
    for (const [en, zh] of Object.entries(punctuationMap)) {
        const escaped = en.replace(/([.*+?^=!:${}()|[\]/\\])/g, "\\$1");

        let regex;
        if (en === ".") {
            regex = new RegExp(`(?<![A-Za-z0-9${chineseNumbers}])(?<!\\.)\\.${1}(?!\\.)(?![A-Za-z0-9])`, "g");
        } else {
            regex = new RegExp(`(?<![A-Za-z0-9${chineseNumbers}])${escaped}(?![A-Za-z0-9])`, "g");
        }

        message = message.replace(regex, zh);
    }

    // ✅ 将 [数字]xxx 替换为按钮 + 纯文本（结构包裹+按钮文字居中优化）
    message = message.replace(/\[(\d+)\](.+?)(?=\n|$)/g, (match, num, content) => {
    const cleanText = content
        .replace(/<\/?[^>]+>/g, '')    // 移除 HTML 标签
        .replace(/<\/button>/gi, '')   // 移除错误残留按钮标签
        .replace(/\s+/g, ' ')          // 合并空白字符
        .trim();

    return `<span class="zheng-pian-group"><button class="zheng-pian-btn" data-payload="${cleanText}"><span>${num}</span></button>${cleanText}</span>`;
    });

    // === Step X: 处理多个“重要经节出处：[经节列表]”，删除原段落并插入详细经节内容 ===
    // 先把 [[ 和 ]] 替换为 [
    message = message.replace(/\[\[/g, '[').replace(/\]\]/g, ']');
    message = message.replace(/重要经节出处：\s*\[([^\]\n<]*)\]/g, (match, verseList) => {
        if (!window.bibleVerse) return '';

        verseList = verseList.replace(/([\u4e00-\u9fa5]{1,3}|\w{1,3})(\d{1,3}):(\d+)/g, (m, book, chapter, verse) => {
            const chineseChapter = arabicToCustomChinese(parseInt(chapter, 10));
            return `${book}${chineseChapter}${verse}`;
        });
        
        const parts = verseList.split(/[；;、，,、\s]+/).map(s => s.trim()).filter(Boolean);
        const cleanedParts = parts.map(ref => ref.replace(/(\d+)[上下]$/, '$1'));

        if (debug) {
            console.groupCollapsed(`🔍 正在解析经节出处：${verseList}`);
            console.log("拆分后 parts:", parts);
        }

        const refs = [];
        let currentBook = '';
        let currentChapter = '';

        cleanedParts.forEach(part => {
            // ✅ 处理范围格式：如 弗四22-24 / 林前三1~3
            if (part.includes('-') || part.includes('~') || part.includes('～')) {
                const [startRaw, endRaw] = part.split(/[~～-]/).map(s => s.trim());

                const startMatch = startRaw.match(/^([\u4e00-\u9fa5]{1,3})(\D?)(\d+)$/);
                const endVerse = parseInt(endRaw, 10);

                if (startMatch) {
                    const book = startMatch[1];
                    const chapter = startMatch[2] || currentChapter;
                    const startVerse = parseInt(startMatch[3], 10);

                    currentBook = book;
                    currentChapter = chapter;

                    for (let i = startVerse; i <= endVerse; i++) {
                        refs.push(`${book}${chapter}${i}`);
                    }

                    if (debug) console.log(`🟡 匹配范围（修正）: ${part} → ${book}${chapter}${startVerse}~${endVerse}`);
                    return;
                } else {
                    if (debug) console.warn(`❌ 无法解析范围: ${part}`);
                    refs.push(part);
                    return;
                }
            }

            // ✅ 完整格式：书 + 章 + 节
            const fullMatch = part.match(/^([\u4e00-\u9fa5]{1,3})(\D?)(\d+)$/);
            const partialMatch = part.match(/^(\D?)(\d+)$/);
            const multiVerseMatch = part.match(/^(\D?)(\d+)[、,](\d+)$/);

            if (fullMatch) {
                currentBook = fullMatch[1];
                currentChapter = fullMatch[2];
                refs.push(currentBook + currentChapter + fullMatch[3]);
                if (debug) console.log(`🟢 匹配完整: ${part}`);
            } else if (multiVerseMatch && currentBook) {
                const chapter = multiVerseMatch[1] || currentChapter;
                const verse1 = multiVerseMatch[2];
                const verse2 = multiVerseMatch[3];
                currentChapter = chapter;
                refs.push(currentBook + currentChapter + verse1);
                refs.push(currentBook + currentChapter + verse2);
                if (debug) console.log(`🔵 匹配多节: ${part}`);
            } else if (partialMatch && currentBook) {
                const chapter = partialMatch[1] || currentChapter;
                const verse = partialMatch[2];
                currentChapter = chapter;
                refs.push(currentBook + currentChapter + verse);
                if (debug) console.log(`🟠 匹配部分: ${part}`);
            } else {
                refs.push(part); // fallback
                if (debug) console.warn(`❌ 无法解析（原样保留）: ${part}`);
            }
        });

        if (debug) {
            console.log("✅ 最终生成 refs:", refs);
            console.groupEnd();
        }

        const expanded = refs.map((ref, index) => {
            let content = window.bibleVerse[ref];
            let finalRef = ref;

            if (debug) console.groupCollapsed(`🔍 尝试匹配: ${ref}`);

            let validPrefix = '';
            if (content) {
                validPrefix = ref;
                if (debug) console.log(`✅ 直接匹配成功: ${ref}`);
            } else {
                // 回溯拼接前缀
                for (let i = index - 1; i >= 0; i--) {
                    const prevRef = refs[i];
                    const prevContent = window.bibleVerse[prevRef];
                    if (prevContent) {
                        validPrefix = prevRef;
                        if (debug) console.log(`ℹ️ 使用回溯前缀: ${validPrefix}`);
                        break;
                    }
                }

                // 拼接尝试：前缀 + 当前
                for (let i = 1; i <= 3 && !content && validPrefix; i++) {
                    const prefix = validPrefix.slice(0, i);
                    const candidate = prefix + ref;
                    if (debug) console.log(`➡️ 尝试回溯拼接: ${candidate}`);
                    content = window.bibleVerse[candidate];
                    if (content) {
                        finalRef = candidate;
                        if (debug) console.log(`✅ 回溯匹配成功: ${candidate}`);
                        break;
                    }
                }
            }

            if (debug && !content) console.warn(`❌ 匹配失败: ${ref}`);
            if (debug) console.groupEnd();

            if (content) {
                return `<p style="margin-bottom:4px;"><strong>${finalRef}</strong>　${content}</p>`;
            } else {
                return `<p style="margin-bottom:1px;"></p>`;
            }
        }).join("");

        return expanded;
    });

    // === Step 7: 转换普通 [] 为加粗，不影响 [数字] ===
    message = message.replace(
        /\[(?!\d+\])([^]*?)\]/g,
        `\n<strong data-tag="inline-bold">\[$1\]</strong>`
    );


    // 正则匹配 [大本诗歌第XXX首 诗歌标题]查看全文
    // 1. 先处理带方括号的格式
    message = message.replace(/\[((?:大本诗歌|补充本诗歌|儿童诗歌)第\d+首.*?)　查看全文\]/g, (match, title) => {
        return `<span class="hymn-title" data-title="${title}">${title}</span> <button class="view-original" data-source="hymns" data-title="${title}">查看全文</button>`;
    });

    // 2. 再处理不带方括号的格式，但排除已经处理过的
    const lines = message.split('\n');
    message = lines.map(line => {
        // 如果这行已经包含了按钮，就不再处理
        if (line.includes('class="view-original"')) {
            return line;
        }
        
        // 1. 优先处理诗歌格式（诗歌、补充本诗歌、儿童诗歌）
        if (/((?:诗歌|补充本诗歌|儿童诗歌)(?:第\d+首|附\d+|其他格式).*?)　查看全文/.test(line)) {
            return line.replace(/((?:诗歌|补充本诗歌|儿童诗歌)(?:第\d+首|附\d+|其他格式).*?)　查看全文/g, (match, title) => {
                return `<span class="hymn-title" data-title_3="${title}">${title}</span> <button class="view-original" data-source="hymns" data-title_3="${title}">查看全文</button>`;
            });
        }
        
        // 2. 然后处理章节格式和纲目格式（创世记第一章、创世记第一章纲目等）
        if (/(.*?(?:章|纲目))　查看全文/.test(line)) {
            return line.replace(/(.*?(?:章|纲目))　查看全文/g, (match, title) => {
                return `<span class="hymn-title" data-title_3="${title}">${title}</span> <button class="view-original" data-source="jing_wen_with_index" data-title_3="${title}">查看全文</button>`;
            });
        }
        
        // 3. 如果都不匹配，返回原行
        return line;
    }).join('\n');

    // === Step 8: 高亮“读经：” ===
    message = message.replace(/(读经\s*[:：])/, `\n<strong>$1</strong>`);

    // === Step 8: 高亮“读经：” ===
    message = message.replace(/(壹　)/, `\n<strong>$1</strong>`);

    // === Step 8: 高亮“参考信息：” ===
    message = message.replace(/(参考信息\s*[:：])/, `<strong>$1</strong>`);

    // === Step 9: 分正文和参考信息 ===
    const [beforeRef, afterRef] = message.split(/<strong>参考信息\s*[:：]<\/strong>/);

    // 正文部分：用 <p> 包裹每段，区分普通和加粗段落
    const formattedBefore = beforeRef
    .split(/\n+/)
    .map(line => line.trim())
    .map(line => {
        if (line.startsWith('<p')) return line;
        const textOnly = line.replace(/<[^>]+>/g, '').trim();
        if (!textOnly) return '';
        const hasInlineBold = /<strong\s+data-tag="inline-bold">/.test(line);
        const margin = hasInlineBold ? '5px' : '12px';
        return `<p style="margin-bottom:${margin};">${line}</p>`;
    })
    .filter(Boolean) // 清掉 return '' 的结果
    .join("")
    .replace(/<p style="margin-bottom:[^>]+;">\s*(<[^>]+>\s*)*<\/p>/g, "");


    // 参考信息部分
    let formattedAfter = "";
    if (afterRef !== undefined) {
        formattedAfter = afterRef
            .split(/\n+/)
            .map(line => line.trim())
            .filter(line => line)
            .map(line => `<p>${line}</p>`)
            .join("");

        formattedAfter = `<p><strong>参考信息：</strong></p>` + formattedAfter;
    }

    return (formattedBefore + formattedAfter).trim();
    return cleanFirstLineExtraChar(formatted);
    
}

// 清除html标签
function getPureTextFromHTML(html) {
    // ✅ 替换 </h1> ~ </h6> 为中文省略号
    html = html.replace(/<\/h[1-6]>/gi, "……");

    // ✅ 替换 </span> 为中文省略号
    html = html.replace(/<\/span>/gi, "……");

    // ✅ 替换 <br> 为换行符
    html = html.replace(/<br\s*\/?>/gi, "\n");

    // ✅ 移除“查看全文”按钮（保留文字）
    html = html.replace(/<button[^>]*?view-original[^>]*?>[\s\S]*?<\/button>/gi, "");

    // ✅ 移除其他按钮
    html = html.replace(/<button[^>]*?>[\s\S]*?<\/button>/gi, "");

    // ✅ 提取纯文本
    const tempDiv = document.createElement("div");
    tempDiv.innerHTML = html;

    return tempDiv.textContent.trim();
}
// 消息处理
async function appendMessage(sender, message, originalUserInput = null) {
    if (sender !== '用户') {
        message = maybeToTraditional(message);
    }

    const messageDiv = document.createElement("div");
    messageDiv.className = `message ${sender === "用户" ? "user" : "bot"}`;

    const avatarDiv = document.createElement("div");
    avatarDiv.className = "avatar";
    avatarDiv.textContent = sender === "用户" ? "U" : "B";

    const contentDiv = document.createElement("div");
    contentDiv.className = "content";

    if (sender === "用户") {
        contentDiv.innerHTML = formatMessage(message);
        messageDiv.append(contentDiv, avatarDiv);
        history.appendChild(messageDiv);
        scrollToBottom();
    } else {
        messageDiv.append(avatarDiv, contentDiv);
        history.appendChild(messageDiv);
        scrollToBottom();

        const formattedMessage = formatMessage(message);
        console.log("🧩 格式化后的 HTML 内容：", formattedMessage);

        // ✅ 无动画：直接显示完整内容
        contentDiv.innerHTML = formattedMessage;
        scrollToBottom();

        // ✅ 按钮组逻辑统一
        let buttonGroup = contentDiv.querySelector(".button-group");
        if (!buttonGroup) {
            buttonGroup = document.createElement("div");
            buttonGroup.className = "button-group";
            contentDiv.appendChild(buttonGroup);
        }

        // ✅ 插入复制按钮（内部已避免重复）
        appendCopyButton();

        // ✅ 插入朗读按钮（使用原始格式文本）

        appendReadButtonToMessageContent(contentDiv, formattedMessage); 

        // ✅ 原始内容展开按钮绑定
       
    }
}





// 查询 hymns.js 获取诗歌内容并弹窗显示
function fetchHymnContent(title) {
    console.log("查询诗歌：", title);
    if (!window.hymns) {
        alert("诗歌数据未加载，请检查 hymns.js");
        return;
    }
    
    if (!window.hymns[title]) {
        alert(`未找到诗歌内容：${title}，请检查 hymns.js 是否包含该诗歌`);
        return;
    }
    
    const formattedContent = formatMessage(window.hymns[title]);
    showHymnModal(title, formattedContent);
}

// 模态框1111
// 2. 找到你现有的 showHymnModal 函数（大约在第573行），替换为以下版本：
// 🔧 完整的 showHymnModal 函数
// 🔧 完整的 showHymnModal 函数
function showHymnModal(title, content) {
    const userLang = navigator.language || navigator.userLanguage;
    const isTraditional = userLang.startsWith("zh-TW") || userLang.startsWith("zh-HK") || userLang.startsWith("zh-MO");
    const selectedLang = isTraditional ? "zh-TW" : "zh-CN";

    if (isTraditional && typeof convertToTraditional === "function") {
        content = convertToTraditional(content);
        title = convertToTraditional(title);
    }

    // 🔧 修复：创建唯一的模态框ID，支持多层叠加
    const modalId = `infoModal_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    // 🔧 修复：每次都创建新的模态框元素
    const modal = document.createElement("div");
    modal.id = modalId;
    modal.className = "modal";
    
    // 🔧 修复：计算当前模态框的z-index和层次样式
    const existingModals = document.querySelectorAll('.modal[style*="display: block"]');
    const baseZIndex = 1000;
    const zIndex = baseZIndex + existingModals.length;
    const modalLevel = existingModals.length; // 当前模态框的层级（0为底层）
    
    // ✨ 新增：为每个层级设置不同的高度和顶端距离
    const heightPercentage = 90 - (modalLevel * 2); // 每层递减2%
    const minHeight = 70; // 最小高度不低于70%
    const finalHeight = Math.max(heightPercentage, minHeight);
    
    // ✨ 新增：控制每层距离顶端的距离
    const topDistances = {
        0: '10dvh',  // 第一层：10dvh
        1: '12dvh',  // 第二层：12dvh
        2: '14dvh',  // 第三层：14dvh（如果需要的话）
        3: '16dvh',  // 第四层：16dvh（如果需要的话）
        // 可以根据需要继续添加更多层级
    };
    
    // 获取当前层级的顶端距离，如果没有定义则使用默认值
    const topDistance = topDistances[modalLevel] || `${10 + modalLevel * 2}dvh`;
    
    modal.style.zIndex = zIndex;
    
    // ✨ 新增：为每层模态框设置不同的顶端距离和高度
    if (modalLevel > 0) {
        modal.style.setProperty('--modal-height', `${finalHeight}%`);
        modal.style.setProperty('--modal-top', topDistance);
        modal.classList.add('layered-modal');
    } else {
        // 第一层也设置顶端距离
        modal.style.setProperty('--modal-top', topDistance);
    }
    
    document.body.appendChild(modal);

    // 计算模态框内容的实际高度（减去顶端距离）
    // 原来的代码
    let contentHeight;
    if (modalLevel === 2) {
        // 第三层模态框（modalLevel=2）完全占满视口
        contentHeight = '100vh';
    } else {
        contentHeight = modalLevel > 0 ? `calc(${finalHeight}vh - ${topDistance})` : `calc(88vh - ${topDistance})`;
    }

    // ✅ 检查是否是章节格式，决定是否显示导航按钮
    const isChapterFormat = /第.+章$/.test(title);
    const navigationButtons = isChapterFormat ? `
        <div class="chapter-navigation" style="display: flex; gap: 10px; margin-left: auto;">
            <button onclick="navigateChapter('prev', '${title}')" style="padding: 5px 10px; background: #007cba; color: white; border: none; border-radius: 3px; cursor: pointer;">上一章</button>
            <button onclick="navigateChapter('next', '${title}')" style="padding: 5px 10px; background: #007cba; color: white; border: none; border-radius: 3px; cursor: pointer;">下一章</button>
        </div>
    ` : '';

    // ✅ 修改：移除朗读按钮HTML，稍后通过统一函数添加
    modal.innerHTML = `
        <div class="modal-content" style="
            ${modalLevel === 2 ? 
                'height: 100vh; max-height: 100vh; margin-top: 0;' : 
                `height: ${contentHeight}; max-height: ${contentHeight}; margin-top: ${topDistance};`
            }
        ">
            <div class="modal-header" style="display: flex; align-items: center; justify-content: space-between;">
                <button class="close">${translations[selectedLang]?.close || "关闭"}</button>
                <div style="display: flex; align-items: center; gap: 10px;">
                    ${navigationButtons}
                    <div class="modal-tools">
                        <button class="copy-modal-content">${translations[selectedLang]?.copy || "📋 复制"}</button>
                    </div>
                </div>
            </div>
            <h3 class="modal-title">${title}</h3>
            <div class="modal-body" style="overflow-y: auto; max-height: calc(100% - 120px);">${content}</div>
        </div>`;
    modal.style.display = 'block';

    // ✅ 新增：使用统一函数添加朗读按钮
    const modalBody = modal.querySelector('.modal-body');
    const rawText = modalBody?.innerText || content;
    
    // 找到modal-tools容器
    let modalTools = modal.querySelector('.modal-tools');
    if (!modalTools) {
        modalTools = document.createElement('div');
        modalTools.className = 'modal-tools';
        const headerDiv = modal.querySelector('.modal-header > div:last-child');
        if (headerDiv) {
            headerDiv.appendChild(modalTools);
        }
    }
    
    // 使用统一函数添加朗读按钮
    appendReadButtonToMessageContent(modalTools, content); 

    // 🔧 修复：关闭函数只关闭当前模态框，并恢复下层模态框的高度和位置
    function closeCurrentModal() {
        console.log(`🔒 关闭模态框 ${modalId}`);
        
        // ✅ 停止当前模态框中所有朗读按钮的音频播放
        const readButtons = modal.querySelectorAll('.read-button');
        readButtons.forEach(btn => {
            // 触发停止事件，让统一朗读函数处理音频清理
            if (btn._audioInstance) {
                btn._audioInstance.pause();
                if (btn._audioUrl) {
                    URL.revokeObjectURL(btn._audioUrl);
                }
                btn._audioInstance = null;
                btn._audioUrl = null;
                btn.textContent = translations[selectedLang]?.read || "🔊 朗读";
                console.log('🛑 已停止模态框中的朗读音频');
            }
        });
        // 🎯 新增：全局停止所有音频（确保彻底清理）
        if (window.globalAudioManager) {
            window.globalAudioManager.stopAll();
            console.log('🛑 全局停止所有音频播放');
        }
            
        // 隐藏并移除当前模态框
        modal.style.display = 'none';
        if (modal.parentNode) {
            modal.parentNode.removeChild(modal);
        }
        
        // ✨ 新增：重新计算剩余模态框的层次样式和顶端距离
        const remainingModals = document.querySelectorAll('.modal[style*="display: block"]');
        remainingModals.forEach((remainingModal, index) => {
            const newHeight = 88 - (index * 2);
            const finalNewHeight = Math.max(newHeight, 70);
            const newTopDistance = topDistances[index] || `${10 + index * 2}dvh`;
            const newContentHeight = `calc(${finalNewHeight}vh - ${newTopDistance})`;
            
            if (index > 0) {
                remainingModal.style.setProperty('--modal-height', `${finalNewHeight}%`);
                remainingModal.style.setProperty('--modal-top', newTopDistance);
                const modalContent = remainingModal.querySelector('.modal-content');
                if (modalContent) {
                    modalContent.style.height = newContentHeight;
                    modalContent.style.maxHeight = newContentHeight;
                    modalContent.style.marginTop = newTopDistance;
                }
            } else {
                // 底层模态框保持第一层的样式
                remainingModal.style.setProperty('--modal-top', topDistances[0] || '10dvh');
                remainingModal.classList.remove('layered-modal');
                const modalContent = remainingModal.querySelector('.modal-content');
                if (modalContent) {
                    const firstLayerHeight = `calc(88vh - ${topDistances[0] || '10dvh'})`;
                    modalContent.style.height = firstLayerHeight;
                    modalContent.style.maxHeight = firstLayerHeight;
                    modalContent.style.marginTop = topDistances[0] || '10dvh';
                }
            }
        });
        
        // 🔧 修复：重新聚焦到下一个可见的模态框
        if (remainingModals.length > 0) {
            const topModal = remainingModals[remainingModals.length - 1];
            topModal.focus();
        }
    }

    // 🔧 修复：为关闭按钮绑定独立的事件处理器
    modal.querySelector('.close').addEventListener('click', closeCurrentModal);

    // 🔧 修复：点击模态框背景只关闭当前模态框
    modal.addEventListener('click', (event) => {
        if (event.target === modal) {
            closeCurrentModal();
        }
    });

    // 🔧 修复：ESC键只关闭最顶层的模态框
    function handleEscapeKey(event) {
        if (event.key === 'Escape') {
            const allModals = document.querySelectorAll('.modal[style*="display: block"]');
            const topModal = allModals[allModals.length - 1];
            if (topModal && topModal.id === modalId) {
                closeCurrentModal();
            }
        }
    }
    
    document.addEventListener('keydown', handleEscapeKey);
    
    // 🔧 修复：模态框关闭时移除ESC键监听器
    const originalClose = closeCurrentModal;
    closeCurrentModal = function() {
        document.removeEventListener('keydown', handleEscapeKey);
        originalClose();
    };

    // 复制功能
    modal.querySelector('.copy-modal-content').onclick = function () {
        const titleText = modal.querySelector('.modal-title')?.innerText || '';
        const contentText = modal.querySelector('.modal-body')?.innerText || '';
        const fullText = `${titleText}\n\n${contentText}`;
        navigator.clipboard.writeText(fullText).then(() => {
            const btn = modal.querySelector('.copy-modal-content');
            btn.textContent = translations[selectedLang]?.copied || "已复制";
            setTimeout(() => (btn.textContent = translations[selectedLang]?.copy || "📋 复制"), 1500);
        });
    };
}


document.addEventListener("DOMContentLoaded", () => {
    const lang = navigator.language || navigator.userLanguage;
    const isTW = lang.startsWith("zh-TW") || lang.startsWith("zh-HK") || lang.startsWith("zh-MO");
    const selectedLang = isTW ? "zh-TW" : "zh-CN"; // ✅ 默认简体中文
    window.selectedLang = selectedLang;

    const t = translations[selectedLang];

    // 页面其他多语言替换
    document.querySelectorAll("[data-i18n]").forEach(el => {
        const key = el.getAttribute("data-i18n");
        if (t[key]) el.textContent = t[key];
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
        const key = el.getAttribute("data-i18n-placeholder");
        if (t[key]) el.setAttribute("placeholder", t[key]);
    });

    // 登录模块多语言替换
    const loginModal = document.getElementById("loginModal");
    if (loginModal) {
        const modalTitle = loginModal.querySelector(".modal-title");
        const usernameInput = document.getElementById("login-username");
        const passwordInput = document.getElementById("login-password");
        const loginButton = document.getElementById("login-submit");

        if (modalTitle) modalTitle.textContent = t.loginTitle;
        if (usernameInput) usernameInput.placeholder = t.usernamePlaceholder;
        if (passwordInput) passwordInput.placeholder = t.passwordPlaceholder;
        if (loginButton) loginButton.textContent = t.loginButton;
    }
});


function autoResizeInput() {
    userInput.style.height = "auto";
    userInput.style.height = userInput.scrollHeight + "px";
}

async function sendMessage() {
    let userMessage = userInput.value.trim();
    if (!userMessage) return;

    const rawUserMessage = userMessage;
    window.userInputWasTraditional = isTraditionalText(rawUserMessage) || shouldDisplayTraditional();
    window.lastUserRawInput = rawUserMessage;

    // 搜索用简体；展示保留用户原文（繁体用户看到繁体输入）
    userMessage = convertTraditionalToSimplified(userMessage);

    appendMessage('用户', window.userInputWasTraditional ? rawUserMessage : userMessage);
    userInput.value = '';
    autoResizeInput();
    sendButton.disabled = true;
    
    // ✅ 如果选择了诗歌分类，进行诗歌专用处理
    // ✅ 如果选择了诗歌分类，进行诗歌专用处理
    if (selectedCategory === '诗歌') {
        console.log("🎵 检测到诗歌分类选择，进入诗歌专用处理");
        
        // ✅ 如果包含诗歌相关关键词，去除空格和所有中英文标点
        if (/补充本|小本|儿童|诗歌|诗歌目录|补充本目录|儿童诗歌目录|^目录$/.test(userMessage)) {
            userMessage = userMessage.replace(/[\s,.!?;:()，。？！；：（）【】《》""'']/g, "");
        }
        
        // 🔧 第一优先级：检查目录查询（无数字）
        const hasNumbers = /\d/.test(userMessage);
        const isDirectoryQuery = !hasNumbers && /^(诗歌目录|补充本目录|补充本诗歌目录|儿童诗歌目录|目录|儿童目录|大本诗歌目录|大本目录|大本诗歌|补充诗歌目录|诗歌|大本|儿童|补充本)$/.test(userMessage);
        
        if (isDirectoryQuery) {
            console.log("📚 【第一优先级】检测到目录查询，进入目录处理流程");
            
            // 🔄 近似词映射函数
            function normalizeDirectoryName(query) {
                // 去除可能的空格和标点
                const cleanQuery = query.trim().replace(/[，。！？；：""''（）]/g, '');
                
                // 近似词映射表
                const synonymMap = {
                    // 儿童诗歌目录的近似词
                    '儿童目录': '儿童诗歌目录',
                    '儿童诗歌目录': '儿童诗歌目录',
                    '儿童诗歌': '儿童诗歌目录',
                    '儿童': '儿童诗歌目录',
                    
                    // 诗歌目录的近似词
                    '诗歌目录': '诗歌目录',
                    '大本诗歌目录': '诗歌目录',
                    '大本目录': '诗歌目录',
                    '诗歌': '诗歌目录',
                    '大本诗歌': '诗歌目录',
                    '大本': '诗歌目录',
                    
                    // 补充本目录的近似词
                    '补充本目录': '补充本诗歌目录',
                    '补充本': '补充本诗歌目录',
                    '补充本诗歌': '补充本诗歌目录',
                    '补充本诗歌目录': '补充本诗歌目录',
                    '补充诗歌目录': '补充本诗歌目录',
                    '小本目录': '补充本诗歌目录',
                    '小本诗歌目录': '补充本诗歌目录'
                };
                
                // 返回标准化后的目录名
                return synonymMap[cleanQuery] || cleanQuery;
            }
            
            // 特殊处理：如果用户只输入"目录"，显示所有可用目录
            if (userMessage === '目录') {
                console.log("📋 用户查询通用目录，显示所有可用目录选项");
                const availableDirectories = [];
                if (window.hymns && window.hymns['诗歌目录']) {
                    availableDirectories.push(`<div style="text-align: center;"><strong>诗歌目录</strong></div>\n${window.hymns['诗歌目录']}`);
                }
                if (window.hymns && window.hymns['补充本诗歌目录']) {
                    availableDirectories.push(`<div style="text-align: center;"><strong>补充本诗歌目录</strong></div>\n${window.hymns['补充本诗歌目录']}`);
                }
                if (window.hymns && window.hymns['儿童诗歌目录']) {
                    availableDirectories.push(`<div style="text-align: center;"><strong>儿童诗歌目录</strong></div>\n${window.hymns['儿童诗歌目录']}`);
                }
                
                if (availableDirectories.length > 0) {
                    const allDirectories = availableDirectories.join('\n\n');
                    appendMessage('AI', allDirectories);
                    scrollToBottom();
                    sendButton.disabled = userInput.value.trim() === '';
                    return;
                }
            } else {
                // 🔄 改进：处理具体的目录查询，先进行近似词标准化
                const standardizedQuery = normalizeDirectoryName(userMessage);
                console.log(`📖 查询具体目录: ${userMessage} -> 标准化为: ${standardizedQuery}`);
                
                if (window.hymns && window.hymns[standardizedQuery]) {
                    console.log(`✅ 【第一优先级】找到目录: ${standardizedQuery}`);
                    const fullMessage = `<div style="text-align: center;"><strong>${standardizedQuery}</strong></div>\n${window.hymns[standardizedQuery]}`;
                    appendMessage('AI', fullMessage);
                    scrollToBottom();
                    sendButton.disabled = userInput.value.trim() === '';
                    return;
                } else {
                    console.log(`❌ 【第一优先级】目录查询未找到: ${standardizedQuery}，继续第二优先级`);
                    // 不要直接返回错误，继续尝试下一个优先级
                }
            }
        }
        
        // 🔧 第二优先级：检查诗歌编号格式（有数字）
        const hymnNumberPattern = /(大本诗歌第|大本第|大本|补充本诗歌第|补充本第|补充本|小本|补充|补|儿童诗歌第|儿童第|儿童|童|儿|诗歌第)\d{1,4}首?|^\d{1,4}[\s首]*$/;
        const isHymnNumber = hymnNumberPattern.test(userMessage);
        
        if (isHymnNumber) {
            console.log("🎵 【第二优先级】检测到诗歌编号格式，进入诗歌编号处理");
            
            // ✅ 优先检查是否匹配特定诗歌格式
            const hymnPattern = /(大本诗歌第|大本第|大本|补充本诗歌第|补充本第|补充本|小本|补充|补|儿童诗歌第|儿童第|儿童|童|儿|诗歌第)(\d{1,4})首?|^(\d{1,4})[\s首]*$/;
            const match = userMessage.match(hymnPattern);
            
            if (match) {
                console.log("🎵 检测到诗歌编号格式");
                
                let category, number;
                
                if (match[3]) {
                    // 纯数字匹配 (如 "5", "123") - 查询所有三种类型
                    number = match[3];
                    console.log(`🔢 纯数字输入: ${number}，查询所有三种诗歌类型`);
                    
                    // 按优先级查询所有三种类型：诗歌 → 补充本 → 儿童
                    const searchPatterns = [
                        { prefix: `诗歌第${number}首`, display: `诗歌第${number}首` },
                        { prefix: `补充本诗歌第${number}首`, display: `补充本诗歌第${number}首` },
                        { prefix: `儿童诗歌第${number}首`, display: `儿童诗歌第${number}首` }
                    ];
                    
                    const foundHymns = [];
                    
                    for (const pattern of searchPatterns) {
                        console.log(`🔍 尝试匹配: ${pattern.prefix}`);
                        const hymnKey = Object.keys(window.hymns).find(key => key.startsWith(pattern.prefix));
                        if (hymnKey && window.hymns[hymnKey]) {
                            console.log(`✅ 找到诗歌: ${hymnKey}`);
                            foundHymns.push({
                                key: hymnKey,
                                display: pattern.display,
                                content: window.hymns[hymnKey]
                            });
                        }
                    }
                    
                    if (foundHymns.length > 0) {
                        // 构建展示消息
                        const hymnList = foundHymns.map(hymn => 
                            `${hymn.display}　查看全文`
                        ).join('<br>');
                        
                        const fullMessage = `${hymnList}`;
                        appendMessage('AI', fullMessage);
                        scrollToBottom();
                        sendButton.disabled = userInput.value.trim() === '';
                        return;
                    } else {
                        console.log(`❌ 【第二优先级】未找到编号为 ${number} 的任何诗歌，继续第三优先级`);
                        // 继续第三优先级
                    }
                } else {
                    // 带前缀的输入 - 查询具体类型
                    const prefix = match[1]; // 各种可能的前缀
                    number = match[2];
                    
                    if (prefix === "补充本诗歌第" || prefix === "补充本第" || prefix === "补充本" || prefix === "补充" || prefix === "补"|| prefix === "小本") {
                        console.log(`🔄 容错处理：将"${prefix}"映射到补充本`);
                        category = "补充本";
                    } else if (prefix === "儿童诗歌第" || prefix === "儿童第" || prefix === "儿童" || prefix === "儿"|| prefix === "童") {
                        console.log(`🔄 容错处理：将"${prefix}"映射到儿童诗歌`);
                        category = "儿童";
                    } else if (prefix === "诗歌第") {
                        category = "诗歌";
                    } else if (prefix.startsWith("大本")) {
                        // 容错处理：所有大本相关输入都映射到主诗歌
                        console.log(`🔄 容错处理：将"${prefix}"映射到主诗歌`);
                        category = "诗歌";
                    }
                    
                    // 构建查找前缀
                    let hymnKeyPrefix;
                    if (category === "诗歌") {
                        hymnKeyPrefix = `诗歌第${number}首`;
                    } else {
                        hymnKeyPrefix = `${category}诗歌第${number}首`;
                    }
                    
                    console.log(`🔍 查找诗歌前缀: ${hymnKeyPrefix}`);
                    
                    // ✅ 查找符合前缀的完整标题
                    const hymnKey = Object.keys(window.hymns).find(key => key.startsWith(hymnKeyPrefix));
                    if (hymnKey && window.hymns[hymnKey]) {
                        console.log(`✅ 【第二优先级】找到诗歌: ${hymnKey}`);
                        const fullMessage = `<strong>${hymnKey}</strong>\n${window.hymns[hymnKey]}`;
                        appendMessage('AI', fullMessage);
                        scrollToBottom();
                        sendButton.disabled = userInput.value.trim() === '';
                        return;
                    } else {
                        console.log(`❌ 【第二优先级】未找到诗歌: ${hymnKeyPrefix}，继续第三优先级`);
                        // 继续第三优先级
                    }
                }
            }
            
            // 首先检查用户是否明确指定了其他类别（排除大本，因为大本要映射到主诗歌）
            if ((userMessage.includes('补充本') || userMessage.includes('补充') || userMessage.includes('补') || 
                userMessage.includes('儿童') || userMessage.includes('儿')) && !userMessage.includes('大本')) {
                console.log("🎯 用户明确指定了非主诗歌类别");
                
                // 尝试提取用户指定的类别和数字 - 扩展容错
                const specificPattern = /(补充本|补充|补|儿童|儿).*?(\d{1,4})/;
                const specificMatch = userMessage.match(specificPattern);
                
                if (specificMatch) {
                    let category = specificMatch[1];
                    const number = specificMatch[2];
                    
                    // 容错映射
                    if (category === "补充" || category === "补") {
                        category = "补充本";
                        console.log(`🔄 容错处理：将"${specificMatch[1]}"映射到补充本`);
                    } else if (category === "儿") {
                        category = "儿童";
                        console.log(`🔄 容错处理：将"${specificMatch[1]}"映射到儿童`);
                    }
                    
                    const hymnKeyPrefix = `${category}诗歌第${number}首`;
                    console.log(`🔍 明确类别匹配: ${hymnKeyPrefix}`);
                    
                    const hymnKey = Object.keys(window.hymns).find(key => key.startsWith(hymnKeyPrefix));
                    if (hymnKey && window.hymns[hymnKey]) {
                        console.log(`✅ 【第二优先级】找到指定类别诗歌: ${hymnKey}`);
                        const fullMessage = `<strong>${hymnKey}</strong>\n${window.hymns[hymnKey]}`;
                        appendMessage('AI', fullMessage);
                        scrollToBottom();
                        sendButton.disabled = userInput.value.trim() === '';
                        return;
                    }
                }
            }
            
            // 处理大本容错：如果输入包含"大本"，直接映射到主诗歌
            if (userMessage.includes('大本')) {
                console.log("🔄 检测到大本输入，进行容错映射到主诗歌");
                const daBenPattern = /大本.*?(\d{1,4})/;
                const daBenMatch = userMessage.match(daBenPattern);
                
                if (daBenMatch) {
                    const number = daBenMatch[1];
                    const hymnKeyPrefix = `诗歌第${number}首`;
                    console.log(`🔍 大本容错映射: ${hymnKeyPrefix}`);
                    
                    const hymnKey = Object.keys(window.hymns).find(key => key.startsWith(hymnKeyPrefix));
                    if (hymnKey && window.hymns[hymnKey]) {
                        console.log(`✅ 【第二优先级】找到大本容错诗歌: ${hymnKey}`);
                        const fullMessage = `<strong>${hymnKey}</strong>\n${window.hymns[hymnKey]}`;
                        appendMessage('AI', fullMessage);
                        scrollToBottom();
                        sendButton.disabled = userInput.value.trim() === '';
                        return;
                    }
                }
            }
            
            // 尝试提取数字编号进行通用搜索
            const numberMatch = userMessage.match(/(\d{1,4})/);
            if (numberMatch) {
                const number = numberMatch[1];
                console.log(`🔢 提取到数字: ${number}`);
                
                // 按优先级尝试匹配各种诗歌类型：诗歌 → 补充本 → 儿童
                const searchPatterns = [
                    `诗歌第${number}首`,
                    `补充本诗歌第${number}首`,
                    `儿童诗歌第${number}首`
                ];
                
                for (const pattern of searchPatterns) {
                    console.log(`🔍 尝试匹配: ${pattern}`);
                    
                    const hymnKey = Object.keys(window.hymns).find(key => key.startsWith(pattern));
                    if (hymnKey && window.hymns[hymnKey]) {
                        console.log(`✅ 【第二优先级】找到诗歌: ${hymnKey}`);
                        const fullMessage = `<strong>${hymnKey}</strong>\n${window.hymns[hymnKey]}`;
                        appendMessage('AI', fullMessage);
                        scrollToBottom();
                        sendButton.disabled = userInput.value.trim() === '';
                        return;
                    }
                }
                
                console.log(`❌ 【第二优先级】未找到编号为 ${number} 的诗歌，继续第三优先级`);
            }
        }
        
        // 🔧 第三优先级：一般匹配（关键词搜索）
        console.log("🔤 【第三优先级】调用 handleLocalDictionaryMatch 进行诗歌关键词搜索");
        const matchedLocally = await handleLocalDictionaryMatch(userMessage);
        if (matchedLocally) {
            sendButton.disabled = userInput.value.trim() === '';
            return;
        }
        
        // 最终fallback - 提供更详细的错误信息
        console.log("❌ 所有优先级都未找到匹配结果");
        
        // 🔄 新增：提供智能提示
        let errorMessage = `在诗歌分类中未找到"${userMessage}"相关的内容。`;
        
        // 根据输入类型提供不同的建议
        if (hasNumbers) {
            errorMessage += `\n\n您输入的似乎是诗歌编号，请尝试：\n• 大本1 (查找诗歌第1首)\n• 补充本5 (查找补充本诗歌第5首)\n• 儿童10 (查找儿童诗歌第10首)`;
        } else {
            errorMessage += `\n\n您可以尝试：\n• 输入诗歌编号：如"大本1"、"补充本5"\n• 查看目录：输入"大本"、"补充本"、"儿童"\n• 搜索关键词：如"赞美"、"感谢"`;
        }
        
        appendMessage('AI', errorMessage);
        sendButton.disabled = userInput.value.trim() === '';
        return;
    }
    
    // ✅ 本地关键词匹配尝试（注解、经节、小百科等非诗歌内容）
    console.log("🔍 进入通用本地词典匹配");
    const matchedLocally = await handleLocalDictionaryMatch(userMessage);
    if (matchedLocally) {
        sendButton.disabled = userInput.value.trim() === '';
        return;
    }
    
    // ✅ 前端未匹配到，直接返回提示信息
    console.log("❌ 所有匹配方式都未找到结果");
    const selectedLang = window.selectedLang || 'zh-CN';
    const noAnswerText = translations[selectedLang]?.noAnswer || "暂时未找到您要的答案，您可以尝试其他问题！";
    appendMessage('AI', noAnswerText);
    sendButton.disabled = userInput.value.trim() === '';
}

sendButton.addEventListener('click', sendMessage);
userInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
});

userInput.addEventListener('input', () => {
    sendButton.disabled = userInput.value.trim() === '';
    autoResizeInput();
});

voiceButton.addEventListener('click', () => {
    if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
        alert("⚠️ 你的浏览器不支持语音识别！");
        return;
    }

    const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
    recognition.lang = isTraditional ? "zh-TW" : "zh-CN"; // ✅ 动态语言设置
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.start();

    voiceButton.style.opacity = "0.5";

    recognition.onresult = (event) => {
        let transcript = event.results[0][0].transcript || '';

        // ✅ 系统语言识别（繁体）
        const userLang = navigator.language || navigator.userLanguage;
        const isTraditional = userLang.startsWith("zh-TW") || userLang.startsWith("zh-HK") || userLang.startsWith("zh-MO");

        // ✅ 自动转为繁体中文
        if (isTraditional && typeof convertToTraditional === "function") {
            transcript = convertToTraditional(transcript);
        }

        // ✅ 正确写入繁体版本
        userInput.value = transcript;
        sendButton.disabled = transcript.trim() === '';
        autoResizeInput();
    };

    recognition.onerror = (event) => alert("语音识别失败：" + event.error);
    recognition.onend = () => voiceButton.style.opacity = "1";
});



// 📌原始消息
function replyFromAI(text, original) {
    appendMessage("AI", text, original);
}

// 📌复制、更多按钮容器
function ensureButtonGroup(contentDiv) {
    let container = contentDiv.querySelector('.button-group');
    if (!container) {
        container = document.createElement('div');
        container.className = 'button-group';
        contentDiv.appendChild(container);
    }
    return container;
}

// 📌 本地关键词处理模块（handleLocalDictionaryMatch 等）：
// ✅ 语气结构剥离：前缀 + 后缀
// ✅ 去除语气结构的前后缀
// ✅ 语气结构剥离：前缀 + 后缀
// ✅ 去掉语气词前缀
function cleanPoliteStructure(text) {
    const politePrefixes = [
        "请问你是否知道", "请问你能不能解释一下", "能不能告诉我",
        "你能不能", "你可以说说", "请你解释", "你知道", "我想知道",
        "我想了解", "请问", "请解释", "请说明", "请讲一下", 
        "能否解释", "能解释一下", "请说明一下", "你可否", "你是否知道",
        "是否能告诉我", "我是否可以知道", "你能告诉我", "请",
        "能不能解释", "方便说一下", "解释一下", "说明一下", 
        "你看", "你认为", "我好奇", "我在想",
        "是否可以理解为", "我们可以说", "你觉得", "是什么", "什么是","一下"
    ];

    const politeSuffixes = ["吗", "呢", "吧", "？", "?", "～"];

    for (const prefix of politePrefixes) {
        if (text.startsWith(prefix)) {
            text = text.slice(prefix.length).trim();
            break;
        }
    }

    text = removeSuffixes(text, politeSuffixes);
    return text;
}

function removeSuffixes(text, suffixes) {
    let changed = true;
    while (changed) {
        changed = false;
        for (const suffix of suffixes) {
            if (text.endsWith(suffix)) {
                text = text.slice(0, -suffix.length).trim();
                changed = true;
                break;
            }
        }
    }
    return text;
}

// ✅ 替换语义结构表达（标注类型）
const replacements = [
    // 定义型表达（会被清洗）
    { from: "了解什么是", to: "", type: "definition" },
    { from: "认识什么是", to: "", type: "definition" },
    { from: "知道什么是", to: "", type: "definition" },
    { from: "什么是", to: "", type: "definition" },
    { from: "是个什么概念", to: "", type: "definition" },
    { from: "该怎么解释", to: "", type: "definition" },
    { from: "如何解释", to: "", type: "definition" },
    { from: "如何理解", to: "", type: "definition" },
    { from: "怎样理解", to: "", type: "definition" },
    { from: "怎么样理解", to: "", type: "definition" },
    { from: "该如何说明", to: "", type: "definition" },
    { from: "可以怎样解释", to: "", type: "definition" },

    // 判断类（保留）
    { from: "是否", to: "", type: "judgment", keep: true },
    { from: "是不是", to: "", type: "judgment", keep: true },
    { from: "算不算", to: "", type: "judgment", keep: true },
    { from: "如何", to: "", type: "judgment", keep: true },
    { from: "怎样", to: "", type: "judgment", keep: true },
    { from: "怎么", to: "", type: "judgment", keep: true },
    { from: "为什么", to: "", type: "judgment", keep: true }
];

// ✅ 主清洗函数：支持类型标记
function standardizeQuestion(input) {
    let text = input.trim();
    text = cleanPoliteStructure(text);

    // ❗排除特殊例外：这些内容不能清洗
    const exceptions = [
        "我们是什么", "我们是什么？"
    ];

    if (exceptions.includes(text)) {
        return text;
    }

    let cleaned = text;
    let matchedType = "";

    for (const { from, to, type, keep } of replacements) {
        if (cleaned.includes(from)) {
            if (keep) {
                matchedType = type; // 标记但不替换
                break;
            } else {
                cleaned = cleaned.replace(from, to).trim();
                matchedType = type;
                break;
            }
        }
    }

    // 安全校验，避免过度清洗
    if (cleaned.length >= 2 && !/^[一二三四五六七八九十]$/.test(cleaned)) {
        return cleaned;
    }

    return input.trim();
}



// 判断是否应该排除
// 判断是否应该排除


// ✅ 主逻辑函数：判断关键词并匹配本地词典（支持查看全文按钮）
const sanitizeHtmlForTitle = (html) => html.replace(/<[^>]+>/g, '');


function isExcluded(query, targetKey, targetContent = '', categoryName = '', debugLevel = 'full') {
    if (!window.exclusionMap && !window.synonymMap) return false;

    const normalizedQuery = (query || '').trim().toLowerCase();
    const normalizedTargetKey = (typeof targetKey === 'string' ? targetKey : '').replace(/\s+/g, '').toLowerCase();
    
    const shouldLog = debugLevel === 'full' || debugLevel === 'simple';
    
    if (shouldLog) {
        console.log(`🔍 isExcluded 检查: query="${normalizedQuery}", targetKey="${normalizedTargetKey}"`);
    }
    
    // 🔧 步骤1：同义词保护
    if (window.synonymMap && window.synonymMap[query]) {
        for (const synonym of window.synonymMap[query]) {
            const normalizedSynonym = synonym.toLowerCase().replace(/\s+/g, '');
            if (normalizedTargetKey.includes(normalizedSynonym)) {
                if (shouldLog) {
                    console.log(`✅ [${categoryName}] 同义词保护: "${targetKey}" 匹配同义词 "${synonym}"`);
                }
                return false;
            }
        }
    }
    
    // 🔧 步骤2：找到排除规则
    let exclusionList = null;
    if (window.exclusionMap && window.exclusionMap[normalizedQuery]) {
        exclusionList = window.exclusionMap[normalizedQuery];
        if (shouldLog) {
            console.log(`✅ 精确匹配排除规则: "${normalizedQuery}"`);
        }
    }

    if (!exclusionList) {
        return false;
    }

    // 🔧 步骤3：核心逻辑 - 优先级匹配
    
    // 首先收集目标中包含的所有相关词汇
    const wordsInTarget = [];
    
    // 检查查询词
    if (normalizedTargetKey.includes(normalizedQuery)) {
        wordsInTarget.push({
            word: normalizedQuery,
            length: normalizedQuery.length,
            type: 'query'
        });
    }
    
    // 检查排除词
    for (const excludedRaw of exclusionList) {
        const excluded = (excludedRaw || '').replace(/\s+/g, '').toLowerCase();
        if (normalizedTargetKey.includes(excluded)) {
            wordsInTarget.push({
                word: excluded,
                length: excluded.length,
                type: 'exclude',
                original: excludedRaw
            });
        }
    }
    
    if (wordsInTarget.length === 0) {
        return false; // 目标不包含任何相关词汇
    }
    
    // 🔧 关键：按长度排序，最长的词汇优先级最高
    wordsInTarget.sort((a, b) => b.length - a.length);
    
    const primaryWord = wordsInTarget[0]; // 最长的词汇被认为是主要内容
    
    if (primaryWord.type === 'exclude') {
        // 如果最长的词是排除词，则排除
        if (shouldLog) {
            console.log(`🚫 [${categoryName}] 主要内容是排除词: "${targetKey}" 主要关于 "${primaryWord.original}"(${primaryWord.length})`);
        }
        return true;
    } else {
        // 如果最长的词是查询词，则不排除
        if (shouldLog) {
            console.log(`✅ [${categoryName}] 主要内容是查询词: "${targetKey}" 主要关于 "${query}"(${primaryWord.length})`);
        }
        return false;
    }
}

// 🔧 辅助函数：检查词汇是否作为完整词出现
function isWholeWord(text, word) {
    // 创建正则表达式，检查词汇边界
    const regex = new RegExp(`(^|[^a-zA-Z\u4e00-\u9fa5])${word}([^a-zA-Z\u4e00-\u9fa5]|$)`, 'i');
    return regex.test(text);
}


// 获取显示标题长度的函数
function getDisplayTitleLength(key, categoryName) {
    if (categoryName === '职事信息') {
        const prefixList = ['今时代神圣启示的先见', '李常受文集', '倪柝声文集', '真理课程', '新约总论', '生命读经', '生命课程'];
        let displayTitle = key;
        for (const prefix of prefixList) {
            const regex = new RegExp(`^.*?${prefix}_`);
            if (regex.test(displayTitle)) {
                displayTitle = displayTitle.replace(regex, '').trim();
                break;
            }
        }
        displayTitle = displayTitle.replace(/_/g, ' ').trim();
        return displayTitle.length;
    }
    return key.length; // 其他分类使用原始长度
}

// 使用显示标题长度的三维度综合排序
function comprehensiveSortWithDisplayLength(results, originalQuery, categoryName) {
    console.log(`🎯 [${categoryName}] 开始三维度综合排序（使用显示标题长度），共 ${results.length} 条结果`);
    
    const sortedResults = results.sort((a, b) => {
        // 计算 a 的综合分数
        const aMatchType = a.score === 0 ? 1000 : (a.score === 0.1 ? 2000 : 3000);
        const aQueryType = a.key.includes(originalQuery) ? 100 : 200;
        const aDisplayLength = getDisplayTitleLength(a.key, categoryName);
        const aTotal = aMatchType + aQueryType + aDisplayLength;
        
        // 计算 b 的综合分数  
        const bMatchType = b.score === 0 ? 1000 : (b.score === 0.1 ? 2000 : 3000);
        const bQueryType = b.key.includes(originalQuery) ? 100 : 200;
        const bDisplayLength = getDisplayTitleLength(b.key, categoryName);
        const bTotal = bMatchType + bQueryType + bDisplayLength;
        
        return aTotal - bTotal;
    });
    
    console.log(`🧩 [${categoryName}] 三维度排序完成（使用显示标题长度）`);
    return sortedResults;
}

function cleanKeyForMatching(key) {
    const prefixList = ['今时代神圣启示的先见', '李常受文集', '倪柝声文集', '真理课程', '新约总论', '生命读经', '生命课程'];
    let cleanedKey = key;
    
    for (const prefix of prefixList) {
        const regex = new RegExp(`^.*?${prefix}_`);
        if (regex.test(cleanedKey)) {
            cleanedKey = cleanedKey.replace(regex, '').trim();
            break;
        }
    }
    
    cleanedKey = cleanedKey.replace(/_/g, ' ').trim();
    return cleanedKey;
}

// ✅ 添加前缀清理函数
function cleanKeyForMatching(key) {
    const prefixList = ['今时代神圣启示的先见', '李常受文集', '倪柝声文集', '真理课程', '新约总论', '生命读经', '生命课程'];
    let cleanedKey = key;
    
    for (const prefix of prefixList) {
        const regex = new RegExp(`^.*?${prefix}_`);
        if (regex.test(cleanedKey)) {
            cleanedKey = cleanedKey.replace(regex, '').trim();
            break;
        }
    }
    
    cleanedKey = cleanedKey.replace(/_/g, ' ').trim();
    return cleanedKey;
}



// ✅ 【修改】handleLocalDictionaryMatch 函数 - 最小修改方案
// 只修改分类处理逻辑，其他代码保持不变

async function handleLocalDictionaryMatch(userMessage) {
    const originalInput = (window.lastUserRawInput || userMessage).trim();
    const rawInput = standardizeQuestion(userMessage.trim());
    const query = rawInput.trim();

    console.log("🔍 原始输入：", originalInput);
    console.log("🎯 清洗后匹配关键词（简体）：", rawInput);

    const categories = [
        {
            name: '诗歌',
            data: window.shi_ge,
            condition: selectedCategory === '诗歌' || (!selectedCategory && rawInput.includes('诗歌')),
            render: (k, v) =>
                `<p style="margin-bottom:12px;"><span class="data-title">${v}</span> <button class="view-original" data-source="hymns" data-title="${v}">查看全文</button></p>${k.slice(0, 120)}……`
        },
        
        // ===== 修复后的经节分类 =====
        {
            name: '经节',
            
            // 安全的数据获取函数
            data: async function() {
                console.log('🔍 开始加载经节数据...');
                
                if (this._mergedData) {
                    console.log('✅ 使用缓存的经节数据');
                    return this._mergedData;
                }

                const mergedData = {};
                let totalLoaded = 0;
                
                // 数据源1：经节问答数据
                try {
                    if (window.jing_jie_wen_da && 
                        typeof window.jing_jie_wen_da === 'object' && 
                        window.jing_jie_wen_da !== null) {
                        
                        const keys = Object.keys(window.jing_jie_wen_da);
                        console.log(`📖 jing_jie_wen_da 键数组:`, keys);
                        
                        if (Array.isArray(keys) && keys.length > 0) {
                            for (const key of keys) {
                                if (key && typeof key === 'string' && window.jing_jie_wen_da[key] !== undefined) {
                                    mergedData[key] = {
                                        content: window.jing_jie_wen_da[key],
                                        source: 'jing_jie_wen_da',
                                        priority: 1
                                    };
                                    totalLoaded++;
                                }
                            }
                            console.log(`📖 成功加载经节问答数据: ${keys.length} 条`);
                        } else {
                            console.warn('⚠️ jing_jie_wen_da 的 keys 不是有效数组:', keys);
                        }
                    } else {
                        console.warn('⚠️ window.jing_jie_wen_da 不存在或无效:', typeof window.jing_jie_wen_da);
                    }
                } catch (error) {
                    console.error('❌ 处理 jing_jie_wen_da 时出错:', error);
                }

                // 数据源2：圣经经文数据
                try {
                    if (window.bibleVerse && 
                        typeof window.bibleVerse === 'object' && 
                        window.bibleVerse !== null) {
                        
                        const keys = Object.keys(window.bibleVerse);
                        console.log(`📜 bibleVerse 键数组长度:`, keys ? keys.length : 'undefined');
                        
                        if (Array.isArray(keys) && keys.length > 0) {
                            for (const key of keys) {
                                if (key && typeof key === 'string' && window.bibleVerse[key] !== undefined) {
                                    mergedData[key] = {
                                        content: window.bibleVerse[key],
                                        source: 'bible_verse',
                                        priority: 2
                                    };
                                    totalLoaded++;
                                }
                            }
                            console.log(`📜 成功加载圣经经文数据: ${keys.length} 条`);
                        } else {
                            console.warn('⚠️ bibleVerse 的 keys 不是有效数组:', keys);
                        }
                    } else {
                        console.warn('⚠️ window.bibleVerse 不存在或无效:', typeof window.bibleVerse);
                    }
                } catch (error) {
                    console.error('❌ 处理 bibleVerse 时出错:', error);
                }

                // 数据源3：经节注释数据
                try {
                    if (window.jing_jie_zhu_shi && 
                        typeof window.jing_jie_zhu_shi === 'object' && 
                        window.jing_jie_zhu_shi !== null) {
                        
                        const keys = Object.keys(window.jing_jie_zhu_shi);
                        console.log(`📝 jing_jie_zhu_shi 键数组长度:`, keys ? keys.length : 'undefined');
                        
                        if (Array.isArray(keys) && keys.length > 0) {
                            for (const key of keys) {
                                if (key && typeof key === 'string' && window.jing_jie_zhu_shi[key] !== undefined) {
                                    mergedData[key] = {
                                        content: window.jing_jie_zhu_shi[key],
                                        source: 'jing_jie_zhu_shi',
                                        priority: 3
                                    };
                                    totalLoaded++;
                                }
                            }
                            console.log(`📝 成功加载经节注释数据: ${keys.length} 条`);
                        } else {
                            console.warn('⚠️ jing_jie_zhu_shi 的 keys 不是有效数组:', keys);
                        }
                    } else {
                        console.warn('⚠️ window.jing_jie_zhu_shi 不存在或无效:', typeof window.jing_jie_zhu_shi);
                    }
                } catch (error) {
                    console.error('❌ 处理 jing_jie_zhu_shi 时出错:', error);
                }

                this._mergedData = mergedData;
                console.log(`🔗 经节数据合并完成，总计加载: ${totalLoaded} 条`);
                console.log(`🔗 合并后的数据键数量: ${Object.keys(mergedData).length}`);
                
                return mergedData;
            },
            
            // 安全的条件检查
            condition: function(selectedCategory, rawInput) {
                try {
                    if (!rawInput || typeof rawInput !== 'string') {
                        return false;
                    }
                    
                    console.log(`🔍 [经节分类] 检查输入: "${rawInput}"`);
                    
                    // 1. 首先检查是否为经节引用格式
                    if (isBibleVerseReference(rawInput)) {
                        console.log(`✅ [经节分类] 识别为经节引用: "${rawInput}"`);
                        return true;
                    }
                    
                    // 2. 检查分类选择
                    if (selectedCategory === '经节') {
                        console.log(`✅ [经节分类] 分类匹配: selectedCategory = "${selectedCategory}"`);
                        return true;
                    }
                    
                    // 3. 检查关键词匹配
                    if (!selectedCategory && rawInput.includes('经节')) {
                        console.log(`✅ [经节分类] 关键词匹配: 包含"经节"`);
                        return true;
                    }
                    
                    console.log(`❌ [经节分类] 条件不满足`);
                    return false;
                    
                } catch (error) {
                    console.error('经节 condition 检查出错:', error);
                    return false;
                }
            },
            
            // 安全的渲染函数
            render: (k, v, index) => {
                try {
                    if (!k || !v) {
                        return '<p>数据格式错误</p>';
                    }
                    
                    const { content, source } = v;
                    
                    if (content === undefined || content === null) {
                        return '<p>内容为空</p>';
                    }

                    if (source === 'jing_jie_wen_da') {
                        const safeContent = String(content);
                        const preview = safeContent.length > 120 ? safeContent.slice(0, 120) + '……' : safeContent;
                        return `<p style="margin-bottom:12px;"><span class="data-title">${k}</span> <button class="view-original" data-source="jing_jie_wen_da" data-title="${k}">查看全文</button></p>${preview}`;
                    } else if (source === 'bible_verse') {
                        return `<div style="border-left: 4px solid #4CAF50; padding-left: 12px; margin-bottom: 12px;">
                                    <p style="margin-bottom:8px; font-weight: bold; color: #2E7D32;">${k}</p>
                                    <p style="margin-bottom:8px; font-size: 16px; line-height: 1.5;">${content}</p>
                                </div>`;
                    } else if (source === 'jing_jie_zhu_shi') {
                        return `${content}`; 
                    } else {
                        return `<h3>${k}</h3>\n[${index + 1}]${String(content).trim()}`;
                    }
                } catch (error) {
                    console.error('经节 render 函数出错:', error);
                    return '<p>渲染出错</p>';
                }
            }
        },

        {
            name: '注解',
            data: window.zhu_jie_wen_da,
            condition: selectedCategory === '注解' || (!selectedCategory && rawInput.includes('注解')),
            render: (k, v) => {
                // 检查value是否为空，如果为空则做成图片按钮
                if (!v || v.trim() === '') {
                    return `<button class="chart-image-btn" data-chart-name="${k}" style="width: 100%; text-align: left !important; margin-bottom: 8px; padding: 10px 15px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; transition: all 0.3s ease; justify-content: flex-start; display: flex; align-items: center;">${k}</button>`;
                } else if (k === '图表') {
                    // 特殊处理：生成按钮列表
                    const chartItems = v.split('\n');
                    const buttons = chartItems.map(item => 
                        `<button class="chart-image-btn" data-chart-name="${item}" style="width: 100%; text-align: left !important; margin-bottom: 8px; padding: 10px 15px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; transition: all 0.3s ease; justify-content: flex-start; display: flex; align-items: center;">${item}</button>`
                    ).join('');
                    return `<div style="display: flex; flex-direction: column; gap: 0;">${buttons}</div>`;
                } else {
                    // 普通注解的现有逻辑
                    return `<p style="margin-bottom:12px;"><span class="data-title">${k}</span> <button class="view-original" data-source="zhu_jie_wen_da" data-title="${k}">查看全文</button></p>${v.slice(0, 120)}……`;
                }
            }
        },
        {
            name: '职事信息',
            data: async function() {
                if (this._mergedData) {
                    return this._mergedData;
                }

                const mergedData = {};
                
                try {
                    const response = await fetch('private/4_zhi_shi_xin_xi_shu_ming.json');
                    const shuMingData = await response.json();
                    
                    this._shuMingData = shuMingData;
                    
                    for (const key of Object.keys(shuMingData)) {
                        mergedData[key] = {
                            content: shuMingData[key],
                            source: 'shu_ming',
                            priority: 1
                        };
                    }
                    
                    console.log(`📚 加载书名数据: ${Object.keys(shuMingData).length} 条`);
                } catch (error) {
                    console.warn('⚠️ 加载书名数据失败:', error);
                }

                if (window.zhi_shi_xin_xi && typeof window.zhi_shi_xin_xi === 'object') {
                    for (const key of Object.keys(window.zhi_shi_xin_xi)) {
                        mergedData[key] = {
                            content: window.zhi_shi_xin_xi[key],
                            source: 'zhi_shi',
                            priority: 2
                        };
                    }
                    
                    console.log(`📖 加载职事数据: ${Object.keys(window.zhi_shi_xin_xi).length} 条`);
                }

                this._mergedData = mergedData;
                console.log(`🔗 合并完成，总计: ${Object.keys(mergedData).length} 条`);
                
                return mergedData;
            },
            
            condition: selectedCategory === '职事信息' || !selectedCategory,
            
            render: (k, v, index) => {
                const { content, source } = v;

                if (source === 'shu_ming') {
                    return `${k}[目录]`;
                } else {
                    let displayTitle = k;
                    const prefixList = ['今时代神圣启示的先见', '李常受文集', '倪柝声文集', '真理课程', '新约总论', '生命读经', '生命课程'];
                    for (const prefix of prefixList) {
                        const regex = new RegExp(`^.*?${prefix}_`);
                        if (regex.test(displayTitle)) {
                            displayTitle = displayTitle.replace(regex, '').trim();
                            break;
                        }
                    }
                    displayTitle = displayTitle.replace(/_/g, ' ').trim();
                    return `<h3>${displayTitle}</h3>\n[${index + 1}]${content.trim()}`;
                }
            }
        },
        {
            name: '问答',
            data: window.xiao_bai_ke,
            condition: selectedCategory === '问答' || !selectedCategory,
            render: (k, v) =>
                `<p><span class="data-title">${k}</span> <button class="view-original" data-source="xiao_bai_ke" data-title="${k}">查看全文</button></p>${v.slice(0, 180)}……`
        }
    ];

    // ✅ 【修改】新的分类处理逻辑 - 最小修改
    console.log(`🎯 当前选择的分类: ${selectedCategory || '未选择'}`);
    
    // 确定要处理的分类
    let targetCategoryName;
    if (selectedCategory) {
        // 用户选择了具体分类
        targetCategoryName = selectedCategory;
        console.log(`✅ 用户选择了分类: ${targetCategoryName}`);
    } else {
        // 用户没选分类，默认使用"问答"分类
        targetCategoryName = '问答';
        console.log(`🔄 未选择分类，默认使用: ${targetCategoryName}`);
    }

    // 找到对应的分类并处理
    for (const category of categories) {
        // ✅ 只处理目标分类
        if (category.name !== targetCategoryName) {
            continue; // 跳过非目标分类
        }
        
        console.log(`🏷️ 检查分类: ${category.name}`);
        const conditionMet = typeof category.condition === 'function'
            ? category.condition(selectedCategory, rawInput)
            : category.condition;
        console.log(`🏷️ 分类条件: ${conditionMet}`);
        
        if (!conditionMet) {
            console.log(`⚠️ [${category.name}] 条件不满足，跳过`);
            continue;
        }

        let dict;
        
        // 处理异步data (主要针对职事信息)
        if (typeof category.data === 'function') {
            try {
                dict = await category.data();
                console.log(`🏷️ 异步加载数据存在: ${!!(dict && typeof dict === 'object')}`);
            } catch (error) {
                console.error(`❌ [${category.name}] 异步数据加载失败:`, error);
                continue;
            }
        } else {
            dict = category.data;
            console.log(`🏷️ 数据存在: ${!!(dict && typeof dict === 'object')}`);
        }
        
        if (!dict || typeof dict !== 'object') {
            console.log(`⚠️ [${category.name}] 数据不存在，跳过`);
            continue;
        }

        const keys = Object.keys(dict);
        console.log(`📊 [${category.name}] 总条目数: ${keys.length}`);

        // 同义词扩展（保持原有逻辑）
        function expandQuery(query) {
            let expandedQueries = [query];
            
            if (window.synonymMap) {
                // 正向：用户搜索key，添加对应的synonyms
                if (window.synonymMap[query]) {
                    expandedQueries.push(...window.synonymMap[query]);
                    console.log(`🔄 同义词扩展: "${query}" → 添加: ${window.synonymMap[query].join(', ')}`);
                }
                
                // 反向：用户搜索synonym，添加对应的key
                for (const [key, synonyms] of Object.entries(window.synonymMap)) {
                    if (synonyms.includes(query)) {
                        expandedQueries.push(key);
                        console.log(`🔄 反向同义词: "${query}" → 添加: "${key}"`);
                    }
                }
            }
            
            // 去重
            const uniqueQueries = [...new Set(expandedQueries)];
            if (uniqueQueries.length > 1) {
                console.log(`🎯 最终扩展查询词: [${uniqueQueries.join(', ')}]`);
            }
            return uniqueQueries;
        }

        const expandedQueries = expandQuery(query);

        // 【保持原有的所有匹配逻辑不变】
        let exactMatch, containsMatches, fuzzyResults, valueMatches = [];

        if (category.name === '经节') {
            // 经节分类的现有逻辑完全保持不变...
            console.log("🔧 经节分类独立匹配处理");
                // ✨ 统一预处理
            const preprocessed = preprocessInput(query);
            console.log(`🧹 预处理: "${query}" ➜ "${preprocessed}"`);

            // 【目录关键词优先】新约/旧约/圣经/目录 → 仅显示 jing_jie_zhu_shi 目录按钮
            const jingJieZhuShiCatalog = lookupJingJieZhuShiCatalog(preprocessed, expandedQueries);
            if (jingJieZhuShiCatalog) {
                console.log(`📂 [经节] jing_jie_zhu_shi 目录关键词: ${jingJieZhuShiCatalog.key}`);
                appendMessage("AI", formatMessage(jingJieZhuShiCatalog.value), originalInput);
                appendCopyButton();
                return true;
            }

            // 【第一优先级】：检查章节格式（以"章"结尾）
            if (detectChapterFormat(preprocessed)) {
                console.log("📖 检测到章节格式，进入章节处理流程");

                try {
                    const chapterResult = await handleChapterFormatQuery(preprocessed);
                    if (chapterResult) return true;
                } catch (error) {
                    console.error("❌ 章节格式处理出错:", error);
                }

                console.log("❌ 章节格式处理失败，继续其他处理逻辑");
            }
                        
            // 【第二优先级】：检查纯书名（目录查询）
            else if (isBookNameOnlyEnhanced(preprocessed)) {
                console.log("📚 检测到纯书名，进入目录查询流程");
                try {
                    const directoryResult = await handleBookDirectoryQuery(preprocessed);
                    if (directoryResult) {
                        return true; // 处理成功，直接返回
                    }
                } catch (error) {
                    console.error("❌ 目录查询处理出错:", error);
                }
                console.log("❌ 目录查询处理失败，继续其他处理逻辑");
            }
            
            // 【第三优先级】：检查经节引用格式
            console.log("🔍 开始经节引用格式优先检查...");
            const bibleVerseResult = prioritizeBibleVerse(preprocessed);
            if (bibleVerseResult.found) {
                console.log(`✅ 找到经节引用: ${bibleVerseResult.key} -> ${bibleVerseResult.content.substring(0, 50)}...`);
                
                const formattedResult = `<div style="border-left: 4px solid #4CAF50; padding-left: 12px; margin-bottom: 12px;">
                    <p style="margin-bottom:8px; font-weight: bold; color: #2E7D32;">${bibleVerseResult.key}</p>
                    <p style="margin-bottom:8px; font-size: 16px; line-height: 1.5;">${bibleVerseResult.content}</p>
                </div>`;
                
                appendMessage("AI", formatMessage(formattedResult), originalInput);
                appendCopyButton();
                return true;
            }
            console.log("❌ 经节引用格式检查未找到匹配，继续常规匹配流程");
            
            // 【第四优先级】：继续现有的三个数据源处理逻辑...
            const allResults = [];
            
            // 定义三个数据源的独立处理逻辑
            const dataSources = [
                {
                    name: 'jing_jie_wen_da',
                    data: window.jing_jie_wen_da,
                    supportsFuzzy: true,
                    supportsContains: true,
                    supportsValueSearch: true,
                    render: (k, v) => `<p style="margin-bottom:12px;"><span class="data-title">${k}</span> <button class="view-original" data-source="jing_jie_wen_da" data-title="${k}">查看全文</button></p>${v.slice(0, 120)}……`
                },
                {
                    name: 'bible_verse',
                    data: window.bibleVerse,
                    supportsFuzzy: false,
                    supportsContains: false,
                    supportsValueSearch: true,
                    render: (k, v) => `<div style="border-left: 4px solid #4CAF50; padding-left: 12px; margin-bottom: 12px;">
                        <p style="margin-bottom:8px; font-weight: bold; color: #2E7D32;">${k}</p>
                        <p style="margin-bottom:8px; font-size: 16px; line-height: 1.5;">${v}</p>
                    </div>`
                },
                {
                    name: 'jing_jie_zhu_shi',
                    data: window.jing_jie_zhu_shi,
                    supportsFuzzy: false,
                    supportsContains: false,
                    supportsValueSearch: true,
                    render: (k, v) => `${v}`
                }
            ];
            
            // 对每个数据源独立进行匹配
            for (const source of dataSources) {
                if (!source.data || typeof source.data !== 'object') {
                    console.log(`⚠️ [${source.name}] 数据不存在，跳过`);
                    continue;
                }
                
                const sourceKeys = Object.keys(source.data);
                console.log(`📊 [${source.name}] 总条目数: ${sourceKeys.length}`);
                
                const sourceResults = [];
                
                // 1. 精确匹配
                const exactMatch = sourceKeys.find(k => {
                    const isMatch = expandedQueries.includes(k);
                    if (isMatch) {
                        const excluded = isExcluded(query, k, source.data[k], category.name, 'full');
                        if (excluded) {
                            console.log(`🚫 [${source.name}] 排除精确匹配: ${k}`);
                            return false;
                        }
                        console.log(`✅ [${source.name}] 精确匹配: ${k}`);
                        return true;
                    }
                    return false;
                });
                
                if (exactMatch) {
                    sourceResults.push({ 
                        key: exactMatch, 
                        value: source.data[exactMatch],
                        score: 0, 
                        source: source.name,
                        matchType: 'exact'
                    });
                }

                // jing_jie_zhu_shi 已有精确匹配时不再做值搜索，避免重复目录按钮
                const skipValueSearch = source.name === 'jing_jie_zhu_shi' && !!exactMatch;
                
                // 2. 包含匹配 (如果支持)
                if (source.supportsContains) {
                    const containsMatches = sourceKeys.filter(k => {
                        if (exactMatch && k === exactMatch) return false;
                        
                        const isMatch = expandedQueries.some(q => k.includes(q));
                        if (isMatch) {
                            const excluded = isExcluded(query, k, source.data[k], category.name, 'simple');
                            if (excluded) {
                                console.log(`🚫 [${source.name}] 排除包含匹配: ${k}`);
                                return false;
                            }
                            console.log(`📌 [${source.name}] 包含匹配: ${k}`);
                            return true;
                        }
                        return false;
                    });
                    
                    for (const match of containsMatches) {
                        sourceResults.push({ 
                            key: match, 
                            value: source.data[match],
                            score: 0.1, 
                            source: source.name,
                            matchType: 'contains'
                        });
                    }
                }
                
                // 3. 模糊匹配 (如果支持)
                if (source.supportsFuzzy) {
                    const fuse = new Fuse(sourceKeys.map(k => ({ key: k })), {
                        keys: ['key'],
                        includeScore: true,
                        threshold: 1.0
                    });
                    
                    const fuzzyResults = fuse.search(query)
                        .filter(result => {
                            const k = result.item.key;
                            if (result.score > 0.25) return false;
                            if (exactMatch && k === exactMatch) return false;
                            if (sourceResults.some(r => r.key === k)) return false;
                            
                            const excluded = isExcluded(query, k, source.data[k], category.name, 'simple');
                            if (excluded) {
                                console.log(`🚫 [${source.name}] 排除模糊匹配: ${k}`);
                                return false;
                            }
                            return true;
                        });
                    
                    for (const result of fuzzyResults) {
                        sourceResults.push({ 
                            key: result.item.key, 
                            value: source.data[result.item.key],
                            score: result.score, 
                            source: source.name,
                            matchType: 'fuzzy'
                        });
                    }
                }

                // 4. 值匹配：在正文（简体）中搜索
                if (source.supportsValueSearch && !skipValueSearch) {
                    const existingKeys = new Set(sourceResults.map((r) => r.key));
                    const valueKeys = matchKeysByValue(
                        sourceKeys,
                        (k) => source.data[k],
                        query,
                        expandedQueries,
                        (q, k, raw) => isExcluded(q, k, raw, category.name, 'simple'),
                    ).filter((k) => !existingKeys.has(k));

                    for (const match of valueKeys) {
                        console.log(`📄 [${source.name}] 值匹配: ${match}`);
                        sourceResults.push({
                            key: match,
                            value: source.data[match],
                            score: 0.2,
                            source: source.name,
                            matchType: 'value',
                        });
                    }
                }
                
                // 对当前数据源的结果进行排序
                sourceResults.sort((a, b) => {
                    const typeOrder = { exact: 0, contains: 1, value: 2, fuzzy: 3 };
                    if (typeOrder[a.matchType] !== typeOrder[b.matchType]) {
                        return typeOrder[a.matchType] - typeOrder[b.matchType];
                    }
                    return a.score - b.score;
                });
                
                // 限制每个数据源的结果数量
                const limitedResults = sourceResults.slice(0, 10);
                allResults.push(...limitedResults);
                
                console.log(`🔍 [${source.name}] 匹配到 ${limitedResults.length} 条结果`);
            }
            
            // 对所有结果进行最终排序
            allResults.sort((a, b) => {
                const typeOrder = { exact: 0, contains: 1, fuzzy: 2 };
                if (typeOrder[a.matchType] !== typeOrder[b.matchType]) {
                    return typeOrder[a.matchType] - typeOrder[b.matchType];
                }
                return a.score - b.score;
            });
            
            // 生成最终输出
            if (allResults.length > 0) {
                console.log(`🧩 [经节] 合并后共 ${allResults.length} 条结果`);
                
                // 按数据源分组显示
                const groupedResults = {};
                for (const result of allResults) {
                    if (!groupedResults[result.source]) {
                        groupedResults[result.source] = [];
                    }
                    groupedResults[result.source].push(result);
                }
                
                const formattedSections = [];
                
                // 按数据源顺序输出
                for (const source of dataSources) {
                    if (groupedResults[source.name] && groupedResults[source.name].length > 0) {
                        const sourceResults = groupedResults[source.name];
                        const formattedResults = sourceResults.map(result => 
                            source.render(result.key, result.value)
                        ).join('\n\n');
                        
                        formattedSections.push(`${formattedResults}`);
                    }
                }
                
                const finalOutput = formattedSections.join('\n\n');
                appendMessage("AI", formatMessage(finalOutput), originalInput); 
                appendCopyButton();
                
                return true;
            } else {
                console.log(`ℹ️ [经节] 无匹配结果`);
                continue;
            }
        }else if (category.name === '注解') {
            console.log("🔧 注解分类独立匹配处理");
            
            // 统一预处理
            const preprocessed = preprocessInput(query);
            console.log(`🧹 预处理: "${query}" ➜ "${preprocessed}"`);
            
            // 【第一优先级】：检查注解引用格式
            if (isBibleAnnotationReference(preprocessed)) {
                console.log("📝 检测到注解引用格式，进入专门处理流程");
                
                try {
                    const annotationResult = await handleAnnotationFormatQuery(preprocessed);
                    if (annotationResult) return true;
                } catch (error) {
                    console.error("❌ 注解格式处理出错:", error);
                }
                
                console.log("❌ 注解格式处理失败，继续传统匹配逻辑");
            }
            
            // 【第二优先级】：继续现有的传统匹配逻辑
            // 使用与其他分类相同的匹配处理方式
            try {
                // 精确匹配
                const rawExactMatch = keys.find(k => expandedQueries.includes(k));
                if (rawExactMatch) {
                    const excluded = isExcluded(query, rawExactMatch, dict[rawExactMatch], category.name, 'full');
                    exactMatch = excluded ? null : rawExactMatch;
                    if (excluded) {
                        console.log(`🚫 [${category.name}] 排除精确匹配: ${rawExactMatch}`);
                    }
                } else {
                    exactMatch = null;
                }
                
                // 包含匹配
                const rawContainsMatches = keys.filter(k => expandedQueries.some(q => k.includes(q)));
                containsMatches = rawContainsMatches.filter(k => {
                    const excluded = isExcluded(query, k, dict[k], category.name, 'simple');
                    if (excluded) {
                        console.log(`🚫 [${category.name}] 排除包含匹配: ${k}`);
                        return false;
                    }
                    return true;
                });

                // 模糊匹配
                const fuse = new Fuse(keys.map(k => ({ key: k })), {
                    keys: ['key'],
                    includeScore: true,
                    threshold: 1.0
                });
                
                const rawFuzzyResults = fuse.search(query);
                fuzzyResults = rawFuzzyResults.filter(result => {
                    const k = result.item.key;
                    if (result.score > 0.25) return false;
                    
                    const excluded = isExcluded(query, k, dict[k], category.name, 'simple');
                    if (excluded) {
                        console.log(`🚫 [${category.name}] 排除模糊匹配: ${k}`);
                        return false;
                    }
                    return true;
                });

                const skipKeys = new Set([
                    ...(exactMatch ? [exactMatch] : []),
                    ...containsMatches,
                    ...fuzzyResults.map((r) => r.item.key),
                ]);
                valueMatches = matchKeysByValue(
                    keys,
                    (k) => dict[k],
                    query,
                    expandedQueries,
                    (q, k, raw) => isExcluded(q, k, raw, category.name, 'simple'),
                ).filter((k) => !skipKeys.has(k));
                if (valueMatches.length) {
                    console.log(`📄 [${category.name}] 值匹配: ${valueMatches.length} 条`);
                }
                
            } catch (error) {
                console.warn(`注解分类匹配出错:`, error);
                exactMatch = null;
                containsMatches = [];
                fuzzyResults = [];
            }           
        } else if (category.name === '职事信息') {
            // 职事信息的现有逻辑保持不变
            console.log("🔧 职事信息特殊匹配处理");
            
            // 精确匹配
            exactMatch = keys.find(k => {
                try {
                    if (!dict[k] || !dict[k].source) {
                        return false;
                    }
                    
                    const cleanedKey = dict[k].source === 'zhi_shi' ? cleanKeyForMatching(k) : k;
                    const isMatch = expandedQueries.includes(cleanedKey);
                    if (isMatch) {
                        const excluded = isExcluded(query, k, dict[k].content || dict[k], category.name, 'full');
                        if (excluded) {
                            console.log(`🚫 [${category.name}] 排除精确匹配: ${k}`);
                            return false;
                        }
                        console.log(`✅ 职事信息精确匹配: 原始key="${k}", 清理key="${cleanedKey}"`);
                        return true;
                    }
                    return false;
                } catch (error) {
                    console.warn(`职事信息精确匹配出错 for key: ${k}`, error);
                    return false;
                }
            });

            // 包含匹配
            containsMatches = keys.filter(k => {
                try {
                    if (!dict[k] || !dict[k].source) {
                        return false;
                    }
                    
                    const cleanedKey = dict[k].source === 'zhi_shi' ? cleanKeyForMatching(k) : k;
                    const isMatch = expandedQueries.some(q => cleanedKey.includes(q));
                    if (isMatch) {
                        const excluded = isExcluded(query, k, dict[k].content || dict[k], category.name, 'simple');
                        if (excluded) {
                            console.log(`🚫 [${category.name}] 排除包含匹配: ${k}`);
                            return false;
                        }
                        console.log(`🔍 职事信息包含匹配: 原始key="${k}", 清理key="${cleanedKey}"`);
                        return true;
                    }
                    return false;
                } catch (error) {
                    console.warn(`职事信息包含匹配出错 for key: ${k}`, error);
                    return false;
                }
            });

            // 模糊匹配
            const keysForFuzzy = keys
                .filter(k => {
                    try {
                        return dict[k] && dict[k].source;
                    } catch (error) {
                        console.warn(`职事信息模糊匹配过滤出错 for key: ${k}`, error);
                        return false;
                    }
                })
                .map(k => ({
                    originalKey: k,
                    searchKey: dict[k].source === 'zhi_shi' ? cleanKeyForMatching(k) : k
                }));
            
            if (keysForFuzzy.length > 0) {
                const fuse = new Fuse(keysForFuzzy, {
                    keys: ['searchKey'],
                    includeScore: true,
                    threshold: 1.0
                });
                
                const rawFuzzyResults = fuse.search(query);
                
                fuzzyResults = rawFuzzyResults
                    .map(result => ({
                        item: { key: result.item.originalKey },
                        score: result.score
                    }))
                    .filter(result => {
                        try {
                            const k = result.item.key;
                            if (result.score > 0.25) return false;
                            
                            const excluded = isExcluded(query, k, dict[k].content || dict[k], category.name, 'simple');
                            if (excluded) {
                                console.log(`🚫 [${category.name}] 排除模糊匹配: ${k}`);
                                return false;
                            }
                            return true;
                        } catch (error) {
                            console.warn(`职事信息模糊匹配排除检查出错:`, error);
                            return false;
                        }
                    });
            } else {
                fuzzyResults = [];
            }

        } else {
            // 其他分类保持原有逻辑
            try {
                // 精确匹配
                const rawExactMatch = keys.find(k => expandedQueries.includes(k));
                if (rawExactMatch) {
                    const excluded = isExcluded(query, rawExactMatch, dict[rawExactMatch], category.name, 'full');
                    exactMatch = excluded ? null : rawExactMatch;
                    if (excluded) {
                        console.log(`🚫 [${category.name}] 排除精确匹配: ${rawExactMatch}`);
                    }
                } else {
                    exactMatch = null;
                }
                
                // 包含匹配
                const rawContainsMatches = keys.filter(k => expandedQueries.some(q => k.includes(q)));
                containsMatches = rawContainsMatches.filter(k => {
                    const excluded = isExcluded(query, k, dict[k], category.name, 'full'); // 改为 'full'
                    if (excluded) {
                        console.log(`🚫 [${category.name}] 排除包含匹配: ${k}`);
                        return false;
                    }
                    console.log(`📌 [${category.name}] 包含匹配: ${k}`);
                    return true;
                });

                // 模糊匹配
                const fuse = new Fuse(keys.map(k => ({ key: k })), {
                    keys: ['key'],
                    includeScore: true,
                    threshold: 1.0
                });
                
                const rawFuzzyResults = fuse.search(query);
                fuzzyResults = rawFuzzyResults.filter(result => {
                    const k = result.item.key;
                    if (result.score > 0.25) return false;
                    
                    const excluded = isExcluded(query, k, dict[k], category.name, 'full'); // 改为 'full'
                    if (excluded) {
                        console.log(`🚫 [${category.name}] 排除模糊匹配: ${k}`);
                        return false;
                    }
                    return true;
                });
                
            } catch (error) {
                console.warn(`其他分类匹配出错:`, error);
                exactMatch = null;
                containsMatches = [];
                fuzzyResults = [];
            }
        }
        console.log(`🎯 [${category.name}] 精确匹配: ${exactMatch || '无'}`);
        console.log(`🎯 [${category.name}] 包含匹配数量: ${containsMatches.length}`);
        console.log(`🔎 [${category.name}] 模糊匹配共找到 ${fuzzyResults.length} 条候选`);

        const merged = [];

        // 处理精确匹配
        if (exactMatch) {
            const excluded = isExcluded(query, exactMatch, dict[exactMatch], category.name, 'full');
            if (excluded) {
                console.log(`🚫 [${category.name}] 排除精确匹配: ${exactMatch}`);
            } else {
                console.log(`✅ [${category.name}] 精确匹配: ${exactMatch}`);
                merged.push({ key: exactMatch, score: 0, excluded: false });
            }
        }

        // 处理包含匹配
        for (const k of containsMatches) {
            if (exactMatch && k === exactMatch) continue;
            
            if (!merged.some(r => r.key === k)) {
                const excluded = isExcluded(query, k, dict[k], category.name, 'simple');
                if (excluded) {
                    console.log(`🚫 [${category.name}] 排除包含匹配: ${k}`);
                    continue;
                }
                
                console.log(`📌 [${category.name}] 包含匹配: ${k}`);
                merged.push({ key: k, score: 0.1, excluded: false });
            }
        }

        // 处理模糊匹配
        for (const result of fuzzyResults) {
            const targetKey = result.item.key;
            if (result.score > 0.25) continue;
            if (exactMatch && targetKey === exactMatch) continue;
            if (merged.some(r => r.key === targetKey)) continue;

            const excluded = isExcluded(query, targetKey, dict[targetKey], category.name, 'simple');
            if (excluded) continue;

            merged.push({ key: targetKey, score: result.score, excluded: false });
        }

        // 处理值匹配（注解等：在正文简体中搜索）
        for (const k of valueMatches) {
            if (exactMatch && k === exactMatch) continue;
            if (merged.some((r) => r.key === k)) continue;
            const excluded = isExcluded(query, k, dict[k], category.name, 'simple');
            if (excluded) continue;
            console.log(`📄 [${category.name}] 值匹配入列: ${k}`);
            merged.push({ key: k, score: 0.2, excluded: false });
        }

        // 应用三维度综合排序
        let topResults;
        
        if (category.name === '职事信息') {
            // 职事信息特殊排序：书名数据直接放最前面，不参与排序
            const shuMingResults = merged.filter(r => dict[r.key].source === 'shu_ming');
            const zhiShiResults = merged.filter(r => dict[r.key].source === 'zhi_shi');
            
            // 对职事信息数据进行排序
            const sortedZhiShiResults = comprehensiveSortWithDisplayLength(zhiShiResults, query, category.name);
            
            // 书名数据直接放最前面 + 排序后的职事信息数据
            const finalResults = [...shuMingResults, ...sortedZhiShiResults];
            topResults = finalResults.slice(0, 100);
            
            console.log(`📚 书名结果: ${shuMingResults.length} 条（优先显示）`);
            console.log(`📖 职事结果: ${sortedZhiShiResults.length} 条（排序后显示）`);
        } else {
            // 其他分类保持原有排序逻辑
            const sortedResults = comprehensiveSortWithDisplayLength(merged, query, category.name);
            topResults = sortedResults.slice(0, 30);
        }

        if (topResults.length > 0) {
            console.log(`🧩 [${category.name}] 最终展示 ${topResults.length} 条结果`);

            const formatted = topResults.map((r, i) => {
                const k = r.key;
                const v = dict[k];
                return category.render(k, v, i);
            }).join('\n\n');

            appendMessage("AI", formatMessage(formatted), originalInput); 
            appendCopyButton();
            
            return true;
            
        } else {
            console.log(`ℹ️ [${category.name}] 无匹配结果`);
        }
        
        // ✅ 【修改】找到目标分类后，无论是否有结果都要跳出循环
        break;
    }

    return false;
}
    
// ✅ 添加“查看全文”按钮事件：匹配对应 source
// ✅ 完整的 handleViewOriginalClicks 函数
document.addEventListener('click', function(event) {
    const button = event.target.closest('.view-original');
    if (!button) return;
    
    event.stopPropagation();
    event.preventDefault();
    
    console.log("🔘 查看全文按钮被点击 (事件委托)");
    
    const rawTitle = button.dataset.title || 
                    button.dataset.title_2 || 
                    button.dataset.title_3 || 
                    button.dataset.bookKey;
    
    const source = button.dataset.source;
    
    console.log("📘 [事件委托] 原始标题：", rawTitle);
    console.log("🔁 [事件委托] 数据源：", source);

    if (!rawTitle) {
        console.error("❌ 无法获取标题数据！");
        alert("⚠️ 按钮数据异常");
        return;
    }

    // ✅ 目录处理分支
    if (source === 'catalog') {
        console.log("🔍 检测到目录数据源");
        fetchCatalogContent(rawTitle);
        return;
    }

    // ✅ 新增：处理圣经整章的数据源（需要通过2_index.json查找）
    if (source === 'jing_wen_with_index') {
        console.log("🔍 检测到需要通过索引查找的经文数据源:", rawTitle);
        
        // 加载2_index.json并查找对应文件
        fetch('private/jing_wen_html/2_index.json')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`索引文件不存在或无法访问: ${response.status}`);
                }
                return response.json();
            })
            .then(indexData => {
                console.log("✅ 索引文件加载成功");
                console.log("🔍 查找标题:", rawTitle);
                
                // 在索引中查找对应的文件名
                const actualFileName = indexData[rawTitle];
                
                if (!actualFileName) {
                    console.error("❌ 在索引中未找到匹配项:", rawTitle);
                    console.log("📋 可用的索引项:", Object.keys(indexData));
                    alert(`未找到"${rawTitle}"对应的文件\n\n请检查索引文件中是否包含该标题`);
                    return;
                }
                
                console.log("✅ 找到对应文件名:", actualFileName);
                
                // 构建完整的文件路径
                const actualFilePath = `private/jing_wen_html/${actualFileName}`;
                
                // 加载实际的HTML文件
                return fetch(actualFilePath);
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`文件不存在或无法访问: ${response.status}`);
                }
                return response.text();
            })
            .then(html => {
                console.log("✅ HTML文件加载成功");
                
                // 提取HTML中的实际内容，保留格式
                const processedContent = extractHTMLContent(html);
                
                // 显示内容（保留HTML格式）
                showHymnModalRaw(rawTitle, processedContent);
            })
            .catch(error => {
                console.error("❌ 加载失败:", error);
                alert(`⚠️ 无法加载文件：${rawTitle}\n\n可能原因：\n1. 索引文件不存在：private/jing_wen_html/2_index.json\n2. 索引中没有该标题的记录\n3. 对应的HTML文件不存在\n4. 网络问题\n\n错误详情: ${error.message}`);
            });
        
        return;
    }
    // ✅ 新增：处理 private/jing_wen_html/ 路径
    if (source && source.startsWith('private/jing_wen_html/')) {
        console.log("🔍 检测到经文HTML文件路径:", source);
        
        fetch(source)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`文件不存在或无法访问: ${response.status}`);
                }
                return response.text();
            })
            // 替换为：
            .then(html => {
                console.log("✅ HTML文件加载成功");
                
                // 提取HTML中的实际内容，保留格式
                const processedContent = extractHTMLContent(html);
                
                // 对于HTML文件，直接显示内容，不再调用formatMessage
                showHymnModalRaw(rawTitle, processedContent);
            })
            .catch(error => {
                console.error("❌ HTML文件加载失败:", error);
                alert(`⚠️ 无法加载文件：${source}\n\n可能原因：\n1. 文件不存在\n2. 文件路径错误\n3. 网络问题\n\n请检查文件是否存在于指定路径`);
            });
        
        return;
    }

    // 🔄 处理其他数据源的现有逻辑
    const title = convertTraditionalToSimplified(rawTitle);
    console.log("🔁 [事件委托] 繁转简结果：", title);

    const dictMap = {
        'hymns': window.hymns,
        'shi_ge': window.shi_ge,
        'zhu_jie_wen_da': window.zhu_jie_wen_da,
        'jing_jie_wen_da': window.jing_jie_wen_da,
        'bible_verse': window.bibleVerse,
        'xiao_bai_ke': window.xiao_bai_ke
    };

    const dict = dictMap[source];
    if (!dict) {
        alert("⚠️ 未加载字典：" + source);
        return;
    }

    // ... 继续你原有的匹配逻辑
    let matchedKey = null;

    if (source === 'hymns') {
        // 你原有的诗歌匹配逻辑
        const allKeys = Object.keys(dict);
        console.log("🔍 开始在诗歌字典中查找:", title);
        
        if (dict[title]) {
            matchedKey = title;
            console.log("✅ 精确匹配成功:", matchedKey);
        } else {
            matchedKey = allKeys.find(k => k.includes(title));
            if (matchedKey) {
                console.log("✅ 包含匹配成功:", matchedKey);
            } else {
                matchedKey = allKeys.find(k => title.includes(k));
                if (matchedKey) {
                    console.log("✅ 反向包含匹配成功:", matchedKey);
                } else {
                    const cleanTitle = title.replace(/[^\u4e00-\u9fa5\d]/g, '');
                    matchedKey = allKeys.find(k => {
                        const cleanKey = k.replace(/[^\u4e00-\u9fa5\d]/g, '');
                        return cleanKey.includes(cleanTitle) || cleanTitle.includes(cleanKey);
                    });
                    if (matchedKey) {
                        console.log("✅ 模糊匹配成功:", matchedKey);
                    }
                }
            }
        }
    } else {
        matchedKey = title;
    }

    console.log("🔑 最终匹配到的key：", matchedKey);

    if (!matchedKey) {
        alert("⚠️ 未找到原文：" + rawTitle);
        return;
    }

    const raw = dict[matchedKey];
    
    if (!raw || raw === undefined || raw === null || raw === '') {
        console.error("❌ 找不到对应内容或内容为空!");
        alert("⚠️ 内容不可用：" + matchedKey);
        return;
    }
    
    const content = formatMessage(raw);
    showHymnModal(matchedKey, content);
});



// 确保这些变量在文件顶部声明，在任何函数外面
const catalogDataFiles = [
  'private/4_zhi_shi_xin_xi_shu_ming.json',
  'private/4_shi_ge_fen_lei_mu_lu.json',
  'private/4_sheng_jing_fen_lei_mu_lu.json',
];

let combinedCatalogData = null;  // 重要：确保这行在全局作用域
let loadingPromise = null;       // 也添加这个变量

async function loadAndMergeCatalogData() {
  console.log("🚀 loadAndMergeCatalogData 被调用");
  console.log("📦 当前 combinedCatalogData:", combinedCatalogData);
  
  if (combinedCatalogData && Object.keys(combinedCatalogData).length > 0) {
    console.log("✅ 使用已缓存的数据");
    return combinedCatalogData;
  }

  // 如果正在加载中，等待同一个Promise
  if (loadingPromise) {
    console.log("⏳ 等待现有的加载过程...");
    return await loadingPromise;
  }

  // 开始新的加载过程
  loadingPromise = (async () => {
    console.log("🔄 开始新的加载过程");
    combinedCatalogData = {};  // 现在这里应该能正常访问

    for (const filePath of catalogDataFiles) {
      try {
        console.log(`📁 加载文件: ${filePath}`);
        const response = await fetch(filePath);
        
        if (!response.ok) {
          console.warn(`❌ 文件加载失败: ${filePath}，状态: ${response.status}`);
          continue;
        }
        
        const data = await response.json();
        console.log(`✅ 文件加载成功: ${filePath}，键数量: ${Object.keys(data).length}`);
        
        Object.assign(combinedCatalogData, data);
      } catch (err) {
        console.error(`💥 文件加载异常: ${filePath}`, err);
      }
    }

    console.log("🏁 加载完成，总键数量:", Object.keys(combinedCatalogData).length);
    loadingPromise = null;
    return combinedCatalogData;
  })();

  return await loadingPromise;
}

let catalogProcessing = false;

async function fetchCatalogContent(bookKey) {
    if (catalogProcessing) {
        console.log('⚠️ fetchCatalogContent 已在处理中，忽略重复调用');
        return;
    }
    
    catalogProcessing = true;
    
    try {
        const callId = Math.random().toString(36).substr(2, 9);
        console.log(`📚 [${callId}] fetchCatalogContent 开始:`, bookKey);

        const shuMingData = await loadAndMergeCatalogData();
        
        console.log(`📊 [${callId}] 获取到的数据键数量:`, 
            shuMingData ? Object.keys(shuMingData).length : 0);

        if (!shuMingData || Object.keys(shuMingData).length === 0) {
            console.log(`❌ [${callId}] 触发空数据警告`);
            alert('目录数据为空，请稍后重试');
            return;
        }

        console.log(`✅ [${callId}] 数据验证通过，开始匹配`);
        
        const simplifiedKey = convertTraditionalToSimplified(bookKey);
        const keyWithoutPunctuation = simplifiedKey.replace(/[,，:：;；.。!！?？()（）【】《》""'']/g, '');

        let matchedOriginalKey = null;
        let entry = null;

        for (const [jsonKey, jsonValue] of Object.entries(shuMingData)) {
            const jsonKeyWithoutPunctuation = jsonKey.replace(/[,，:：;；.。!！?？()（）【】《》""'']/g, '');

            if (keyWithoutPunctuation === jsonKeyWithoutPunctuation) {
                matchedOriginalKey = jsonKey;
                entry = jsonValue;
                break;
            }
        }

        if (entry) {
            const formattedTitle = formatMessage(matchedOriginalKey);
            const formattedContent = formatMessage(entry);
            showHymnModal(formattedTitle, formattedContent);
        } else {
            alert('未找到目录内容');
        }
    } catch (error) {
        console.error(`💥 加载失败:`, error);
        alert('加载目录失败，请稍后重试');
    } finally {
        setTimeout(() => {
            catalogProcessing = false;
        }, 1000);
    }
}


// 更多按钮
function appendRegenerateButton(originalMessage) {
    const lastBotMessage = history.lastElementChild;
    if (!lastBotMessage || !lastBotMessage.classList.contains('bot')) return;
    const contentDiv = lastBotMessage.querySelector('.content');
    if (!contentDiv) return;

    // ✅ 获取/创建按钮容器
    const btnContainer = ensureButtonGroup(contentDiv);

    // 避免重复插入
    if (btnContainer.querySelector('.regenerate-button')) return;

    const btn = document.createElement("button");
    btn.textContent = translations[selectedLang]?.more || "🔄 更多";
    btn.className = "regenerate-button";

    btn.onclick = async () => {
        console.log("🔄 点击更多，发送原始问题：", originalMessage);
        if (!originalMessage || typeof originalMessage !== 'string') {
            alert("⚠️ 找不到原始提问，无法重新生成");
            return;
        }

        showLoading();

        try {
            const response = await fetch(fixedApiUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: originalMessage })
            });

            removeLoading();
            btn.disabled = false;

            const data = await response.json();
            if (data.success && data.data?.response) {
                appendMessage('AI', data.data.response, originalMessage);
            } else {
                appendMessage('AI', '⚠️ 后台没有返回有效结果');
            }
        } catch (err) {
            removeLoading();
            btn.disabled = false;
            appendMessage('AI', '⚠️ 请求失败，请检查网络');
        }
    };

    btnContainer.appendChild(btn);
}


// ✅ 复制按钮
function appendCopyButton() {
    const lastBotMessage = history.lastElementChild;
    if (!lastBotMessage || !lastBotMessage.classList.contains('bot')) return;
    const contentDiv = lastBotMessage.querySelector('.content');
    if (!contentDiv) return;

    const btnContainer = ensureButtonGroup(contentDiv);
    if (btnContainer.querySelector('.copy-button')) return;

    const btn = document.createElement("button");
    btn.textContent = translations[selectedLang]?.copy || "📋 复制";
    btn.className = "copy-button";

    btn.onclick = () => {
        const messageDiv = lastBotMessage;
        const userMessageDiv = messageDiv?.previousElementSibling;

        let question = '';
        if (userMessageDiv?.classList.contains('user')) {
            question = userMessageDiv.querySelector('.content')?.innerText.trim() || '';
        }

        const clone = contentDiv.cloneNode(true);
        clone.querySelectorAll('button').forEach(btn => btn.remove());
        const paragraphs = Array.from(clone.querySelectorAll('p, h3, h4'));
        const answer = paragraphs.map(p => p.innerText.trim()).filter(Boolean).join('\n\n');

        const fullText = question
            ? `❓ 用户提问：\n${question}\n\n📘 精选回复：\n${answer}`
            : `📘 精选回复：\n${answer}`;

        navigator.clipboard.writeText(fullText).then(() => {
            btn.textContent = translations[selectedLang]?.copied || "✅ 已复制";
            setTimeout(() => (btn.textContent = translations[selectedLang]?.copy || "📋 复制"), 1500);
        });

        console.log("📋 正在复制：", fullText);
    };

    btnContainer.appendChild(btn);
}



// ✅ 先保存原始函数
const originalAppendMessage = appendMessage;

// ✅ 然后重写 appendMessage
appendMessage = function(sender, message, originalUserInput = null) {
    originalAppendMessage(sender, message);  // ✅ 这里才不会报错

    if (sender === 'AI') {
       
        // ✅appendRegenerateButton(originalUserInput);
        appendCopyButton();

        // ✅ 加载 cha_kan_zheng_pian.js 按钮处理
        //  document.querySelectorAll(".zheng-pian-btn").forEach(btn => {
            //  btn.addEventListener("click", () => {
              //    const payload = btn.dataset.payload;
                //  console.log("📤 点击按钮发送内容：", payload);

               //   if (typeof window.handleZhengPianClick === "function") {
                //      window.handleZhengPianClick(payload);
              //    } else {
               //       alert("❌ 模块未加载！");
               //   }
            //  });
        //  });
    }
};


// ✅ 统一的字体调整函数（同时支持缩放和字体大小调整）
let scaleFactor = 1.0;
let currentFontSize = 16; // 默认字体大小

// 主要的字体调整函数
function adjustFontSize(direction) {
    console.log(`🔤 adjustFontSize called with direction: ${direction}`);
    
    try {
        // 方法1：使用CSS transform scale（推荐，兼容性更好）
        const target = document.querySelector('.chat-container');
        if (target) {
            scaleFactor += direction * 0.1;
            scaleFactor = Math.min(Math.max(scaleFactor, 0.8), 1.5);
            
            console.log(`📏 New scale factor: ${scaleFactor}`);
            
            // 优先使用transform，因为兼容性更好
            target.style.transform = `scale(${scaleFactor})`;
            target.style.transformOrigin = 'top center';
            
            // 存储当前缩放值
            localStorage.setItem('fontScaleFactor', scaleFactor.toString());
            
            // 显示临时提示
            showFontAdjustmentFeedback(scaleFactor);
        }
    } catch (error) {
        console.error('❌ Font adjustment error:', error);
        
        // 备用方法：调整根元素字体大小
        try {
            const html = document.documentElement;
            const style = getComputedStyle(html);
            const currentSize = parseFloat(style.fontSize) || 16;
            const newSize = Math.min(24, Math.max(12, currentSize + direction * 2));
            html.style.fontSize = newSize + 'px';
            
            console.log(`📏 Fallback font size: ${currentSize}px -> ${newSize}px`);
            showFontAdjustmentFeedback(newSize / 16);
        } catch (fallbackError) {
            console.error('❌ Fallback font adjustment also failed:', fallbackError);
        }
    }
}

// 显示字体调整反馈
function showFontAdjustmentFeedback(scale) {
    // 移除已存在的反馈元素
    const existingFeedback = document.querySelector('.font-feedback');
    if (existingFeedback) {
        existingFeedback.remove();
    }
    
    // 创建反馈元素
    const feedback = document.createElement('div');
    feedback.className = 'font-feedback';
    feedback.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: rgba(0, 0, 0, 0.8);
        color: white;
        padding: 10px 20px;
        border-radius: 8px;
        font-size: 16px;
        font-weight: bold;
        z-index: 10000;
        pointer-events: none;
        transition: opacity 0.3s ease;
    `;
    
    const percentage = Math.round(scale * 100);
    feedback.textContent = `字体大小: ${percentage}%`;
    
    document.body.appendChild(feedback);
    
    // 2秒后自动移除
    setTimeout(() => {
        feedback.style.opacity = '0';
        setTimeout(() => {
            if (feedback.parentNode) {
                feedback.parentNode.removeChild(feedback);
            }
        }, 300);
    }, 2000);
}

// 页面加载时恢复字体设置
document.addEventListener('DOMContentLoaded', function() {
    const savedScale = localStorage.getItem('fontScaleFactor');
    if (savedScale) {
        scaleFactor = parseFloat(savedScale);
        const target = document.querySelector('.chat-container');
        if (target && scaleFactor !== 1.0) {
            target.style.transform = `scale(${scaleFactor})`;
            target.style.transformOrigin = 'top center';
        }
    }
});

// ✅ 确保全局可访问
window.adjustFontSize = adjustFontSize;

// ✅ 添加手机端触摸事件支持
document.addEventListener('DOMContentLoaded', function() {
    const fontButtons = document.querySelectorAll('.font-controls button');
    
    fontButtons.forEach(button => {
        // 获取原始的onclick属性值
        const onclickAttr = button.getAttribute('onclick');
        
        if (onclickAttr) {
            // 解析onclick中的函数调用
            const match = onclickAttr.match(/adjustFontSize\(([^)]+)\)/);
            if (match) {
                const direction = parseInt(match[1]);
                
                // 移除原始的onclick属性
                button.removeAttribute('onclick');
                
                // 添加现代事件监听器（支持触摸）
                function handleFontAdjust(event) {
                    event.preventDefault();
                    event.stopPropagation();
                    
                    console.log(`🔤 Font button clicked: direction=${direction}`);
                    adjustFontSize(direction);
                    
                    // 添加视觉反馈
                    button.style.transform = 'scale(0.95)';
                    setTimeout(() => {
                        button.style.transform = '';
                    }, 150);
                }
                
                // 同时绑定多种事件，确保兼容性
                button.addEventListener('click', handleFontAdjust, { passive: false });
                button.addEventListener('touchstart', handleFontAdjust, { passive: false });
                
                // 添加键盘支持
                button.addEventListener('keydown', function(event) {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        handleFontAdjust(event);
                    }
                });
                
                console.log(`✅ Enhanced font button: ${button.textContent} (direction: ${direction})`);
            }
        }
    });
});

// ✅ 调试函数
window.debugFontControls = function() {
    console.log('🔍 Font Controls Debug Info:');
    console.log('Current scale factor:', scaleFactor);
    console.log('Chat container element:', document.querySelector('.chat-container'));
    console.log('Font control buttons:', document.querySelectorAll('.font-controls button'));
    
    const target = document.querySelector('.chat-container');
    if (target) {
        console.log('Current transform:', target.style.transform);
        console.log('Current zoom:', target.style.zoom);
    }
    
    // 测试函数
    console.log('Testing adjustFontSize function...');
    if (typeof adjustFontSize === 'function') {
        console.log('✅ adjustFontSize function is available');
    } else {
        console.log('❌ adjustFontSize function is NOT available');
    }
};

console.log('✅ Enhanced font control system loaded');



document.body.addEventListener('click', (e) => {
    const btn = e.target.closest('.zheng-pian-btn');
    if (!btn) return;

    const payload = btn.dataset.payload;
    console.log("📤 按钮点击发送内容：", payload);  // ✅ 你要的打印就在这里

    if (typeof window.handleZhengPianClick === "function") {
        window.handleZhengPianClick(payload);
    } else {
        alert("⚠️ 功能模块未加载");
    }
});


window.adjustFontSize = function (delta) {
  const html = document.documentElement;
  const style = getComputedStyle(html);
  const currentSize = parseFloat(style.fontSize);
  const newSize = Math.min(24, Math.max(12, currentSize + delta));
  html.style.fontSize = newSize + 'px';
};




window.addEventListener("message", function(event) {
  if (event.data?.type === "need-zheng-pian-content") {
    const ctx = window._zheng_pian_tab_context;

    let retries = 0;
    const maxRetries = 20; // 最多等待 2 秒

    const waitInterval = setInterval(() => {
      if (ctx && ctx.targetWindow === event.source && ctx.content) {
        clearInterval(waitInterval);
        event.source.postMessage({ type: "zheng-pian-content", content: ctx.content }, "*");
      } else if (++retries > maxRetries) {
        clearInterval(waitInterval);
        event.source.postMessage({
          type: "zheng-pian-content",
          content: `<div style="text-align:center; padding:2rem; font-size:1.2rem; color:#888;">
            抱歉，尚未准备好内容，请重试。
          </div>`
        }, "*");
      }
    }, 100);
  }
});

(function () {
    const userLang = navigator.language || navigator.userLanguage;
    const isTraditional = userLang.startsWith("zh-TW") || userLang.startsWith("zh-HK") || userLang.startsWith("zh-MO");
    const selectedLang = isTraditional ? "zh-TW" : (translations[userLang] ? userLang : "zh-CN");
    window.selectedLang = selectedLang;

    document.body.setAttribute("data-lang", selectedLang);

    document.querySelectorAll("[data-i18n]").forEach(el => {
        const key = el.getAttribute("data-i18n");
        if (translations[selectedLang][key]) el.textContent = translations[selectedLang][key];
    });

    document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
        const key = el.getAttribute("data-i18n-placeholder");
        if (translations[selectedLang][key]) el.setAttribute("placeholder", translations[selectedLang][key]);
    });

    const sendButton = document.getElementById("send-button");
    const userInput = document.getElementById("user-input");
    const loginModal = document.getElementById("loginModal");

    if (!loginModal) {
        console.error("❌ loginModal 元素未找到！");
        return;
    }

    // 🔒 检查 localStorage 是否已登录
    const isLoggedIn = localStorage.getItem("isLoggedIn") === "true";

    if (isLoggedIn) {
        loginModal.style.display = "none";  // 已登录则直接关闭登录模态
        sendButton.disabled = userInput.value.trim() === '';
    } else {
        loginModal.style.display = "block";  // 未登录则显示登录模态
        sendButton.disabled = true;
    }

    const loginSubmit = document.getElementById("login-submit");
    loginSubmit.addEventListener("click", async () => {
        const username = document.getElementById("login-username").value.trim();
        const password = document.getElementById("login-password").value.trim();

        if (!username || !password) {
            alert("⚠️ 请输入用户名和密码");
            return;
        }

        try {
            const response = await fetch("/private/userdb.json");
            if (!response.ok) {
                throw new Error("无法读取用户数据库");
            }

            const userdb = await response.json();

            if (userdb[username] && userdb[username] === password) {
                // 登录成功，记录 localStorage 状态
                localStorage.setItem("isLoggedIn", "true");
                loginModal.style.display = "none";
                sendButton.disabled = userInput.value.trim() === '';
            } else {
                alert("⚠️ 用户名或密码错误");
            }
        } catch (error) {
            console.error("❌ 验证用户信息出错：", error);
            alert("⚠️ 验证失败，请稍后再试");
        }
    });

    loginModal.addEventListener('click', (event) => {
        if (event.target === loginModal) {
            alert("⚠️ 请先登录！");
        }
    });

    userInput.addEventListener('input', () => {
        if (loginModal.style.display === "none") {
            sendButton.disabled = userInput.value.trim() === '';
        } else {
            sendButton.disabled = true;
        }
    });
})();


// 🔧朗读按钮事件处理函数（使用统一流程）
// 🔧 第一步：在 scripts.js 文件末尾添加 StreamingTTSManager 类
// 🎵 全局音频管理器 - 确保同一时间只有一个音频播放
// 将此代码添加到 scripts.js 文件的开头（在现有代码之前）

class GlobalAudioManager {
    constructor() {
        this.currentInstance = null;
        this.allInstances = new Set();
    }

    // 注册新的音频实例
    register(instance) {
        this.allInstances.add(instance);
        console.log(`🎵 注册音频实例，当前总数: ${this.allInstances.size}`);
    }

    // 注销音频实例
    unregister(instance) {
        this.allInstances.delete(instance);
        if (this.currentInstance === instance) {
            this.currentInstance = null;
        }
        console.log(`🎵 注销音频实例，当前总数: ${this.allInstances.size}`);
    }

    // 请求播放权限（停止其他所有音频）
    requestPlay(instance) {
        console.log(`🎯 请求播放权限`);
        
        // 停止当前播放的音频
        if (this.currentInstance && this.currentInstance !== instance) {
            console.log(`🛑 停止之前的音频实例`);
            this.currentInstance.forceStop();
        }

        // 停止所有其他音频实例
        this.allInstances.forEach(inst => {
            if (inst !== instance && inst.isActive()) {
                console.log(`🛑 停止其他音频实例`);
                inst.forceStop();
            }
        });

        // 设置当前实例
        this.currentInstance = instance;
        console.log(`✅ 播放权限已授予`);
    }

    // 释放播放权限
    releasePlay(instance) {
        if (this.currentInstance === instance) {
            this.currentInstance = null;
            console.log(`🔓 释放播放权限`);
        }
    }

    // 停止所有音频
    stopAll() {
        console.log(`🛑 停止所有音频实例`);
        this.allInstances.forEach(instance => {
            instance.forceStop();
        });
        this.currentInstance = null;
    }

    // 获取当前状态
    getStatus() {
        return {
            totalInstances: this.allInstances.size,
            hasCurrentInstance: !!this.currentInstance,
            currentInstanceActive: this.currentInstance ? this.currentInstance.isActive() : false
        };
    }
}

// 创建全局音频管理器实例
window.globalAudioManager = new GlobalAudioManager();

// 🔧 修改 StreamingTTSManager 类，添加全局管理支持
// 🔧 修复音频播放中断问题 - 替换 StreamingTTSManager 类

// 🔧 修复后的 StreamingTTSManager 类 - 支持请求中断

class StreamingTTSManager {
    constructor(apiUrl, voice = 'Zhiyu') {
        this.apiUrl = apiUrl;
        this.voice = voice;
        this.maxChunkLength = 80;
        this.audioContext = null;
        this.audioQueue = [];
        this.isPlaying = false;
        this.isPaused = false;
        this.currentAudioSource = null;
        this.currentIndex = 0;
        this.onProgress = null;
        this.onComplete = null;
        this.onError = null;
        this.instanceId = Date.now() + Math.random();
        this.totalChunks = 0;
        this.processedChunks = 0;
        this.playbackStarted = false;
        
        // 🆕 新增：用于管理正在进行的请求
        this.activeRequests = new Set(); // 存储正在进行的fetch请求
        this.isDestroyed = false;        // 标记实例是否已销毁
        
        // 注册到全局管理器
        if (window.globalAudioManager) {
            window.globalAudioManager.register(this);
        }
    }

    async initAudioContext() {
        if (!this.audioContext) {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
        
        if (this.audioContext.state === 'suspended') {
            await this.audioContext.resume();
        }
    }

    isActive() {
        return this.isPlaying || this.isPaused || this.audioQueue.length > 0;
    }

    forceStop() {
        console.log(`🛑 强制停止音频实例 ${this.instanceId}`);
        this.stop();
    }

    requestPlayPermission() {
        if (window.globalAudioManager) {
            window.globalAudioManager.requestPlay(this);
        }
    }

    releasePlayPermission() {
        if (window.globalAudioManager) {
            window.globalAudioManager.releasePlay(this);
        }
    }

    chunkText(text) {
        console.log(`📝 开始智能分块，原文长度: ${text.length}`);
        
        if (text.length <= this.maxChunkLength) {
            return [text];
        }

        const chunks = [];
        const paragraphs = text.split(/\n\n+/).filter(p => p.trim());
        
        for (const paragraph of paragraphs) {
            if (paragraph.length <= this.maxChunkLength) {
                chunks.push(paragraph.trim());
                continue;
            }
            
            const sentences = paragraph.match(/[^。！？；。\n]+[。！？；。\n]*/g) || [paragraph];
            
            let currentChunk = '';
            for (const sentence of sentences) {
                const trimmedSentence = sentence.trim();
                if (!trimmedSentence) continue;
                
                if ((currentChunk + trimmedSentence).length <= this.maxChunkLength) {
                    currentChunk += trimmedSentence;
                } else {
                    if (currentChunk) {
                        chunks.push(currentChunk.trim());
                    }
                    
                    if (trimmedSentence.length > this.maxChunkLength) {
                        chunks.push(...this.forceChunk(trimmedSentence));
                        currentChunk = '';
                    } else {
                        currentChunk = trimmedSentence;
                    }
                }
            }
            
            if (currentChunk) {
                chunks.push(currentChunk.trim());
            }
        }

        return chunks.filter(chunk => chunk.length > 0);
    }

    forceChunk(text) {
        const chunks = [];
        for (let i = 0; i < text.length; i += this.maxChunkLength) {
            chunks.push(text.substring(i, i + this.maxChunkLength));
        }
        return chunks;
    }

    // 🔧 修复：支持请求中断的音频块获取函数
    async fetchAudioChunk(text, index) {
        console.log(`🎵 获取音频块 ${index + 1}: "${text.substring(0, 20)}..."`);
        
        // 🆕 检查实例是否已销毁
        if (this.isDestroyed) {
            console.log(`⚠️ 实例已销毁，取消请求: 块 ${index + 1}`);
            throw new Error('Instance destroyed');
        }
        
        try {
            const params = new URLSearchParams({
                text: text,
                voice: this.voice
            });
            
            const url = `${this.apiUrl}/?${params.toString()}`;
            console.log(`📡 请求URL长度: ${url.length}`);
            
            // 🆕 创建AbortController用于中断请求
            const abortController = new AbortController();
            const signal = abortController.signal;
            
            // 🆕 将请求控制器添加到活动请求集合
            this.activeRequests.add(abortController);
            
            // 🆕 设置请求超时（可选，防止请求卡住）
            const timeoutId = setTimeout(() => {
                console.log(`⏰ 请求超时，中断块 ${index + 1}`);
                abortController.abort('timeout');
            }, 30000); // 30秒超时
            
            const response = await fetch(url, { signal });
            
            // 🆕 清除超时定时器
            clearTimeout(timeoutId);
            
            // 🆕 从活动请求集合中移除
            this.activeRequests.delete(abortController);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const arrayBuffer = await response.arrayBuffer();
            
            // 🆕 再次检查实例状态（在长时间异步操作后）
            if (this.isDestroyed) {
                console.log(`⚠️ 实例已销毁，丢弃音频数据: 块 ${index + 1}`);
                throw new Error('Instance destroyed during processing');
            }
            
            const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);
            
            console.log(`✅ 音频块 ${index + 1} 获取成功，时长: ${audioBuffer.duration.toFixed(2)}s`);
            
            return {
                buffer: audioBuffer,
                index: index,
                text: text,
                duration: audioBuffer.duration
            };
            
        } catch (error) {
            // 🆕 从活动请求集合中移除失败的请求
            this.activeRequests.forEach(controller => {
                if (controller.signal.aborted) {
                    this.activeRequests.delete(controller);
                }
            });
            
            if (error.name === 'AbortError' || error.message.includes('destroyed')) {
                console.log(`🚫 音频块 ${index + 1} 请求被中断或实例已销毁`);
                throw new Error('Request aborted or instance destroyed');
            } else {
                console.error(`❌ 音频块 ${index + 1} 获取失败:`, error);
                throw error;
            }
        }
    }

    async processStreamingTTS(text, progressCallback = null, completeCallback = null, errorCallback = null) {
        console.log(`🚀 开始流式TTS处理，文本长度: ${text.length}`);
        
        // 请求播放权限，停止其他音频
        this.requestPlayPermission();
        
        await this.initAudioContext();
        
        this.reset();
        this.onProgress = progressCallback;
        this.onComplete = completeCallback;
        this.onError = errorCallback;
        
        const chunks = this.chunkText(text);
        this.totalChunks = chunks.length;
        this.processedChunks = 0;
        
        console.log(`📋 总计 ${chunks.length} 个音频块`);
        
        // 🔧 关键修复：确保音频队列初始化正确
        this.audioQueue = new Array(chunks.length).fill(null);
        
        this.startStreamingProcess(chunks);
        return true;
    }

    async startStreamingProcess(chunks) {
        console.log(`🔄 开始处理 ${chunks.length} 个音频块`);
        
        // 🔧 修复：立即处理第一个块，确保快速开始播放
        this.processChunkAsync(chunks[0], 0)
            .then(audioData => {
                // 🆕 检查实例状态
                if (this.isDestroyed) {
                    console.log(`⚠️ 实例已销毁，忽略第一个块的结果`);
                    return;
                }
                
                console.log(`✅ 第一个音频块准备完成，开始播放`);
                this.audioQueue[0] = audioData;
                this.processedChunks++;
                
                // 立即开始播放第一个块
                if (!this.isPlaying && !this.isDestroyed) {
                    this.startPlayback();
                }
                
                this.updateProgress();
            })
            .catch(error => {
                if (!this.isDestroyed) {
                    console.error(`❌ 第一个块处理失败:`, error);
                    if (this.onError && !error.message.includes('destroyed')) {
                        this.onError(error);
                    }
                }
            });

        // 处理后续块
        for (let i = 1; i < chunks.length; i++) {
            // 🆕 在每次循环开始时检查实例状态
            if (this.isDestroyed) {
                console.log(`🛑 实例已销毁，停止处理后续块 (从块 ${i + 1} 开始)`);
                break;
            }
            
            // 🔧 修复：添加适当延迟，避免并发过多
            await this.delay(100 * i); // 递增延迟
            
            // 🆕 再次检查实例状态（延迟后）
            if (this.isDestroyed) {
                console.log(`🛑 实例已销毁，跳过块 ${i + 1}`);
                break;
            }
            
            this.processChunkAsync(chunks[i], i)
                .then(audioData => {
                    // 🆕 检查实例状态
                    if (this.isDestroyed) {
                        console.log(`⚠️ 实例已销毁，忽略块 ${i + 1} 的结果`);
                        return;
                    }
                    
                    this.audioQueue[i] = audioData;
                    this.processedChunks++;
                    
                    console.log(`✅ 音频块 ${i + 1} 处理完成 (${this.processedChunks}/${this.totalChunks})`);
                    this.updateProgress();
                    
                    // 检查是否全部完成
                    if (this.processedChunks === this.totalChunks) {
                        console.log(`🎯 所有音频块处理完成`);
                    }
                })
                .catch(error => {
                    if (!this.isDestroyed && !error.message.includes('destroyed')) {
                        console.error(`❌ 块 ${i + 1} 处理失败:`, error);
                        if (this.onError) {
                            this.onError(error);
                        }
                    }
                });
        }
    }

    // 🔧 新增：更新进度的独立方法
    updateProgress() {
        if (this.onProgress && !this.isDestroyed) {
            this.onProgress({
                processed: this.processedChunks,
                total: this.totalChunks,
                percentage: (this.processedChunks / this.totalChunks * 100).toFixed(1),
                currentChunk: this.currentIndex + 1,
                isPlaying: this.isPlaying
            });
        }
    }

    async processChunkAsync(text, index) {
        return await this.fetchAudioChunk(text, index);
    }

    async startPlayback() {
        if (this.isPlaying || this.isDestroyed) {
            console.warn(`⚠️ 播放已在进行中或实例已销毁`);
            return;
        }
        
        console.log('🎵 开始流式播放');
        this.isPlaying = true;
        this.playbackStarted = true;
        this.currentIndex = 0;
        
        await this.playNextChunk();
    }

    async playNextChunk() {
        if (!this.isPlaying || this.isPaused || this.isDestroyed) {
            console.log(`⏸️ 播放暂停、停止或实例已销毁 (playing: ${this.isPlaying}, paused: ${this.isPaused}, destroyed: ${this.isDestroyed})`);
            return;
        }

        console.log(`🔍 尝试播放块 ${this.currentIndex + 1}/${this.totalChunks}`);
        
        // 🔧 修复：增加等待时间和次数，确保音频块准备好
        let waitCount = 0;
        const maxWait = 200; // 增加最大等待次数到20秒
        
        while (!this.audioQueue[this.currentIndex] && waitCount < maxWait && this.isPlaying && !this.isDestroyed) {
            await this.delay(100);
            waitCount++;
            
            if (waitCount % 50 === 0) { // 每5秒打印一次等待日志
                console.log(`⏳ 等待音频块 ${this.currentIndex + 1} 准备中... (${waitCount * 100}ms)`);
            }
        }
        
        // 🆕 再次检查实例状态
        if (this.isDestroyed) {
            console.log(`🛑 实例已销毁，停止播放`);
            return;
        }
        
        const audioData = this.audioQueue[this.currentIndex];
        if (!audioData) {
            console.error(`❌ 音频块 ${this.currentIndex + 1} 超时未准备好，等待了 ${waitCount * 100}ms`);
            
            // 🔧 修复：如果当前块失败，尝试播放下一块
            this.currentIndex++;
            if (this.currentIndex < this.totalChunks && !this.isDestroyed) {
                console.log(`🔄 跳过失败的块，尝试下一块`);
                await this.playNextChunk();
            } else {
                console.log(`⚠️ 所有块都处理完成或失败，结束播放`);
                this.finishPlayback();
            }
            return;
        }
        
        console.log(`🔊 播放音频块 ${this.currentIndex + 1}，时长: ${audioData.duration.toFixed(2)}s`);
        
        // 🔧 修复：确保音频源正确创建和连接
        try {
            // 🆕 再次检查实例状态
            if (this.isDestroyed) {
                console.log(`🛑 实例已销毁，取消播放`);
                return;
            }
            
            this.currentAudioSource = this.audioContext.createBufferSource();
            this.currentAudioSource.buffer = audioData.buffer;
            this.currentAudioSource.connect(this.audioContext.destination);
            
            // 🎚️ 设置播放速度为0.9倍
            this.currentAudioSource.playbackRate.value = 0.9;
            
            // 🔧 关键修复：添加错误处理和更详细的结束逻辑
            this.currentAudioSource.onended = () => {
                // 🆕 检查实例状态
                if (this.isDestroyed) {
                    console.log(`⚠️ 实例已销毁，忽略播放结束事件`);
                    return;
                }
                
                console.log(`✅ 音频块 ${this.currentIndex + 1} 播放完成`);
                this.currentIndex++;
                
                if (this.currentIndex < this.totalChunks && this.isPlaying && !this.isDestroyed) {
                    console.log(`🔄 继续播放下一块 (${this.currentIndex + 1}/${this.totalChunks})`);
                    // 小延迟确保平滑切换
                    setTimeout(() => {
                        if (!this.isDestroyed) {
                            this.playNextChunk();
                        }
                    }, 50);
                } else {
                    console.log(`🎯 所有音频块播放完成`);
                    this.finishPlayback();
                }
            };
            
            this.currentAudioSource.onerror = (error) => {
                if (!this.isDestroyed) {
                    console.error(`❌ 音频块 ${this.currentIndex + 1} 播放出错:`, error);
                    this.currentIndex++;
                    if (this.currentIndex < this.totalChunks && this.isPlaying) {
                        this.playNextChunk();
                    } else {
                        this.finishPlayback();
                    }
                }
            };
            
            // 🔧 关键：确保音频上下文处于运行状态
            if (this.audioContext.state === 'suspended') {
                await this.audioContext.resume();
            }
            
            // 🆕 最后一次检查实例状态
            if (this.isDestroyed) {
                console.log(`🛑 实例已销毁，取消音频播放`);
                return;
            }
            
            this.currentAudioSource.start(0);
            console.log(`▶️ 音频块 ${this.currentIndex + 1} 开始播放`);
            
        } catch (error) {
            if (!this.isDestroyed) {
                console.error(`❌ 创建音频源失败:`, error);
                this.currentIndex++;
                if (this.currentIndex < this.totalChunks && this.isPlaying) {
                    await this.playNextChunk();
                } else {
                    this.finishPlayback();
                }
            }
        }
    }

    // 🔧 新增：播放完成的独立方法
    finishPlayback() {
        if (this.isDestroyed) {
            console.log(`⚠️ 实例已销毁，跳过播放完成处理`);
            return;
        }
        
        console.log('🏁 播放流程完成');
        this.isPlaying = false;
        this.playbackStarted = false;
        this.releasePlayPermission();
        
        if (this.onComplete) {
            this.onComplete();
        }
    }

    pause() {
        if (!this.isPlaying || this.isPaused) return;
        
        console.log('⏸️ 暂停播放');
        this.isPaused = true;
        if (this.currentAudioSource) {
            this.currentAudioSource.stop();
        }
    }

    resume() {
        if (!this.isPaused) return;
        
        console.log('▶️ 恢复播放');
        this.isPaused = false;
        this.playNextChunk();
    }

    stop() {
        console.log('🛑 停止播放');
        this.isPlaying = false;
        this.isPaused = false;
        this.playbackStarted = false;
        
        if (this.currentAudioSource) {
            try {
                this.currentAudioSource.stop();
            } catch (error) {
                console.warn('停止音频源时出错:', error);
            }
            this.currentAudioSource = null;
        }
        
        this.releasePlayPermission();
        this.reset();
    }

    reset() {
        this.audioQueue = [];
        this.currentIndex = 0;
        this.processedChunks = 0;
        this.totalChunks = 0;
        this.playbackStarted = false;
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // 🔧 修复：增强的销毁方法，支持中断正在进行的请求
    destroy() {
        console.log(`🗑️ 销毁音频实例 ${this.instanceId}`);
        
        // 🆕 标记实例为已销毁状态
        this.isDestroyed = true;
        
        // 🆕 中断所有正在进行的请求
        console.log(`🚫 中断 ${this.activeRequests.size} 个正在进行的请求`);
        this.activeRequests.forEach(controller => {
            try {
                controller.abort('Instance destroyed');
                console.log(`✅ 已中断一个请求`);
            } catch (error) {
                console.warn('中断请求时出错:', error);
            }
        });
        this.activeRequests.clear();
        
        // 停止播放和清理音频资源
        this.stop();
        
        // 从全局管理器注销
        if (window.globalAudioManager) {
            window.globalAudioManager.unregister(this);
        }
        
        // 🆕 清理音频上下文（如果需要）
        if (this.audioContext && this.audioContext.state !== 'closed') {
            try {
                // 注意：关闭AudioContext会影响其他音频，通常不建议关闭
                // this.audioContext.close();
            } catch (error) {
                console.warn('关闭AudioContext时出错:', error);
            }
        }
        
        console.log(`✅ 音频实例 ${this.instanceId} 销毁完成`);
    }

    // 🔧 新增：获取播放状态的详细信息
    getDetailedStatus() {
        return {
            isPlaying: this.isPlaying,
            isPaused: this.isPaused,
            playbackStarted: this.playbackStarted,
            currentIndex: this.currentIndex,
            totalChunks: this.totalChunks,
            processedChunks: this.processedChunks,
            queueLength: this.audioQueue.length,
            progress: this.totalChunks > 0 ? (this.currentIndex / this.totalChunks * 100).toFixed(1) : 0,
            isDestroyed: this.isDestroyed,
            activeRequestsCount: this.activeRequests.size
        };
    }
}

// 🔧 修改 appendReadButtonToMessageContent 函数，添加清理逻辑
function appendReadButtonToMessageContent(contentDiv, rawMessage) {
    const TTS_ENDPOINT = "https://x2vi7ecfqk3q7qqfpruvveqkj40vbnxc.lambda-url.us-east-1.on.aws";
    
    const readBtn = document.createElement("button");
    readBtn.textContent = translations[selectedLang]?.read || "🔊 朗读";
    readBtn.className = "read-button";

    let ttsManager = null;
    let isProcessing = false;

    readBtn.addEventListener("click", async () => {
        if (isProcessing) {
            // 停止当前处理
            if (ttsManager) {
                ttsManager.destroy();
            }
            ttsManager = null;
            isProcessing = false;
            readBtn.textContent = translations[selectedLang]?.read || "🔊 朗读";
            return;
        }

        // 开始流式处理
        readBtn.textContent = "⏳ 准备中...";
        isProcessing = true;

        try {
            // ✅ 添加 await，因为 prepareTextForReading 现在是 async
            const finalText = await prepareTextForReading(rawMessage);
            if (!finalText) {
                throw new Error('文本准备失败');
            }

            // 🎯 创建新的TTS管理器会自动停止其他音频
            ttsManager = new StreamingTTSManager(TTS_ENDPOINT, "Zhiyu");

            await ttsManager.processStreamingTTS(
                finalText,
                // 进度回调
                (progress) => {
                    if (progress.isPlaying) {
                        readBtn.textContent = `⏸️ 暂停 (${progress.percentage}%)`;
                    } else {
                        readBtn.textContent = `📥 加载中 (${progress.percentage}%)`;
                    }
                },
                // 完成回调
                () => {
                    readBtn.textContent = translations[selectedLang]?.read || "🔊 朗读";
                    isProcessing = false;
                    if (ttsManager) {
                        ttsManager.destroy();
                        ttsManager = null;
                    }
                },
                // 错误回调
                (error) => {
                    console.error('流式TTS错误:', error);
                    readBtn.textContent = "❌ 播放失败";
                    isProcessing = false;
                    if (ttsManager) {
                        ttsManager.destroy();
                        ttsManager = null;
                    }
                    setTimeout(() => {
                        readBtn.textContent = translations[selectedLang]?.read || "🔊 朗读";
                    }, 2000);
                }
            );

        } catch (error) {
            console.error('启动流式TTS失败:', error);
            readBtn.textContent = "❌ 启动失败";
            isProcessing = false;
            if (ttsManager) {
                ttsManager.destroy();
                ttsManager = null;
            }
            setTimeout(() => {
                readBtn.textContent = translations[selectedLang]?.read || "🔊 朗读";
            }, 2000);
        }
    });    

    // 🎯 清理函数 - 确保彻底清理
    readBtn.stopAndCleanup = function() {
        if (ttsManager) {
            ttsManager.destroy();
            ttsManager = null;
        }
        isProcessing = false;
        readBtn.textContent = translations[selectedLang]?.read || "🔊 朗读";
    };

    // 兼容性保持
    readBtn._audioInstance = null;
    readBtn._audioUrl = null;

    // 获取或创建按钮容器
    let buttonGroup = contentDiv.querySelector(".button-group");
    if (!buttonGroup) {
        buttonGroup = document.createElement("div");
        buttonGroup.className = "button-group";
        contentDiv.appendChild(buttonGroup);
    }

    if (buttonGroup.querySelector('.read-button')) return;

    const copyBtn = buttonGroup.querySelector('.copy-button');
    if (copyBtn && copyBtn.nextSibling) {
        buttonGroup.insertBefore(readBtn, copyBtn.nextSibling);
    } else {
        buttonGroup.appendChild(readBtn);
    }
}

// 4. 添加语音可用性测试函数
async function testTTSVoice(voiceId) {
    const TTS_ENDPOINT = "https://x2vi7ecfqk3q7qqfpruvveqkj40vbnxc.lambda-url.us-east-1.on.aws";
    
    try {
        const params = new URLSearchParams({
            text: "测试",
            voice: voiceId
        });
        
        const url = `${TTS_ENDPOINT}/?${params.toString()}`;
        console.log(`🧪 测试语音: ${voiceId}`);
        
        const response = await fetch(url);
        
        if (response.ok) {
            console.log(`✅ 语音 ${voiceId} 可用`);
            return true;
        } else {
            console.log(`❌ 语音 ${voiceId} 不可用: ${response.status} ${response.statusText}`);
            return false;
        }
    } catch (error) {
        console.log(`❌ 语音 ${voiceId} 测试失败:`, error);
        return false;
    }
}

// 5. 批量测试可用语音
async function findAvailableVoices() {
    const voicesToTest = [
        'Zhiyu',      // 女声
        'Zhiyong',    // 男声
        'Kangkang',   // 男声
        'Hiujin',     // 台湾女声
        'Hiuwan'      // 香港女声
    ];
    
    console.log('🧪 开始测试可用语音...');
    const availableVoices = [];
    
    for (const voice of voicesToTest) {
        const isAvailable = await testTTSVoice(voice);
        if (isAvailable) {
            availableVoices.push(voice);
        }
        // 添加延迟避免请求过于频繁
        await new Promise(resolve => setTimeout(resolve, 1000));
    }
    
    console.log('✅ 可用语音列表:', availableVoices);
    return availableVoices;
}

// 6. 导出测试函数
window.testTTSVoice = testTTSVoice;
window.findAvailableVoices = findAvailableVoices;



// 🎯 可选：添加全局停止所有音频的快捷方式
window.stopAllAudio = function() {
    if (window.globalAudioManager) {
        window.globalAudioManager.stopAll();
        console.log('🛑 已停止所有音频播放');
    }
};

// 🎯 页面卸载时清理所有音频
window.addEventListener('beforeunload', function() {
    if (window.globalAudioManager) {
        window.globalAudioManager.stopAll();
    }
});

// 🔧 统一的朗读文本处理函数（提取经节和提取文本）
async function prepareTextForReading(rawMessage) {
    console.log(`🎙️ 开始准备朗读文本`);
    
    try {
        // 步骤1: 提取纯文本 - ✅ 添加 await
        const pureText = await extractPureTextForReading(rawMessage);
        if (!pureText) {
            console.warn('⚠️ 纯文本提取失败');
            return '';
        }
        
        // 步骤2: 格式转换（经节引用等） - ✅ 现在 pureText 是字符串
        const processedText = processTextForReadingFromMessage(pureText);
        
        console.log(`🎯 朗读文本准备完成，最终文本长度: ${processedText.length}`);
        return processedText;
        
    } catch (error) {
        console.error('❌ 朗读文本准备失败:', error);
        return '';
    }
}



// ========== 朗读功能提取经节==========
function processTextForReadingFromMessage(text) {
    const bookMap = {
        '创':'创世记','出':'出埃及记','利':'利未记','民':'民数记','申':'申命记','书':'约书亚记','士':'士师记','得':'路得记',
        '撒上':'撒母耳记上','撒下':'撒母耳记下','王上':'列王纪上','王下':'列王纪下','代上':'历代志上','代下':'历代志下',
        '拉':'以斯拉记','尼':'尼希米记','斯':'以斯帖记','伯':'约伯记','诗':'诗篇','箴':'箴言','传':'传道书','歌':'雅歌',
        '赛':'以赛亚书','耶':'耶利米书','哀':'耶利米哀歌','结':'以西结书','但':'但以理书','何':'何西阿书','珥':'约珥书',
        '摩':'阿摩司书','俄':'俄巴底亚书','拿':'约拿书','弥':'弥迦书','鸿':'那鸿书','哈':'哈巴谷书','番':'西番雅书',
        '该':'哈该书','亚':'撒迦利亚书','玛':'玛拉基书','太':'马太福音','可':'马可福音','路':'路加福音','约':'约翰福音',
        '徒':'使徒行传','罗':'罗马书','林前':'哥林多前书','林后':'哥林多后书','加':'加拉太书','弗':'以弗所书','腓':'腓立比书',
        '西':'歌罗西书','帖前':'帖撒罗尼迦前书','帖后':'帖撒罗尼迦后书','提前':'提摩太前书','提后':'提摩太后书','多':'提多书',
        '门':'腓利门书','来':'希伯来书','雅':'雅各书','彼前':'彼得前书','彼后':'彼得后书','约壹':'约翰一书','约贰':'约翰二书',
        '约叁':'约翰三书','犹':'犹大书','启':'启示录'
    };

    // 简化格式转标准格式映射表（用于朗读）
    const simplifiedToStandardMap = {
        // 21-99: 简化格式转为标准格式
        '二一': '二十一', '二二': '二十二', '二三': '二十三', '二四': '二十四', '二五': '二十五',
        '二六': '二十六', '二七': '二十七', '二八': '二十八', '二九': '二十九',
        '三一': '三十一', '三二': '三十二', '三三': '三十三', '三四': '三十四', '三五': '三十五',
        '三六': '三十六', '三七': '三十七', '三八': '三十八', '三九': '三十九',
        '四一': '四十一', '四二': '四十二', '四三': '四十三', '四四': '四十四', '四五': '四十五',
        '四六': '四十六', '四七': '四十七', '四八': '四十八', '四九': '四十九',
        '五一': '五十一', '五二': '五十二', '五三': '五十三', '五四': '五十四', '五五': '五十五',
        '五六': '五十六', '五七': '五十七', '五八': '五十八', '五九': '五十九',
        '六一': '六十一', '六二': '六十二', '六三': '六十三', '六四': '六十四', '六五': '六十五',
        '六六': '六十六', '六七': '六十七', '六八': '六十八', '六九': '六十九',
        '七一': '七十一', '七二': '七十二', '七三': '七十三', '七四': '七十四', '七五': '七十五',
        '七六': '七十六', '七七': '七十七', '七八': '七十八', '七九': '七十九',
        '八一': '八十一', '八二': '八十二', '八三': '八十三', '八四': '八十四', '八五': '八十五',
        '八六': '八十六', '八七': '八十七', '八八': '八十八', '八九': '八十九',
        '九一': '九十一', '九二': '九十二', '九三': '九十三', '九四': '九十四', '九五': '九十五',
        '九六': '九十六', '九七': '九十七', '九八': '九十八', '九九': '九十九',
        
        // 整十数保持不变
        '一十': '十', '二十': '二十', '三十': '三十', '四十': '四十', '五十': '五十', 
        '六十': '六十', '七十': '七十', '八十': '八十', '九十': '九十',
        
        // 简化格式转为传统格式（用于朗读）
        '一〇〇': '一百', '一〇一': '一百零一', '一〇二': '一百零二', '一〇三': '一百零三', 
        '一〇四': '一百零四', '一〇五': '一百零五', '一〇六': '一百零六', '一〇七': '一百零七', 
        '一〇八': '一百零八', '一〇九': '一百零九', '一一〇': '一百一十', '一一一': '一百一十一', 
        '一一二': '一百一十二', '一一三': '一百一十三', '一一四': '一百一十四', '一一五': '一百一十五', 
        '一一六': '一百一十六', '一一七': '一百一十七', '一一八': '一百一十八', '一一九': '一百一十九', 
        '一二〇': '一百二十', '一二一': '一百二十一', '一二二': '一百二十二', '一二三': '一百二十三', 
        '一二四': '一百二十四', '一二五': '一百二十五', '一二六': '一百二十六', '一二七': '一百二十七', 
        '一二八': '一百二十八', '一二九': '一百二十九', '一三〇': '一百三十', '一三一': '一百三十一', 
        '一三二': '一百三十二', '一三三': '一百三十三', '一三四': '一百三十四', '一三五': '一百三十五', 
        '一三六': '一百三十六', '一三七': '一百三十七', '一三八': '一百三十八', '一三九': '一百三十九', 
        '一四〇': '一百四十', '一四一': '一百四十一', '一四二': '一百四十二', '一四三': '一百四十三', 
        '一四四': '一百四十四', '一四五': '一百四十五', '一四六': '一百四十六', '一四七': '一百四十七', 
        '一四八': '一百四十八', '一四九': '一百四十九', '一五〇': '一百五十'
    };

    const cnNumMap = {'零':0,'〇':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10};
    
    // 增强的中文数字转换函数
    function chineseToStandardReading(text) {
        console.log(`🔢 转换中文数字: "${text}"`);
        
        // 1. 首先检查是否在简化格式映射表中
        if (simplifiedToStandardMap[text]) {
            const result = simplifiedToStandardMap[text];
            console.log(`✅ 简化格式转换: "${text}" -> "${result}"`);
            return result;
        }
        
        // 2. 如果是阿拉伯数字，直接返回
        if (/^\d+$/.test(text)) {
            console.log(`✅ 阿拉伯数字保持: "${text}"`);
            return String(Number(text));
        }
        
        // 3. 处理标准中文数字格式
        if (text === '十') return '十';
        if (text.startsWith('十')) return '十' + (cnNumMap[text[1]] ? cnNumMap[text[1]] : text[1]);
        if (text.length === 2 && text[1] === '十') return (cnNumMap[text[0]] ? cnNumMap[text[0]] : text[0]) + '十';
        if (text.includes('十')) {
            const parts = text.split('十');
            const left = cnNumMap[parts[0]] || parts[0];
            const right = parts[1] ? (cnNumMap[parts[1]] || parts[1]) : '';
            return left + '十' + right;
        }
        
        // 4. 其他情况保持原样
        console.log(`✅ 保持原样: "${text}"`);
        return text;
    }

    // 移除括号内容
    text = text.replace(/（[^）]*）|\([^)]*\)/g, '');
    
    const bookPattern = Object.keys(bookMap).join('|');
    
    // 扩展正则表达式以支持多种模式
    // 模式1: 创二二1 (简化中文数字格式)
    // 模式2: 创110章1节 (阿拉伯数字+章字格式)
    // 模式3: 创一1 (标准中文数字格式)
    const combinedPattern = new RegExp(
        `(${bookPattern})` +                                    // 书名简写
        `(?:` +                                                 // 开始非捕获组
            `([一二三四五六七八九十〇零]+)(\\d[\\d~\\-～－–—,，；;]*)` +   // 模式1&3: 中文章节+数字节
            `|` +                                               // 或者
            `(\\d+)章(\\d+)(?:节)?` +                           // 模式2: 数字章+章字+数字节+(可选节字)
        `)`,                                                    // 结束非捕获组
        'g'
    );

    let newText = text.replace(combinedPattern, (match, book, chapterChinese, verse1, chapterArabic, verse2) => {
        console.log(`🔍 匹配到经节引用: ${match}`);
        console.log(`📖 解析结果: 书名="${book}", 中文章="${chapterChinese}", 节1="${verse1}", 阿拉伯章="${chapterArabic}", 节2="${verse2}"`);
        
        const fullBook = bookMap[book] || book;
        let result;
        
        if (chapterChinese && verse1) {
            // 模式1&3: 创二二1 或 创一1 (处理中文数字)
            const standardChapter = chineseToStandardReading(chapterChinese);
            console.log(`📊 模式1&3处理: 中文章节"${chapterChinese}" -> 标准格式"${standardChapter}"`);
            
            if (verse1) {
                const verseClean = verse1.replace(/[~\-～－–—]/g, '至');
                result = `${fullBook}${standardChapter}章${verseClean}节……`;
            } else {
                result = `${fullBook}${standardChapter}章`;
            }
        } else if (chapterArabic && verse2) {
            // 模式2: 创110章1节 (处理阿拉伯数字)
            const chapterNum = chineseToStandardReading(chapterArabic);
            console.log(`📊 模式2处理: 阿拉伯章节"${chapterArabic}" -> "${chapterNum}"`);
            
            result = `${fullBook}${chapterNum}章${verse2}节……`;
        } else {
            // 备用处理
            result = match;
        }
        
        console.log(`✅ 最终转换: "${match}" -> "${result}"`);
        return result;
    });

    // 替换全角空格为句号
    newText = newText.replace(/\u3000/g, '。');

    console.log(`🎯 朗读文本处理完成:`);
    console.log(`   原文: "${text.substring(0, 50)}${text.length > 50 ? '...' : ''}"`);
    console.log(`   处理后: "${newText.substring(0, 50)}${newText.length > 50 ? '...' : ''}"`);
    
    return newText;
}



// ========== 朗读文本提取纯文本 ==============================================================================================================================================================================================
// 全局变量存储替换映射
let pollyReplacementMap = null;

// 异步加载替换映射文件
async function loadPollyReplacementMap() {
    if (pollyReplacementMap !== null) {
        return pollyReplacementMap;
    }
    
    try {
        const response = await fetch('/private/polly_replacement_map.json');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        pollyReplacementMap = await response.json();
        console.log(`📋 成功加载Polly替换映射，共${Object.keys(pollyReplacementMap).length}条规则`);
        return pollyReplacementMap;
    } catch (error) {
        console.error('❌ 加载Polly替换映射失败:', error);
        pollyReplacementMap = {}; // 设置为空对象避免重复加载
        return {};
    }
}

// 应用Polly替换规则
function applyPollyReplacements(text, replacementMap) {
    if (!text || !replacementMap || Object.keys(replacementMap).length === 0) {
        return text;
    }
    
    let processedText = text;
    let replacementCount = 0;
    
    // 按照键的长度降序排列，优先处理较长的匹配项
    const sortedKeys = Object.keys(replacementMap).sort((a, b) => b.length - a.length);
    
    for (const original of sortedKeys) {
        const replacement = replacementMap[original];
        if (processedText.includes(original)) {
            const beforeReplace = processedText;
            processedText = processedText.replaceAll(original, replacement);
            if (beforeReplace !== processedText) {
                replacementCount++;
                console.log(`🔄 Polly替换: "${original}" → "${replacement}"`);
            }
        }
    }
    
    if (replacementCount > 0) {
        console.log(`✅ Polly替换完成，共应用${replacementCount}条规则`);
    }
    
    return processedText;
}

async function extractPureTextForReading(rawMessage) {
    console.log(`🧹 开始提取纯文本，原始消息长度: ${rawMessage ? rawMessage.length : 0}`);
    console.log(`📝 原始消息预览: ${rawMessage ? rawMessage.substring(0, 200) : 'null'}`);
    
    if (!rawMessage || typeof rawMessage !== 'string') {
        console.warn('⚠️ 无效的输入消息');
        return '';
    }

    // 🆕 加载Polly替换映射
    const replacementMap = await loadPollyReplacementMap();

    try {
        // ✅ 移除HTML中的sup标签
        function removeSuperscripts(html) {
            console.log("🔍 removeSuperscripts调用 - 输入长度:", html.length);
            console.log("🔍 输入内容预览:", html.substring(0, 100));
            
            let cleaned = html;
            
            // 移除HTML中的sup标签及其内容
            const supMatches = html.match(/<sup[^>]*>.*?<\/sup>/gi);
            if (supMatches) {
                console.log("🎯 发现HTML sup标签:", supMatches);
                cleaned = cleaned.replace(/<sup[^>]*>.*?<\/sup>/gi, '');
                cleaned = cleaned.replace(/<sup[^>]*\/>/gi, '');
            }
            
            console.log("✂️ 清理后长度:", cleaned.length);
            console.log("✂️ 清理后预览:", cleaned.substring(0, 100));
            
            console.log(`🗑️ sup移除完成，移除前: ${html.length}, 移除后: ${cleaned.length}`);
            return cleaned;
        }

        // 1. 创建临时DOM容器
        const tempDiv = document.createElement("div");
        
        // 2. 处理原始消息，移除sup标签
        console.log("🔧 开始处理原始消息...");
        const cleanedMessage = removeSuperscripts(rawMessage);
        console.log("🔧 插入DOM前的消息长度:", cleanedMessage.length);
        tempDiv.innerHTML = cleanedMessage;

        // 3. 移除DOM中剩余的sup元素
        const remainingSups = tempDiv.querySelectorAll('sup');
        if (remainingSups.length > 0) {
            console.log(`🗑️ DOM中发现${remainingSups.length}个sup元素，移除之`);
            remainingSups.forEach(sup => sup.remove());
        }

        // 🎯 4. 改进：智能处理 verse-number 内容
        const verseNumbers = tempDiv.querySelectorAll('.verse-number');
        if (verseNumbers.length > 0) {
            console.log(`🔢 发现${verseNumbers.length}个verse-number元素，智能处理中`);
            verseNumbers.forEach(vn => {
                const content = vn.textContent.trim();
                console.log(`📍 检查verse-number内容: "${content}"`);
                
                // 检查是否为 数字:数字 格式（如 1:1, 12:34 等）
                const versePattern = /^\d{1,3}:\d{1,3}$/;
                
                if (versePattern.test(content)) {
                    // 如果是经文格式（数字:数字），则完全移除
                    console.log(`🗑️ 移除经文引用格式: "${content}"`);
                    vn.remove();
                } else {
                    // 如果不是经文格式，完全保留原内容
                    console.log(`✅ 保留非经文格式内容: "${content}"`);
                    // 不做任何修改，保持原样
                }
            });
        }

        // 🎯 5. 新增：处理 outline 元素，移除经文引用部分
        const outlineElements = tempDiv.querySelectorAll('.outline, [class*="outline"]');
        if (outlineElements.length > 0) {
            console.log(`📋 发现${outlineElements.length}个outline元素，处理经文引用`);
            outlineElements.forEach(outline => {
                const originalText = outline.textContent;
                
                // 查找"一"、"二"、"三"等中文数字开始的经文引用
                // 匹配模式：空格 + 中文数字/阿拉伯数字 + 可能的内容
                const cleanedText = originalText.replace(/\s+[一二三四五六七八九十\d]+[^\s]*.*$/, '');
                
                if (cleanedText !== originalText) {
                    console.log(`📝 outline清理: "${originalText}" → "${cleanedText}"`);
                    outline.textContent = cleanedText;
                } else {
                    console.log(`📝 outline无需清理: "${originalText}"`);
                }
            });
        }

        // 6. 移除其他不需要朗读的元素
        tempDiv.querySelectorAll('button, script, style, .button-group').forEach(el => {
            el.remove();
        });

        let finalText = '';

        // 7. 特殊情况：如果没有<p>标签，直接提取整个容器的文本
        if (tempDiv.querySelectorAll('p').length === 0) {
            let directText = tempDiv.innerText.trim();
            
            // 🎯 修复：为直接提取的文本添加句号（处理多段落情况）
            if (directText) {
                // 按换行符分割成段落
                const paragraphs = directText.split(/\n+/).filter(p => p.trim());
                
                // 为每个段落添加句号
                const processedParagraphs = paragraphs.map(paragraph => {
                    const trimmed = paragraph.trim();
                    if (trimmed && !trimmed.endsWith('。') && !trimmed.endsWith('.') && 
                        !trimmed.endsWith('！') && !trimmed.endsWith('？')) {
                        return trimmed + '。';
                    }
                    return trimmed;
                });
                
                directText = processedParagraphs.join('\n\n');
                console.log(`📄 直接提取文本已处理段落并添加句号，段落数: ${processedParagraphs.length}`);
            }
            
            finalText = directText;
            console.log(`📄 直接提取文本: "${finalText.substring(0, 100)}${finalText.length > 100 ? '...' : ''}"`);
        } else {
            // 8. 提取所有段落的纯文本内容
            const paragraphs = Array.from(tempDiv.querySelectorAll('p'));
            const textParts = paragraphs
                .map(p => {
                    let text = p.innerText.trim();
                    
                    // 🎯 新增：为每个段落添加句号
                    if (text && !text.endsWith('。') && !text.endsWith('.') && 
                        !text.endsWith('！') && !text.endsWith('？')) {
                        text += '。';
                    }
                    
                    console.log(`📄 提取段落: "${text.substring(0, 50)}${text.length > 50 ? '...' : ''}"`);
                    return text;
                })
                .filter(Boolean); // 过滤掉空字符串

            // 9. 如果没有找到段落，尝试提取整个容器的文本
            if (textParts.length === 0) {
                let fallbackText = tempDiv.innerText.trim();
                
                // 🎯 修复：为备用文本添加句号（处理多段落情况）
                if (fallbackText) {
                    // 按换行符分割成段落
                    const paragraphs = fallbackText.split(/\n+/).filter(p => p.trim());
                    
                    // 为每个段落添加句号
                    const processedParagraphs = paragraphs.map(paragraph => {
                        const trimmed = paragraph.trim();
                        if (trimmed && !trimmed.endsWith('。') && !trimmed.endsWith('.') && 
                            !trimmed.endsWith('！') && !trimmed.endsWith('？')) {
                            return trimmed + '。';
                        }
                        return trimmed;
                    });
                    
                    fallbackText = processedParagraphs.join('\n\n');
                    console.log(`🔄 备用文本已处理段落并添加句号，段落数: ${processedParagraphs.length}`);
                }
                
                finalText = fallbackText;
                console.log(`🔄 使用备用文本提取: "${finalText.substring(0, 50)}${finalText.length > 50 ? '...' : ''}"`);
            } else {
                // 10. 用双换行符连接所有段落
                finalText = textParts.join('\n\n');
            }
        }

        // 🆕 11. 应用Polly替换规则
        console.log(`🔄 开始应用Polly替换规则...`);
        finalText = applyPollyReplacements(finalText, replacementMap);
        
        console.log(`✅ 纯文本提取完成:`);
        console.log(`  总字符数: ${finalText.length}`);
        console.log(`  文本预览: "${finalText.substring(0, 100)}${finalText.length > 100 ? '...' : ''}"`);
        
        return finalText;

    } catch (error) {
        console.error('❌ 纯文本提取过程中出错:', error);
        
        // 错误情况下的备用处理
        try {
            const tempDiv = document.createElement("div");
            let cleanedFallback = rawMessage.replace(/<sup[^>]*>.*?<\/sup>/gi, '')
                                           .replace(/<sup[^>]*\/>/gi, '');
            tempDiv.innerHTML = cleanedFallback;
            
            // 应用新的排除规则到备用处理
            tempDiv.querySelectorAll('sup').forEach(el => el.remove());
            
            // 🎯 改进：备用处理中也应用智能verse-number处理
            tempDiv.querySelectorAll('.verse-number').forEach(vn => {
                const content = vn.textContent.trim();
                const versePattern = /^\d{1,3}:\d{1,3}$/;
                
                if (versePattern.test(content)) {
                    // 如果是经文格式，移除
                    vn.remove();
                } else {
                    // 如果不是经文格式，完全保留
                    // 不做任何修改
                }
            });
            
            // 处理outline元素
            tempDiv.querySelectorAll('.outline, [class*="outline"]').forEach(outline => {
                const originalText = outline.textContent;
                const cleanedText = originalText.replace(/\s+[一二三四五六七八九十\d]+[^\s]*.*$/, '');
                outline.textContent = cleanedText;
            });
            
            let fallbackText = tempDiv.innerText || tempDiv.textContent || '';
            
            // 🎯 修复：为错误处理的备用文本也添加多段落句号处理
            if (fallbackText) {
                // 按换行符分割成段落
                const paragraphs = fallbackText.split(/\n+/).filter(p => p.trim());
                
                // 为每个段落添加句号
                const processedParagraphs = paragraphs.map(paragraph => {
                    const trimmed = paragraph.trim();
                    if (trimmed && !trimmed.endsWith('。') && !trimmed.endsWith('.') && 
                        !trimmed.endsWith('！') && !trimmed.endsWith('？')) {
                        return trimmed + '。';
                    }
                    return trimmed;
                });
                
                fallbackText = processedParagraphs.join('\n\n');
                console.log(`🚨 错误处理备用文本已处理段落并添加句号，段落数: ${processedParagraphs.length}`);
            }
            
            // 🆕 对备用文本也应用Polly替换
            fallbackText = applyPollyReplacements(fallbackText, replacementMap);
            
            console.log(`🚨 使用备用文本提取: "${fallbackText.substring(0, 50)}"`);
            return fallbackText.trim();
        } catch (fallbackError) {
            console.error('❌ 备用文本提取也失败:', fallbackError);
            return rawMessage || '';
        }
    }
}

// 3. 为全局提供一个快捷停止函数
window.stopAllAudioAndCloseModals = function() {
    console.log('🛑 停止所有音频并关闭所有模态框');
    
    // 停止所有音频
    if (window.globalAudioManager) {
        window.globalAudioManager.stopAll();
    }
    
    // 关闭所有模态框
    const allModals = document.querySelectorAll('.modal[style*="display: block"]');
    allModals.forEach(modal => {
        modal.style.display = 'none';
        if (modal.parentNode) {
            modal.parentNode.removeChild(modal);
        }
    });
    
    console.log(`✅ 已关闭 ${allModals.length} 个模态框并停止所有音频`);
};

// 4. 可选：添加键盘快捷键支持（Ctrl+Shift+S 停止所有音频）
document.addEventListener('keydown', function(event) {
    if (event.ctrlKey && event.shiftKey && event.key === 'S') {
        event.preventDefault();
        window.stopAllAudioAndCloseModals();
        alert('已停止所有音频播放');
    }
});

// 5. 修改现有的模态框事件监听器，确保ESC键也能停止音频
// 在您现有的ESC键处理函数中添加音频停止逻辑：

function handleEscapeKey(event) {
    if (event.key === 'Escape') {
        const allModals = document.querySelectorAll('.modal[style*="display: block"]');
        const topModal = allModals[allModals.length - 1];
        if (topModal && topModal.id === modalId) {
            // 🎯 关键：在关闭模态框前停止音频
            if (window.globalAudioManager) {
                window.globalAudioManager.stopAll();
                console.log('🛑 ESC键触发：停止所有音频');
            }
            closeCurrentModal();
        }
    }
}

// 6. 页面可见性变化时的处理（用户切换到其他标签页时暂停音频）
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        // 页面不可见时暂停音频（可选功能）
        console.log('📱 页面切换到后台');
        // 如果您希望切换标签页时暂停音频，取消下面的注释
        // if (window.globalAudioManager && window.globalAudioManager.currentInstance) {
        //     window.globalAudioManager.currentInstance.pause();
        //     console.log('⏸️ 后台暂停音频');
        // }
    } else {
        console.log('📱 页面回到前台');
        // 可以在这里添加恢复播放的逻辑（如果需要）
    }
});

// 7. 优化的全局音频管理器，添加更多控制方法
if (window.globalAudioManager) {
    // 添加暂停所有音频的方法
    window.globalAudioManager.pauseAll = function() {
        console.log('⏸️ 暂停所有音频');
        this.allInstances.forEach(instance => {
            if (instance.isActive() && instance.isPlaying) {
                instance.pause();
            }
        });
    };
    
    // 添加恢复所有音频的方法
    window.globalAudioManager.resumeAll = function() {
        console.log('▶️ 恢复所有音频');
        if (this.currentInstance && this.currentInstance.isPaused) {
            this.currentInstance.resume();
        }
    };
    
    // 添加获取播放状态的方法
    window.globalAudioManager.getPlayingStatus = function() {
        const status = {
            totalInstances: this.allInstances.size,
            hasCurrentInstance: !!this.currentInstance,
            isPlaying: false,
            isPaused: false,
            currentProgress: 0
        };
        
        if (this.currentInstance) {
            status.isPlaying = this.currentInstance.isPlaying;
            status.isPaused = this.currentInstance.isPaused;
            if (this.currentInstance.getDetailedStatus) {
                const details = this.currentInstance.getDetailedStatus();
                status.currentProgress = details.progress;
                status.currentChunk = details.currentIndex + 1;
                status.totalChunks = details.totalChunks;
            }
        }
        
        return status;
    };
}

// 8. 在控制台提供调试命令
window.audioDebug = {
    stop: () => window.stopAllAudioAndCloseModals(),
    pause: () => window.globalAudioManager?.pauseAll(),
    resume: () => window.globalAudioManager?.resumeAll(),
    status: () => window.globalAudioManager?.getPlayingStatus(),
    help: () => {
        console.log(`
🎵 音频调试命令：
• audioDebug.stop()   - 停止所有音频并关闭模态框
• audioDebug.pause()  - 暂停所有音频
• audioDebug.resume() - 恢复音频播放
• audioDebug.status() - 查看播放状态
• Ctrl+Shift+S        - 快捷键停止所有音频
        `);
    }
};

console.log('🎵 音频控制增强功能已加载，输入 audioDebug.help() 查看可用命令');

// 9. 自动检测长时间播放并提示用户
let longPlaybackTimer = null;

if (window.globalAudioManager) {
    const originalRequestPlay = window.globalAudioManager.requestPlay;
    window.globalAudioManager.requestPlay = function(instance) {
        // 清除之前的计时器
        if (longPlaybackTimer) {
            clearTimeout(longPlaybackTimer);
        }
        
        // 设置新的计时器（5分钟后提示）
        longPlaybackTimer = setTimeout(() => {
            if (this.currentInstance && this.currentInstance.isActive()) {
                console.log('⏰ 音频已播放超过5分钟');
                // 可以在这里添加用户提示（可选）
                // if (confirm('音频已播放较长时间，是否停止？')) {
                //     this.stopAll();
                // }
            }
        }, 5 * 60 * 1000); // 5分钟
        
        // 调用原始方法
        originalRequestPlay.call(this, instance);
    };
}






let selectedCategory = null;
window.__setSelectedCategory = (v) => { selectedCategory = v; };

document.getElementById("category-toggle").addEventListener("click", () => {
  document.getElementById("category-options").classList.toggle("hidden");
});

document.querySelectorAll("#category-options button").forEach(btn => {
  btn.addEventListener("click", () => {
    selectedCategory = btn.dataset.category;
    const toggleBtn = document.getElementById("category-toggle");
    toggleBtn.textContent = selectedCategory;
    toggleBtn.classList.add("active");
    document.getElementById("category-options").classList.add("hidden");
    console.log("当前分类切换为：", selectedCategory);
  });
});

// ========== 经文功能处理模块 ==========// ============ 图表的显示逻辑按钮 ============// ============ 图表的显示逻辑按钮 ============// ============ 图表的显示逻辑按钮 ============// ============ 图表的显示逻辑按钮 ============// ============ 图表的显示逻辑按钮 ============// ============ 图表的显示逻辑按钮 ============// ============ 图表的显示逻辑按钮 ============// ============ 图表的显示逻辑按钮 ============// ============ 图表的显示逻辑按钮 ============// ============ 图表的显示逻辑按钮 ============// ============ 图表的显示逻辑按钮 ============// ============ 图表的显示逻辑按钮 ============// ============ 图表的显示逻辑按钮 ============// ============ 图表的显示逻辑按钮 ============// ============ 图表的显示逻辑按钮 ============// ============ 图表的显示逻辑按钮 ============
// 1. 首先在你的 scripts.js 文件末尾添加以下章节导航功能：
// 章节导航函数
// 同时确保你的 navigateChapter 函数是这样的完整版本：
window.navigateChapter = async function(direction, currentTitle) {
    console.log(`🔄 通过索引导航请求: ${direction}, 当前章节: ${currentTitle}`);
    
    try {
        // 解析当前章节信息
        const chapterInfo = parseChapterTitle(currentTitle);
        if (!chapterInfo) {
            console.error("❌ 无法解析章节信息:", currentTitle);
            alert("无法识别当前章节格式");
            return;
        }
        
        // 计算目标章节
        const targetChapter = direction === 'next' ? 
            chapterInfo.chapterNum + 1 : 
            chapterInfo.chapterNum - 1;
            
        if (targetChapter < 1) {
            alert("已经是第一章了");
            return;
        }
        
        // 构建目标标题（用作索引key）
        const targetTitle = `${chapterInfo.bookName}第${ARABIC_TO_CHINESE[targetChapter]}章`;
        console.log(`🎯 目标标题（索引key）: ${targetTitle}`);
        
        // 通过索引文件查找实际文件名
        const indexResponse = await fetch('private/jing_wen_html/2_index.json');
        if (!indexResponse.ok) {
            throw new Error(`索引文件加载失败: HTTP ${indexResponse.status}`);
        }
        
        const indexData = await indexResponse.json();
        console.log("✅ 索引文件加载成功");
        
        // 在索引中查找对应的实际文件名
        const actualFileName = indexData[targetTitle];
        
        if (!actualFileName) {
            console.log(`⚠️ 索引中未找到: ${targetTitle}，尝试直接访问文件`);
            // 可以在这里添加备用逻辑，或者直接返回
            return;
        }
        
        console.log(`✅ 找到对应文件名: ${actualFileName}`);
        
        // 构建实际的文件路径
        const actualFilePath = `private/jing_wen_html/${actualFileName}`;
        console.log(`📁 实际文件路径: ${actualFilePath}`);
        
        // 加载实际的HTML文件
        const response = await fetch(actualFilePath);
        if (!response.ok) {
            if (response.status === 404) {
                alert(`${targetTitle} 文件不存在: ${actualFileName}`);
            } else {
                throw new Error(`HTTP ${response.status}`);
            }
            return;
        }
        
        const html = await response.text();
        
        // 提取HTML内容并更新当前模态框
        const processedContent = extractHTMLContent(html);
        updateModalContentRaw(targetTitle, processedContent);
        
        console.log(`✅ 成功导航到: ${targetTitle}`);
        
    } catch (error) {
        console.error("❌ 章节导航失败:", error);
        alert(`加载章节失败: ${error.message}`);
    }
};

// 解析章节标题
function parseChapterTitle(title) {
    // 匹配格式：创世记第一章、出埃及记第二十二章等
    const match = title.match(/^(.+?)第(.+?)章$/);
    if (!match) {
        return null;
    }
    
    const bookName = match[1];
    const chapterChinese = match[2];
    const chapterNum = chineseToNumber(chapterChinese);
    
    return {
        bookName: bookName,
        chapterChinese: chapterChinese,
        chapterNum: chapterNum
    };
}

// 中文数字转阿拉伯数字
// ✅ 根据你的数据格式，修正 chineseToNumber 函数
function chineseToNumber(chinese) {
    // 你的数据使用的特殊格式映射
    const specialMap = {
        // 100-109 (一〇〇格式)
        '一〇〇': 100, '一〇一': 101, '一〇二': 102, '一〇三': 103, '一〇四': 104,
        '一〇五': 105, '一〇六': 106, '一〇七': 107, '一〇八': 108, '一〇九': 109,
        
        // 110-119 (一一〇格式)
        '一一〇': 110, '一一一': 111, '一一二': 112, '一一三': 113, '一一四': 114,
        '一一五': 115, '一一六': 116, '一一七': 117, '一一八': 118, '一一九': 119,
        
        // 120-129 (一二〇格式)
        '一二〇': 120, '一二一': 121, '一二二': 122, '一二三': 123, '一二四': 124,
        '一二五': 125, '一二六': 126, '一二七': 127, '一二八': 128, '一二九': 129,
        
        // 130-139 (一三〇格式)
        '一三〇': 130, '一三一': 131, '一三二': 132, '一三三': 133, '一三四': 134,
        '一三五': 135, '一三六': 136, '一三七': 137, '一三八': 138, '一三九': 139,
        
        // 140-150 (一四〇格式)
        '一四〇': 140, '一四一': 141, '一四二': 142, '一四三': 143, '一四四': 144,
        '一四五': 145, '一四六': 146, '一四七': 147, '一四八': 148, '一四九': 149,
        '一五〇': 150
    };
    
    // 标准格式映射（1-99）
    const standardMap = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
        '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15,
        '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20,
        '二十一': 21, '二十二': 22, '二十三': 23, '二十四': 24, '二十五': 25,
        '二十六': 26, '二十七': 27, '二十八': 28, '二十九': 29, '三十': 30,
        '三十一': 31, '三十二': 32, '三十三': 33, '三十四': 34, '三十五': 35,
        '三十六': 36, '三十七': 37, '三十八': 38, '三十九': 39, '四十': 40,
        '四十一': 41, '四十二': 42, '四十三': 43, '四十四': 44, '四十五': 45,
        '四十六': 46, '四十七': 47, '四十八': 48, '四十九': 49, '五十': 50,
        '五十一': 51, '五十二': 52, '五十三': 53, '五十四': 54, '五十五': 55,
        '五十六': 56, '五十七': 57, '五十八': 58, '五十九': 59, '六十': 60,
        '六十一': 61, '六十二': 62, '六十三': 63, '六十四': 64, '六十五': 65,
        '六十六': 66, '六十七': 67, '六十八': 68, '六十九': 69, '七十': 70,
        '七十一': 71, '七十二': 72, '七十三': 73, '七十四': 74, '七十五': 75,
        '七十六': 76, '七十七': 77, '七十八': 78, '七十九': 79, '八十': 80,
        '八十一': 81, '八十二': 82, '八十三': 83, '八十四': 84, '八十五': 85,
        '八十六': 86, '八十七': 87, '八十八': 88, '八十九': 89, '九十': 90,
        '九十一': 91, '九十二': 92, '九十三': 93, '九十四': 94, '九十五': 95,
        '九十六': 96, '九十七': 97, '九十八': 98, '九十九': 99
    };
    
    // 先检查特殊格式，再检查标准格式
    return specialMap[chinese] || standardMap[chinese] || parseInt(chinese) || 1;
}


// 更新模态框内容

/** 聊天/API/Bot 用：只取 body 正文，不含 style（弹窗仍用 extractHTMLContent） */
/** 恢复本专用字体转码失败时的乱码修复（U+FFFD + 字母 → 正确汉字） */
function fixRecoveryBibleGlyphCorruption(text) {
    if (!text || typeof text !== 'string' || !text.includes('\uFFFD')) return text;
    const map = { k: '祂', q: '痲', F: '镕', Z: '繸', m: '醡' };
    return text.replace(/\uFFFD(.)/g, (match, ch) => map[ch] || match);
}

function applyAnnotationInlineStyles(root) {
    if (!root || !root.querySelectorAll) return;
    const supStyle = 'color:#e74c3c;font-weight:bold;font-size:0.75em;vertical-align:super;';
    const noteStyle = 'color:#2d5016;font-weight:bold;';

    root.querySelectorAll('.verse-text sup, .verse-content sup, sup.clickable-sup').forEach((el) => {
        el.setAttribute('style', supStyle);
    });
    root.querySelectorAll('.note-number').forEach((el) => {
        el.setAttribute('style', noteStyle);
    });
}

function extractChatHTMLContent(html) {
    try {
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        const body = doc.querySelector('body');
        if (body) {
            const bodyClone = body.cloneNode(true);
            bodyClone.querySelectorAll('script').forEach((script) => script.remove());
            applyAnnotationInlineStyles(bodyClone);
            return fixRecoveryBibleGlyphCorruption(bodyClone.innerHTML.trim());
        }
    } catch (error) {
        console.error('extractChatHTMLContent 失败:', error);
    }
    return fixRecoveryBibleGlyphCorruption(String(html)
        .replace(/<style[\s\S]*?<\/style>/gi, '')
        .replace(/<script[\s\S]*?<\/script>/gi, '')
        .replace(/<head[\s\S]*?<\/head>/gi, ''));
}

function extractHTMLContent(html) {
    try {
        console.log("🔍 开始处理HTML内容，保留原有格式");
        
        // 创建一个临时的DOM解析器
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        
        // 提取所有CSS样式
        const styles = doc.querySelectorAll('style, link[rel="stylesheet"]');
        let cssContent = '';
        
        styles.forEach(style => {
            if (style.tagName === 'STYLE') {
                cssContent += style.innerHTML + '\n';
            } else if (style.tagName === 'LINK') {
                // 对于外部CSS文件，我们暂时保留link标签
                cssContent += style.outerHTML + '\n';
            }
        });
        
        // 获取body内容
        const body = doc.querySelector('body');
        let bodyContent = '';
        
        if (body) {
            // 克隆body内容，移除script标签但保留其他所有内容
            const bodyClone = body.cloneNode(true);
            const scripts = bodyClone.querySelectorAll('script');
            scripts.forEach(script => script.remove());
            
            bodyContent = bodyClone.innerHTML;
        } else {
            // 如果没有body标签，尝试获取其他容器的内容
            const containers = doc.querySelectorAll('main, article, .content, .container');
            if (containers.length > 0) {
                bodyContent = containers[0].outerHTML;
            } else {
                // 最后的备选方案：移除head和script，保留其他所有内容
                const allContent = doc.documentElement.innerHTML;
                bodyContent = allContent
                    .replace(/<head>[\s\S]*?<\/head>/gi, '')
                    .replace(/<script[\s\S]*?<\/script>/gi, '')
                    .replace(/<\/?body[^>]*>/gi, '')
                    .replace(/<\/?html[^>]*>/gi, '');
            }
        }
        
        // 构建完整的格式化内容
        let finalContent = '';
        
        // 如果有CSS样式，添加到内容中
        if (cssContent.trim()) {
            finalContent += `<style>\n${cssContent}</style>\n`;
        }
        
        // 添加body内容
        finalContent += bodyContent;
        
        console.log("✅ HTML内容处理完成，保留了原有格式");
        console.log("📄 内容预览:", finalContent.substring(0, 300) + "...");
        
        return fixRecoveryBibleGlyphCorruption(finalContent);
        
    } catch (error) {
        console.error("❌ HTML内容处理失败:", error);
        // 如果处理失败，返回原始HTML但移除危险的script标签
        return fixRecoveryBibleGlyphCorruption(html.replace(/<script[\s\S]*?<\/script>/gi, ''));
    }
}

// 完整的 showHymnModalRaw 函数，包含所有功能按钮：

// 🔧 完整的 showHymnModalRaw 函数
// 🔧 完整的 showHymnModalRaw 函数
function showHymnModalRaw(title, content) {
    const userLang = navigator.language || navigator.userLanguage;
    const isTraditional = userLang.startsWith("zh-TW") || userLang.startsWith("zh-HK") || userLang.startsWith("zh-MO");
    const selectedLang = isTraditional ? "zh-TW" : "zh-CN";

    if (isTraditional && typeof convertToTraditional === "function") {
        title = convertToTraditional(title);
        // 注意：这里不转换content，因为它包含HTML标签
    }

    // 创建模态框
    const modalId = `infoModal_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const modal = document.createElement("div");
    modal.id = modalId;
    modal.className = "modal";
    
    const existingModals = document.querySelectorAll('.modal[style*="display: block"]');
    const baseZIndex = 1000;
    const zIndex = baseZIndex + existingModals.length;
    const modalLevel = existingModals.length;
    
    const heightPercentage = 100 - (modalLevel * 1);
    const minHeight = 70;
    const finalHeight = Math.max(heightPercentage, minHeight);
    
    const topDistances = {
        0: '0dvh', 1: '2dvh', 2: '0dvh', 3: '3dvh'  // 顶部间距随层级递增
    };
    const topDistance = topDistances[modalLevel] || `${modalLevel * 1}dvh`;
    modal.style.zIndex = zIndex;
    
    if (modalLevel > 0) {
        modal.style.setProperty('--modal-height', `${finalHeight}%`);
        modal.style.setProperty('--modal-top', topDistance);
        modal.classList.add('layered-modal');
    } else {
        modal.style.setProperty('--modal-top', topDistance);
    }
    
    document.body.appendChild(modal);
    let contentHeight;
    if (modalLevel === 2) {
        contentHeight = '100dvh';
    } else {
        // 让模态框从底部开始，高度为 finalHeight
        contentHeight = `${finalHeight}vh`;
    }
    
    // 检查是否是章节格式，决定是否显示导航按钮
    const isChapterFormat = /第.+章$/.test(title);
    const navigationButtons = isChapterFormat ? `
        <div class="chapter-navigation" style="display: flex; gap: 10px; margin-left: auto;">
            <button onclick="navigateChapter('prev', '${title}')" style="padding: 5px 10px; background: #007cba; color: white; border: none; border-radius: 3px; cursor: pointer;">上一章</button>
            <button onclick="navigateChapter('next', '${title}')" style="padding: 5px 10px; background: #007cba; color: white; border: none; border-radius: 3px; cursor: pointer;">下一章</button>
        </div>
    ` : '';

    // ✅ 修改：移除朗读按钮HTML，稍后通过统一函数添加
    modal.innerHTML = `
        <div class="modal-content" style="
            ${modalLevel > 0 ? `height: ${contentHeight}; max-height: ${contentHeight};` : `height: ${contentHeight}; max-height: ${contentHeight};`}
            margin-top: ${topDistance};
        ">
            <div class="modal-header" style="display: flex; align-items: center; justify-content: space-between;">
                <button class="close">${translations[selectedLang]?.close || "关闭"}</button>
                <div style="display: flex; align-items: center; gap: 10px;">
                    ${navigationButtons}
                    <div class="modal-tools">
                        <button class="copy-modal-content">${translations[selectedLang]?.copy || "📋 复制"}</button>
                    </div>
                </div>
            </div>
            <h3 class="modal-title">${title}</h3>
            <div class="modal-body" style="overflow-y: auto; max-height: calc(100% - 120px);">${content}</div>
        </div>`;
    modal.style.display = 'block';

    // ✅ 新增：使用统一函数添加朗读按钮
    const modalBody = modal.querySelector('.modal-body');
    const rawText = modalBody?.innerText || content;
    
    // 找到modal-tools容器
    let modalTools = modal.querySelector('.modal-tools');
    if (!modalTools) {
        modalTools = document.createElement('div');
        modalTools.className = 'modal-tools';
        const headerDiv = modal.querySelector('.modal-header > div:last-child');
        if (headerDiv) {
            headerDiv.appendChild(modalTools);
        }
    }
    
    // 使用统一函数添加朗读按钮
    appendReadButtonToMessageContent(modalTools, content); 

    // 🔧 修复：关闭函数只关闭当前模态框，并恢复下层模态框的高度和位置
    function closeCurrentModal() {
        console.log(`🔒 关闭模态框 ${modalId}`);
        
        // ✅ 停止当前模态框中所有朗读按钮的音频播放
        const readButtons = modal.querySelectorAll('.read-button');
        readButtons.forEach(btn => {
            // 触发停止事件，让统一朗读函数处理音频清理
            if (btn._audioInstance) {
                btn._audioInstance.pause();
                if (btn._audioUrl) {
                    URL.revokeObjectURL(btn._audioUrl);
                }
                btn._audioInstance = null;
                btn._audioUrl = null;
                btn.textContent = translations[selectedLang]?.read || "🔊 朗读";
                console.log('🛑 已停止模态框中的朗读音频');
            }
        });
        // 🎯 新增：全局停止所有音频（确保彻底清理）
        if (window.globalAudioManager) {
            window.globalAudioManager.stopAll();
            console.log('🛑 全局停止所有音频播放');
        }
                
        // 隐藏并移除当前模态框
        modal.style.display = 'none';
        if (modal.parentNode) {
            modal.parentNode.removeChild(modal);
        }
        
        // ✨ 新增：重新计算剩余模态框的层次样式和顶端距离
        const remainingModals = document.querySelectorAll('.modal[style*="display: block"]');
        remainingModals.forEach((remainingModal, index) => {
            const newHeight = 100 - (index * 0.7);
            const finalNewHeight = Math.max(newHeight, 70);
            const newTopDistance = topDistances[index] || `${10 + index * 1}dvh`;
            const newContentHeight = `calc(${finalNewHeight}vh - ${newTopDistance})`;
            
            if (index > 0) {
                remainingModal.style.setProperty('--modal-height', `${finalNewHeight}%`);
                remainingModal.style.setProperty('--modal-top', newTopDistance);
                const modalContent = remainingModal.querySelector('.modal-content');
                if (modalContent) {
                    modalContent.style.height = newContentHeight;
                    modalContent.style.maxHeight = newContentHeight;
                    modalContent.style.marginTop = newTopDistance;
                }
            } else {
                // 底层模态框保持第一层的样式
                remainingModal.style.setProperty('--modal-top', topDistances[0] || '10dvh');
                remainingModal.classList.remove('layered-modal');
                const modalContent = remainingModal.querySelector('.modal-content');
                if (modalContent) {
                    const firstLayerHeight = `calc(88vh - ${topDistances[0] || '10dvh'})`;
                    modalContent.style.height = firstLayerHeight;
                    modalContent.style.maxHeight = firstLayerHeight;
                    modalContent.style.marginTop = topDistances[0] || '10dvh';
                }
            }
        });
        
        // 🔧 修复：重新聚焦到下一个可见的模态框
        if (remainingModals.length > 0) {
            const topModal = remainingModals[remainingModals.length - 1];
            topModal.focus();
        }
    }

    // 🔧 修复：为关闭按钮绑定独立的事件处理器
    modal.querySelector('.close').addEventListener('click', closeCurrentModal);

    // 🔧 修复：点击模态框背景只关闭当前模态框
    modal.addEventListener('click', (event) => {
        if (event.target === modal) {
            closeCurrentModal();
        }
    });

    // 🔧 修复：ESC键只关闭最顶层的模态框
    function handleEscapeKey(event) {
        if (event.key === 'Escape') {
            const allModals = document.querySelectorAll('.modal[style*="display: block"]');
            const topModal = allModals[allModals.length - 1];
            if (topModal && topModal.id === modalId) {
                closeCurrentModal();
            }
        }
    }
    
    document.addEventListener('keydown', handleEscapeKey);
    
    // 🔧 修复：模态框关闭时移除ESC键监听器
    const originalClose = closeCurrentModal;
    closeCurrentModal = function() {
        document.removeEventListener('keydown', handleEscapeKey);
        originalClose();
    };

    // 复制功能
    modal.querySelector('.copy-modal-content').onclick = function () {
        const titleText = modal.querySelector('.modal-title')?.innerText || '';
        const contentText = modal.querySelector('.modal-body')?.innerText || '';
        const fullText = `${titleText}\n\n${contentText}`;
        navigator.clipboard.writeText(fullText).then(() => {
            const btn = modal.querySelector('.copy-modal-content');
            btn.textContent = translations[selectedLang]?.copied || "已复制";
            setTimeout(() => (btn.textContent = translations[selectedLang]?.copy || "📋 复制"), 1500);
        });
    };
}

window.navigateChapterRaw = async function(direction, currentTitle) {
    console.log(`🔄 HTML格式导航请求: ${direction}, 当前章节: ${currentTitle}`);
    
    try {
        // 解析当前章节信息
        const chapterInfo = parseChapterTitle(currentTitle);
        if (!chapterInfo) {
            console.error("❌ 无法解析章节信息:", currentTitle);
            alert("无法识别当前章节格式");
            return;
        }
        
        // 计算目标章节
        const targetChapter = direction === 'next' ? 
            chapterInfo.chapterNum + 1 : 
            chapterInfo.chapterNum - 1;
            
        if (targetChapter < 1) {
            alert("已经是第一章了");
            return;
        }
        
        // 构建目标文件路径
        const targetTitle = `${chapterInfo.bookName}第${ARABIC_TO_CHINESE[targetChapter]}章`;
        const targetPath = `private/jing_wen_html/${targetTitle}.html`;
        
        console.log(`🎯 目标章节: ${targetTitle}`);
        console.log(`📁 目标路径: ${targetPath}`);
        
        // 尝试加载目标章节
        const response = await fetch(targetPath);
        if (!response.ok) {
            if (response.status === 404) {
                alert(`${targetTitle} 不存在或尚未录入`);
            } else {
                throw new Error(`HTTP ${response.status}`);
            }
            return;
        }
        
        const html = await response.text();
        
        // 提取HTML内容，保留格式
        const processedContent = extractHTMLContent(html);
        
        // 更新当前模态框内容（HTML格式版本）
        updateModalContentRaw(targetTitle, processedContent);
        
        console.log(`✅ 成功导航到: ${targetTitle}，保留HTML格式`);
        
    } catch (error) {
        console.error("❌ 章节导航失败:", error);
        alert(`加载章节失败: ${error.message}`);
    }
};


// 专门用于HTML内容的模态框更新函数：
// ✅ 正确的唯一的 updateModalContentRaw 函数：
function updateModalContentRaw(newTitle, newContent) {
    console.log(`🔧 开始更新模态框: ${newTitle}`);
    
    const activeModals = document.querySelectorAll('.modal[style*="display: block"]');
    if (activeModals.length === 0) {
        console.error("❌ 没有找到活动的模态框");
        return;
    }
    
    const currentModal = activeModals[activeModals.length - 1];
    
    // 更新标题
    const titleElement = currentModal.querySelector('.modal-title');
    if (titleElement) {
        titleElement.textContent = newTitle;
        console.log(`✅ 标题已更新为: ${newTitle}`);
    }
    
    // 直接使用新内容，保留HTML格式
    const bodyElement = currentModal.querySelector('.modal-body');
    if (bodyElement) {
        bodyElement.innerHTML = newContent;
        console.log(`✅ 内容已更新`);
    }
    
    // 🔧 关键修复：更新导航按钮，确保使用 navigateChapter
    const navButtons = currentModal.querySelectorAll('.chapter-navigation button');
    console.log(`🔍 找到 ${navButtons.length} 个导航按钮`);
    
    navButtons.forEach((btn, index) => {
        const buttonText = btn.textContent;
        console.log(`🔧 处理按钮 ${index + 1}: "${buttonText}"`);
        
        if (buttonText === '上一章') {
            const newOnclick = `navigateChapter('prev', '${newTitle}')`;
            btn.setAttribute('onclick', newOnclick);
            console.log(`✅ 上一章按钮已更新: ${newOnclick}`);
        } else if (buttonText === '下一章') {
            const newOnclick = `navigateChapter('next', '${newTitle}')`;
            btn.setAttribute('onclick', newOnclick);
            console.log(`✅ 下一章按钮已更新: ${newOnclick}`);
        }
    });
    
    console.log(`✅ 模态框内容已更新为: ${newTitle}，保留了HTML格式`);
}

// ========== 经文功能处理模块 ==========

// ========== 注解功能处理模块 ==========


// 缓存索引数据，避免重复加载
let zhuJieIndex = null;
let indexLoadPromise = null;

// 全局事件监听器：处理所有可点击上标的点击事件
document.addEventListener('click', function(event) {
    const supButton = event.target.closest('.clickable-sup');
    if (!supButton) return;
    
    event.preventDefault();
    event.stopPropagation();
    
    console.log('🔘 点击了上标按钮');
    
    handleZhuJieClick(supButton);
});

// 支持键盘操作
document.addEventListener('keydown', function(event) {
    if ((event.key === 'Enter' || event.key === ' ') && 
        event.target.classList.contains('clickable-sup')) {
        event.preventDefault();
        handleZhuJieClick(event.target);
    }
});

// 主处理函数：处理注解点击事件
function handleZhuJieClick(supElement) {
    console.log('🎯 开始处理注解点击');
    
    // 1. 获取当前页面的 MAIN_TITLE
    const mainTitleElement = document.querySelector('h1.main-title');
    if (!mainTitleElement) {
        console.error('❌ 未找到页面标题元素');
        alert('未找到页面标题，无法加载注解');
        return;
    }
    
    // 2. 找到包含这个上标的 verse 元素
    const verseElement = supElement.closest('.verse');
    if (!verseElement) {
        console.error('❌ 未找到所属的经文节点');
        alert('未找到经文节点，无法加载注解');
        return;
    }
    
    // 3. 获取该节的 verse-number
    const verseNumberElement = verseElement.querySelector('.verse-number');
    if (!verseNumberElement) {
        console.error('❌ 未找到经文编号');
        alert('未找到经文编号，无法加载注解');
        return;
    }
    
    // 4. 计算请求内容
    const mainTitle = mainTitleElement.textContent || mainTitleElement.innerText;
    const cleanTitle = mainTitle.replace(/\s+/g, ''); // 去除所有空格
    const verseNumber = verseNumberElement.textContent || verseNumberElement.innerText;
    
    // 提取冒号后的内容（节号）
    const colonIndex = verseNumber.indexOf(':');
    const verseNum = colonIndex !== -1 ? verseNumber.substring(colonIndex + 1) : verseNumber;
    
    // 构建最终请求内容：清理后标题 + 节号 + "节注"
    const requestContent = cleanTitle + verseNum + '节注';
    
    console.log('📖 页面标题:', mainTitle);
    console.log('🧹 清理后标题:', cleanTitle);
    console.log('📍 经文编号:', verseNumber);
    console.log('🔢 节号:', verseNum);
    console.log('🎯 最终请求内容:', requestContent);
    
    // 5. 查找并加载注解文件
    fetchZhuJieContent(requestContent);
}

// 加载注解索引文件
async function loadZhuJieIndex() {
    console.log('📚 开始加载注解索引文件');
    
    // 如果已经有加载中的Promise，直接返回
    if (indexLoadPromise) {
        return await indexLoadPromise;
    }
    
    // 如果已经缓存了索引，直接返回
    if (zhuJieIndex) {
        return zhuJieIndex;
    }
    
    // 开始加载索引
    indexLoadPromise = (async () => {
        try {
            const response = await fetch('private/zhu_jie_html/2_index.json');
            if (!response.ok) {
                throw new Error(`索引文件加载失败: ${response.status} ${response.statusText}`);
            }
            
            const index = await response.json();
            console.log('✅ 注解索引加载成功，共', Object.keys(index).length, '条记录');
            console.log('📋 索引内容预览:', Object.keys(index).slice(0, 5));
            
            zhuJieIndex = index;
            return index;
            
        } catch (error) {
            console.error('❌ 加载注解索引失败:', error);
            throw error;
        } finally {
            indexLoadPromise = null; // 清除加载Promise
        }
    })();
    
    return await indexLoadPromise;
}

// 异步加载注解内容 - 使用索引查找
async function fetchZhuJieContent(requestContent) {
    console.log('🔍 开始查找注解文件:', requestContent);
    
    try {
        // 1. 加载索引文件
        const index = await loadZhuJieIndex();
        
        // 2. 在索引中查找对应的文件名
        const fileName = index[requestContent];
        
        if (!fileName) {
            console.log('❌ 在索引中未找到匹配项');
            console.log('🔍 索引中的可用项:', Object.keys(index));
            
            // 尝试模糊匹配
            const fuzzyMatch = findFuzzyMatch(requestContent, Object.keys(index));
            if (fuzzyMatch) {
                console.log('🎯 找到模糊匹配:', fuzzyMatch);
                const confirmLoad = confirm(`未找到完全匹配的注解，是否加载相似的注解："${fuzzyMatch}"？`);
                if (confirmLoad) {
                    await loadZhuJieFile(index[fuzzyMatch], fuzzyMatch);
                    return;
                }
            }
            
            alert(`未找到"${requestContent}"的注解内容\n\n请检查：\n1. 文件是否存在\n2. 索引文件是否已更新\n3. 请求内容是否正确`);
            return;
        }
        
        console.log('✅ 在索引中找到匹配项:', fileName);
        
        // 3. 加载对应的HTML文件
        await loadZhuJieFile(fileName, requestContent);
        
    } catch (error) {
        console.error('💥 加载注解内容失败:', error);
        
        if (error.message.includes('索引文件加载失败')) {
            alert(`注解索引文件不存在或无法访问\n\n请确保以下文件存在：\nprivate/zhu_jie_html/2_index.json\n\n错误详情: ${error.message}`);
        } else {
            alert(`加载注解失败: ${error.message}`);
        }
    }
}

// 加载具体的注解HTML文件
async function loadZhuJieFile(fileName, requestContent) {
    const filePath = `private/zhu_jie_html/${fileName}`;
    
    console.log('📁 加载注解文件:', filePath);
    
    try {
        const response = await fetch(filePath);
        if (!response.ok) {
            throw new Error(`文件加载失败: ${response.status} ${response.statusText}`);
        }
        
        const htmlContent = await response.text();
        console.log('✅ 注解文件加载成功');
        
        // 提取HTML内容
        const processedContent = extractHTMLContent(htmlContent);
        
        // 显示注解内容
        showZhuJieModal(processedContent);
        
    } catch (error) {
        console.error('❌ 注解文件加载失败:', error);
        throw new Error(`无法加载注解文件 "${fileName}": ${error.message}`);
    }
}

// 模糊匹配函数 - 查找相似的注解标题
function findFuzzyMatch(target, candidates) {
    console.log('🔍 开始模糊匹配，目标:', target);
    
    // 简单的包含匹配
    for (const candidate of candidates) {
        if (candidate.includes(target) || target.includes(candidate)) {
            console.log('📌 包含匹配成功:', candidate);
            return candidate;
        }
    }
    
    // 更宽泛的匹配 - 移除数字后比较
    const targetBase = target.replace(/\d+/g, '');
    for (const candidate of candidates) {
        const candidateBase = candidate.replace(/\d+/g, '');
        if (candidateBase === targetBase) {
            console.log('📌 基础匹配成功:', candidate);
            return candidate;
        }
    }
    
    console.log('❌ 未找到模糊匹配');
    return null;
}

// 显示注解模态框（不需要title参数）
function showZhuJieModal(content) {
    console.log('📋 显示注解模态框');
    
    // 检查是否存在 showHymnModalRaw 函数
    if (typeof showHymnModalRaw === 'function') {
        showHymnModalRaw('注解内容', content);
    } else {
        // 备用方案：使用简单的模态框
        console.warn('⚠️ showHymnModalRaw 函数不存在，使用备用显示方案');
        showSimpleModal('注解内容', content);
    }
}

// 备用的简单模态框显示函数
function showSimpleModal(title, content) {
    // 创建模态框
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 10000;
    `;
    
    modal.innerHTML = `
        <div style="
            background: white;
            padding: 20px;
            border-radius: 10px;
            max-width: 80%;
            max-height: 80%;
            overflow-y: auto;
            position: relative;
        ">
            <button onclick="this.closest('[style*=position]').remove()" style="
                position: absolute;
                top: 10px;
                right: 10px;
                background: #f44336;
                color: white;
                border: none;
                border-radius: 50%;
                width: 30px;
                height: 30px;
                cursor: pointer;
            ">×</button>
            <h2>${title}</h2>
            <div>${content}</div>
        </div>
    `;
    
    // 点击背景关闭
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            modal.remove();
        }
    });
    
    document.body.appendChild(modal);
}

// 工具函数：手动重新加载索引（用于调试）
window.reloadZhuJieIndex = async function() {
    console.log('🔄 手动重新加载注解索引');
    zhuJieIndex = null;
    indexLoadPromise = null;
    
    try {
        await loadZhuJieIndex();
        console.log('✅ 索引重新加载成功');
    } catch (error) {
        console.error('❌ 索引重新加载失败:', error);
    }
};

// ========== 注解功能处理模块结束 ==========
// ========== 注解功能处理模块结束 ==========


// ============ 整章，整卷查询处理逻辑============

// 测试章节格式标准化
function testChapterStandardization() {
    console.log('=== 测试章节格式标准化 ===');
    
    const testCases = [
        '创世记第一章',     // 标准格式
        '创世记1章',        // 阿拉伯数字
        '马太第3章',        // 混合格式
        '太1章',            // 极简写
        '罗马书第十二章',   // 完整书名
        '罗马12章',         // 灵活书名
        '林前第一章',       // 简写
        '哥林多前书1章'     // 完整名称
    ];
    
    testCases.forEach(testCase => {
        console.log(`\n测试: "${testCase}"`);
        const result = standardizeChapterInputEnhanced(testCase);
        if (result) {
            console.log(`✅ 成功: "${testCase}" -> "${result.standardFormat}"`);
            console.log(`   详情: 原书名="${result.originalBook}", 标准书名="${result.standardBook}"`);
            console.log(`   详情: 原章节="${result.originalChapter}", 标准章节="${result.standardChapter}"`);
        } else {
            console.log(`❌ 失败: "${testCase}"`);
        }
    });
    
    console.log('=== 测试完成 ===');
}

// 测试书名识别
function testBookNameRecognition() {
    console.log('=== 测试书名识别 ===');
    
    const testCases = [
        '创世记',      // 标准全称
        '马太',        // 简写
        '太',          // 极简写
        '罗马',        // 灵活书名
        '罗马书',      // 完整书名
        '箴言',        // 不带书字
        '箴言书',      // 带书字
        '林前',        // 简写
        '哥林多前书'   // 完整名
    ];
    
    testCases.forEach(testCase => {
        console.log(`\n测试: "${testCase}"`);
        const isBook = isBookNameOnlyEnhanced(testCase);
        const standardName = standardizeBookNameEnhanced(testCase);
        console.log(`   是否为书名: ${isBook ? '✅' : '❌'}`);
        console.log(`   标准化结果: ${standardName || '无法识别'}`);
    });
    
    console.log('=== 测试完成 ===');
}

// 导出测试函数
window.testChapterStandardization = testChapterStandardization;
window.testBookNameRecognition = testBookNameRecognition;

console.log('✅ 经节分类增强功能已加载完成');
console.log('📝 测试方法: window.testChapterStandardization() 和 window.testBookNameRecognition()');
console.log('🔧 修改说明: 请将上述注释中的代码插入到现有的 handleLocalDictionaryMatch 函数中');// ============ 新增数据映射表 ============

// 书名变体完整映射表（扩展现有的BOOK_NAME_MAP）
const BOOK_VARIANT_COMPLETE_MAP = {
    // 现有BOOK_NAME_MAP的内容保持不变，这里添加额外的变体
    '创世记': '创世记',
    '出埃及记': '出埃及记', 
    '利未记': '利未记',
    '民数记': '民数记',
    '申命记': '申命记',
    '约书亚记': '约书亚记',
    '士师记': '士师记',
    '路得记': '路得记',
    '撒母耳记上': '撒母耳记上',
    '撒母耳记下': '撒母耳记下',
    '列王纪上': '列王纪上',
    '列王纪下': '列王纪下',
    '历代志上': '历代志上',
    '历代志下': '历代志下',
    '以斯拉记': '以斯拉记',
    '尼希米记': '尼希米记',
    '以斯帖记': '以斯帖记',
    '约伯记': '约伯记',
    '诗篇': '诗篇',
    '箴言': '箴言',
    '箴言书': '箴言',
    '传道书': '传道书',
    '雅歌': '雅歌',
    '雅歌书': '雅歌',
    '以赛亚书': '以赛亚书',
    '耶利米书': '耶利米书',
    '耶利米哀歌': '耶利米哀歌',
    '以西结书': '以西结书',
    '但以理书': '但以理书',
    '何西阿书': '何西阿书',
    '约珥书': '约珥书',
    '阿摩司书': '阿摩司书',
    '俄巴底亚书': '俄巴底亚书',
    '约拿书': '约拿书',
    '弥迦书': '弥迦书',
    '那鸿书': '那鸿书',
    '哈巴谷书': '哈巴谷书',
    '西番雅书': '西番雅书',
    '哈该书': '哈该书',
    '撒迦利亚书': '撒迦利亚书',
    '玛拉基书': '玛拉基书',
    '马太福音': '马太福音',
    '马可福音': '马可福音',
    '路加福音': '路加福音',
    '约翰福音': '约翰福音',
    '使徒行传': '使徒行传',
    '罗马书': '罗马书',
    '哥林多前书': '哥林多前书',
    '哥林多后书': '哥林多后书',
    '加拉太书': '加拉太书',
    '以弗所书': '以弗所书',
    '腓立比书': '腓立比书',
    '歌罗西书': '歌罗西书',
    '帖撒罗尼迦前书': '帖撒罗尼迦前书',
    '帖撒罗尼迦后书': '帖撒罗尼迦后书',
    '提摩太前书': '提摩太前书',
    '提摩太后书': '提摩太后书',
    '提多书': '提多书',
    '腓利门书': '腓利门书',
    '希伯来书': '希伯来书',
    '雅各书': '雅各书',
    '彼得前书': '彼得前书',
    '彼得后书': '彼得后书',
    '约翰一书': '约翰一书',
    '约翰二书': '约翰二书',
    '约翰三书': '约翰三书',
    '犹大书': '犹大书',
    '启示录': '启示录',
    // 灵活书名（带/不带"书"字的双向映射）
    '诗篇': '诗篇',
    '箴言书': '箴言',
    '传道': '传道书', 
    '传道书': '传道书',
    '雅歌': '雅歌',
    '雅歌书': '雅歌',
    '以赛亚': '以赛亚书',
    '以赛亚书': '以赛亚书',
    '耶利米': '耶利米书',
    '耶利米书': '耶利米书',
    '以西结': '以西结书',
    '以西结书': '以西结书',
    '但以理': '但以理书',
    '但以理书': '但以理书',
    '何西阿': '何西阿书',
    '何西阿书': '何西阿书',
    '约珥': '约珥书',
    '约珥书': '约珥书',
    '阿摩司': '阿摩司书',
    '阿摩司书': '阿摩司书',
    '俄巴底亚': '俄巴底亚书',
    '俄巴底亚书': '俄巴底亚书',
    '约拿': '约拿书',
    '约拿书': '约拿书',
    '弥迦': '弥迦书',
    '弥迦书': '弥迦书',
    '那鸿': '那鸿书',
    '那鸿书': '那鸿书',
    '哈巴谷': '哈巴谷书',
    '哈巴谷书': '哈巴谷书',
    '西番雅': '西番雅书',
    '西番雅书': '西番雅书',
    '哈该': '哈该书',
    '哈该书': '哈该书',
    '撒迦利亚': '撒迦利亚书',
    '撒迦利亚书': '撒迦利亚书',
    '玛拉基': '玛拉基书',
    '玛拉基书': '玛拉基书',
    
    // 新约灵活书名
    '罗马': '罗马书',
    '罗马书': '罗马书',
    '加拉太': '加拉太书',
    '加拉太书': '加拉太书',
    '以弗所': '以弗所书',
    '以弗所书': '以弗所书',
    '腓立比': '腓立比书',
    '腓立比书': '腓立比书',
    '歌罗西': '歌罗西书',
    '歌罗西书': '歌罗西书',
    '提摩太前': '提摩太前书',
    '提摩太前书': '提摩太前书',
    '提摩太后': '提摩太后书',
    '提摩太后书': '提摩太后书',
    '提多': '提多书',
    '提多书': '提多书',
    '腓利门': '腓利门书',
    '腓利门书': '腓利门书',
    '希伯来': '希伯来书',
    '希伯来书': '希伯来书',
    '雅各': '雅各书',
    '雅各书': '雅各书',
    '犹大': '犹大书',
    '犹大书': '犹大书',
    
    // 简写变体（扩展）
    '马太': '马太福音',
    '马可': '马可福音',
    '路加': '路加福音',
    '约翰': '约翰福音',
    '约壹': '约翰一书',
    '约贰': '约翰二书',
    '约叁': '约翰三书',
    '行传': '使徒行传',
    '林前': '哥林多前书',
    '林后': '哥林多后书',
    '提前': '提摩太前书',
    '提后': '提摩太后书',
    '彼前': '彼得前书',
    '彼后': '彼得后书',
    '撒上': '撒母耳记上',
    '撒下': '撒母耳记下',
    '王上': '列王纪上',
    '王下': '列王纪下',
    '代上': '历代志上',
    '代下': '历代志下',
    '帖前': '帖撒罗尼迦前书',
    '帖后': '帖撒罗尼迦后书',
    '创': '创世记', '出': '出埃及记', '利': '利未记', '民': '民数记', '申': '申命记', '书': '约书亚记', '士': '士师记', '得': '路得记', '撒上': '撒母耳记上', '撒下': '撒母耳记下', '王上': '列王纪上', '王下': '列王纪下', '代上': '历代志上', '代下': '历代志下', '拉': '以斯拉记', '尼': '尼希米记', '斯': '以斯帖记', '伯': '约伯记', '诗': '诗篇', '箴': '箴言', '传': '传道书', '歌': '雅歌', '赛': '以赛亚书', '耶': '耶利米书', '哀': '耶利米哀歌', '结': '以西结书', '但': '但以理书', '何': '何西阿书', '珥': '约珥书', '摩': '阿摩司书', '俄': '俄巴底亚书', '拿': '约拿书', '弥': '弥迦书', '鸿': '那鸿书', '哈': '哈巴谷书', '番': '西番雅书', '该': '哈该书', '亚': '撒迦利亚书', '玛': '玛拉基书', 
    '太': '马太福音', '可': '马可福音', '路': '路加福音', '约': '约翰福音', '徒': '使徒行传', '罗': '罗马书', '林前': '哥林多前书', '林后': '哥林多后书', '加': '加拉太书', '弗': '以弗所书', '腓': '腓立比书', '西': '歌罗西书', '帖前': '帖撒罗尼迦前书', '帖后': '帖撒罗尼迦后书', '提前': '提摩太前书', '提后': '提摩太后书', '多': '提多书', '门': '腓利门书', '来': '希伯来书', '雅': '雅各书', '彼前': '彼得前书', '彼后': '彼得后书', '约壹': '约翰一书', '约贰': '约翰二书', '约叁': '约翰三书', '犹': '犹大书', '启': '启示录'
};

// 章节格式识别模式
/**
 * 通用预处理函数 - 移除所有空格和标点符号
 * @param {string} input - 原始输入
 * @returns {string} - 清理后的输入
 */
function preprocessInput(input) {
    if (!input || typeof input !== 'string') {
        return '';
    }
    
    // 移除所有空格和标点符号的正则表达式
    const cleaningRegex = /[\s\u3000,.，。、；;！!？?""''「」『』（）()【】\[\]《》<>]/g;
    let cleaned = input.replace(cleaningRegex, '').trim();
    
    // 🆕 篇字替换为章字（但保护"诗篇"不被替换）
    // 先标记"诗篇"，替换其他"篇"为"章"，再还原"诗篇"
    const temp = cleaned.replace(/诗篇/g, '【SHIPIAN】'); // 临时标记
    const replacedPian = temp.replace(/篇/g, '章');        // 替换篇为章
    const finalCleaned = replacedPian.replace(/【SHIPIAN】/g, '诗篇'); // 还原诗篇
    
    console.log(`🧹 统一预处理: "${input}" -> "${finalCleaned}"`);
    return finalCleaned;
}

// ============ 章节格式识别模式 ============

const CHAPTER_FORMAT_PATTERNS = [
    // 模式1: 完整书名 + 第 + 章节号 + 章
    {
        regex: /^(.+?)第([一二三四五六七八九十百〇零\d]+)章$/,
        type: 'full_with_di',
        priority: 1,
        extract: (match) => ({ book: match[1], chapter: match[2] })
    },
    
    // 模式2: 完整书名 + 章节号 + 章（省略"第"）
    {
        regex: /^(.+?)([一二三四五六七八九十百〇零\d]+)章$/,
        type: 'full_no_di',
        priority: 2,
        extract: (match) => ({ book: match[1], chapter: match[2] })
    },
    
    // 模式3: 书名变体 + 第 + 章节号 + 章
    {
        regex: /^([^第章\d]{1,6})第([一二三四五六七八九十百〇零\d]+)章$/,
        type: 'variant_with_di',
        priority: 3,
        extract: (match) => ({ book: match[1], chapter: match[2] })
    },
    
    // 模式4: 书名变体 + 章节号 + 章（省略"第"）
    {
        regex: /^([^第章\d]{1,6})([一二三四五六七八九十百〇零\d]+)章$/,
        type: 'variant_no_di',
        priority: 4,
        extract: (match) => ({ book: match[1], chapter: match[2] })
    },
        {
        regex: /^(.+?)第([一二三四五六七八九十百〇零\d]+)章$/,
        type: 'full_with_di',
        priority: 1,
        extract: (match) => ({ book: match[1], chapter: match[2] })
    },
    
    // 模式2: 完整书名 + 章节号 + 章（省略"第"）
    {
        regex: /^(.+?)([一二三四五六七八九十百〇零\d]+)篇$/,
        type: 'full_no_di',
        priority: 2,
        extract: (match) => ({ book: match[1], chapter: match[2] })
    },
    
    // 模式3: 书名变体 + 第 + 章节号 + 章
    {
        regex: /^([^第章\d]{1,6})第([一二三四五六七八九十百〇零\d]+)篇$/,
        type: 'variant_with_di',
        priority: 3,
        extract: (match) => ({ book: match[1], chapter: match[2] })
    },
    
    // 模式4: 书名变体 + 章节号 + 章（省略"第"）
    {
        regex: /^([^第章\d]{1,6})([一二三四五六七八九十百〇零\d]+)篇$/,
        type: 'variant_no_di',
        priority: 4,
        extract: (match) => ({ book: match[1], chapter: match[2] })
    }
];

// ============ 缓存和数据加载函数 ============
function detectChapterFormat(input) {
    return CHAPTER_FORMAT_PATTERNS.some(pattern => pattern.regex.test(input));
}
// 缓存变量
let shengJingDirectoryCache = null;
let jingWenIndexCache = null;

// 异步加载圣经分类目录
async function loadShengJingDirectoryData() {
    console.log('📚 开始加载圣经分类目录数据');
    
    if (shengJingDirectoryCache) {
        console.log('✅ 使用缓存的目录数据');
        return shengJingDirectoryCache;
    }
    
    try {
        const response = await fetch('private/4_sheng_jing_fen_lei_mu_lu.json');
        if (!response.ok) {
            throw new Error(`目录文件加载失败: ${response.status} ${response.statusText}`);
        }
        
        const data = await response.json();
        shengJingDirectoryCache = data;
        
        console.log(`✅ 圣经目录数据加载成功，共 ${Object.keys(data).length} 条记录`);
        return data;
        
    } catch (error) {
        console.error('❌ 加载圣经目录数据失败:', error);
        throw error;
    }
}

// 异步加载经文HTML索引
async function loadJingWenIndexData() {
    console.log('📖 开始加载经文HTML索引数据');
    
    if (jingWenIndexCache) {
        console.log('✅ 使用缓存的索引数据');
        return jingWenIndexCache;
    }
    
    try {
        const response = await fetch('private/jing_wen_html/2_index.json');
        if (!response.ok) {
            throw new Error(`索引文件加载失败: ${response.status} ${response.statusText}`);
        }
        
        const data = await response.json();
        jingWenIndexCache = data;
        
        console.log(`✅ 经文索引数据加载成功，共 ${Object.keys(data).length} 条记录`);
        return data;
        
    } catch (error) {
        console.error('❌ 加载经文索引数据失败:', error);
        throw error;
    }
}

// 异步加载具体的HTML文件
async function loadJingWenHTMLFile(fileName) {
    console.log(`📄 开始加载HTML文件: ${fileName}`);
    
    try {
        const filePath = `private/jing_wen_html/${fileName}`;
        const response = await fetch(filePath);
        
        if (!response.ok) {
            throw new Error(`HTML文件加载失败: ${response.status} ${response.statusText}`);
        }
        
        const htmlContent = await response.text();
        console.log(`✅ HTML文件加载成功: ${fileName}`);
        
        return htmlContent;
        
    } catch (error) {
        console.error(`❌ 加载HTML文件失败: ${fileName}`, error);
        throw error;
    }
}

// ============ 标准化函数（带预处理） ============

/**
 * 标准化书名（带预处理）
 * @param {string} bookInput - 原始书名输入
 * @returns {string|null} - 标准化后的书名或null
 */
function standardizeBookNameEnhanced(bookInput) {
    // 🔧 添加预处理
    const cleanedInput = preprocessInput(bookInput);
    console.log(`🔄 标准化书名: "${cleanedInput}"`);
    
    if (!cleanedInput) {
        return null;
    }
    
    /*// 1. 检查现有的BOOK_NAME_MAP（基础映射整章查询先不要）
    if (typeof BOOK_NAME_MAP !== 'undefined' && BOOK_NAME_MAP[cleanedInput]) {
        const result = cleanedInput; // 已经是标准格式
        console.log(`✅ 基础映射匹配: "${cleanedInput}" -> "${result}"`);
        return result;
    }*/
    
    // 2. 检查扩展的变体映射
    if (typeof BOOK_VARIANT_COMPLETE_MAP !== 'undefined' && BOOK_VARIANT_COMPLETE_MAP[cleanedInput]) {
        const result = BOOK_VARIANT_COMPLETE_MAP[cleanedInput];
        console.log(`✅ 变体映射匹配: "${cleanedInput}" -> "${result}"`);
        return result;
    }
    
    console.log(`❌ 无法标准化书名: "${cleanedInput}"`);
    return null;
}

/**
 * 标准化章节号（带预处理）
 * @param {string} chapterInput - 原始章节输入
 * @returns {string|null} - 标准化后的章节号
 */
function standardizeChapterNumberEnhanced(chapterInput) {
    // 🔧 添加预处理
    const cleanedInput = preprocessInput(chapterInput);
    console.log(`🔢 标准化章节号: "${cleanedInput}"`);
    
    if (!cleanedInput) {
        return null;
    }
    
    // 如果是阿拉伯数字，使用现有的arabicToCustomChinese函数
    if (/^\d+$/.test(cleanedInput)) {
        const num = parseInt(cleanedInput);
        if (typeof arabicToCustomChinese === 'function') {
            const result = arabicToCustomChinese(num);
            console.log(`✅ 阿拉伯数字转中文: "${cleanedInput}" -> "${result}"`);
            return result;
        } else {
            console.warn('⚠️ arabicToCustomChinese 函数未定义');
            return cleanedInput;
        }
    }
    
    // 如果是中文数字，直接在C_ARABIC_TO_CHINESE中查找是否可以标准化
    if (typeof C_ARABIC_TO_CHINESE !== 'undefined' && C_ARABIC_TO_CHINESE.hasOwnProperty(cleanedInput)) {
        // 找到了对应的标准化形式
        const standardized = C_ARABIC_TO_CHINESE[cleanedInput];
        console.log(`🔄 中文数字标准化: "${cleanedInput}" -> "${standardized}"`);
        return standardized;
    } else {
        // 如果在C_ARABIC_TO_CHINESE中找不到，直接返回原输入
        console.log(`✅ 已是中文数字: "${cleanedInput}"`);
        return cleanedInput;
    }
}

/**
 * 识别章节格式并提取信息（带预处理）
 * @param {string} input - 原始输入
 * @returns {object} - 提取结果
 */
function identifyAndExtractChapterInfo(input) {
    // 🔧 添加预处理
    const cleanedInput = preprocessInput(input);
    console.log(`🔍 识别章节格式: "${cleanedInput}"`);
    
    if (!cleanedInput) {
        return { success: false };
    }
    
    for (const pattern of CHAPTER_FORMAT_PATTERNS) {
        const match = cleanedInput.match(pattern.regex);
        if (match) {
            const extracted = pattern.extract(match);
            console.log(`✅ 匹配模式 ${pattern.type}: 书名="${extracted.book}", 章节="${extracted.chapter}"`);
            
            return {
                success: true,
                type: pattern.type,
                priority: pattern.priority,
                book: extracted.book,
                chapter: extracted.chapter
            };
        }
    }
    
    console.log(`❌ 无法匹配任何章节格式: "${cleanedInput}"`);
    return { success: false };
}

/**
 * 标准化章节输入（主函数，带预处理）
 * @param {string} input - 原始输入
 * @returns {object|null} - 标准化结果
 */
function standardizeChapterInputEnhanced(input) {
    console.log(`🎯 开始标准化章节输入: "${input}"`);
    
    // 预处理已经在identifyAndExtractChapterInfo中完成
    
    // 1. 格式识别和信息提取
    const formatInfo = identifyAndExtractChapterInfo(input);
    if (!formatInfo.success) {
        return null;
    }
    
    // 2. 标准化书名
    const standardBook = standardizeBookNameEnhanced(formatInfo.book);
    if (!standardBook) {
        console.log(`❌ 书名无法标准化: "${formatInfo.book}"`);
        return null;
    }
    
    // 3. 标准化章节号
    const standardChapter = standardizeChapterNumberEnhanced(formatInfo.chapter);
    
    // 4. 构建最终标准格式
    const finalFormat = `${standardBook}第${standardChapter}章`;
    console.log(`✅ 章节标准化成功: "${input}" -> "${finalFormat}"`);
    
    return {
        standardFormat: finalFormat,
        originalBook: formatInfo.book,
        originalChapter: formatInfo.chapter,
        standardBook: standardBook,
        standardChapter: standardChapter,
        patternType: formatInfo.type
    };
}

/**
 * 判断是否为纯书名（带预处理）
 * @param {string} query - 查询字符串
 * @returns {boolean} - 是否为书名
 */
function isBookNameOnlyEnhanced(query) {
    // 🔧 添加预处理
    const cleanedQuery = preprocessInput(query);
    console.log(`📖 检查是否为纯书名: "${cleanedQuery}"`);
    
    if (!cleanedQuery) {
        return false;
    }
    
    // 检查现有映射和扩展映射
    const isBookName = (typeof BOOK_NAME_MAP !== 'undefined' && BOOK_NAME_MAP[cleanedQuery]) || 
                      (typeof BOOK_VARIANT_COMPLETE_MAP !== 'undefined' && BOOK_VARIANT_COMPLETE_MAP[cleanedQuery]);
    
    if (isBookName) {
        console.log(`✅ 识别为书名: "${cleanedQuery}"`);
        return true;
    }
    
    console.log(`❌ 不是书名: "${cleanedQuery}"`);
    return false;
}

// ============ 主处理函数（带预处理） ============

/**
 * 处理章节格式查询（输入已预处理）
 * @param {string} query - 查询字符串
 * @returns {boolean} - 是否处理成功
 */
async function handleChapterFormatQuery(query) {
    console.log(`📖 处理章节格式查询: "${query}"`);
    
    try {
        // 1. 标准化章节输入（内部会进行预处理）
        const standardized = standardizeChapterInputEnhanced(query);
        if (!standardized) {
            console.log(`❌ 章节格式标准化失败: "${query}"`);
            return false;
        }
        
        console.log(`🎯 标准化结果: "${standardized.standardFormat}"`);
        
        // 2. 加载HTML索引
        const indexData = await loadJingWenIndexData();
        
        // 3. 在索引中查找对应的HTML文件名
        const htmlFileName = indexData[standardized.standardFormat];
        
        if (!htmlFileName) {
            console.log(`❌ 在索引中未找到: "${standardized.standardFormat}"`);
            
            // 提供友好的错误提示
            const availableKeys = Object.keys(indexData).filter(key => 
                key.includes(standardized.standardBook.substring(0, 2))
            ).slice(0, 5);
            
            let errorMessage = `未找到"${standardized.standardFormat}"的内容`;
            if (availableKeys.length > 0) {
                errorMessage += `\n\n该书卷的可用章节包括：\n${availableKeys.join('\n')}`;
            }
            
            if (typeof appendMessage === 'function') {
                appendMessage('AI', errorMessage);
            }
            if (typeof appendCopyButton === 'function') {
                appendCopyButton();
            }
            return true;
        }
        
        console.log(`✅ 找到对应HTML文件: ${htmlFileName}`);
        
        // 4. 加载HTML文件内容
        const htmlContent = await loadJingWenHTMLFile(htmlFileName);
        
        // 5. 提取并处理HTML内容
        const processedContent = typeof extractChatHTMLContent === 'function' ?
                                extractChatHTMLContent(htmlContent) : htmlContent;
        
        // 6. 显示内容
        if (typeof showHymnModalRaw === 'function') {
            showHymnModalRaw(standardized.standardFormat, processedContent);
        }
        
        console.log(`✅ 章节内容显示成功: "${standardized.standardFormat}"`);
        return true;
        
    } catch (error) {
        console.error('❌ 处理章节格式查询失败:', error);
        
        let errorMessage = `加载章节内容失败: ${error.message}`;
        
        if (error.message.includes('索引文件加载失败')) {
            errorMessage += '\n\n请确保索引文件存在：private/jing_wen_html/2_index.json';
        } else if (error.message.includes('HTML文件加载失败')) {
            errorMessage += '\n\n该章节的HTML文件可能不存在或路径错误';
        }
        
        if (typeof appendMessage === 'function') {
            appendMessage('AI', errorMessage);
        }
        if (typeof appendCopyButton === 'function') {
            appendCopyButton();
        }
        return true;
    }
}

/**
 * 处理书名目录查询（输入已预处理）
 * @param {string} query - 查询字符串
 * @returns {boolean} - 是否处理成功
 */
async function handleBookDirectoryQuery(query) {
    console.log(`📚 处理书名目录查询: "${query}"`);
    
    try {
        // 1. 标准化书名（内部会进行预处理）
        const standardBook = standardizeBookNameEnhanced(query);
        if (!standardBook) {
            console.log(`❌ 书名标准化失败: "${query}"`);
            return false;
        }
        
        console.log(`🎯 标准化书名: "${standardBook}"`);
        
        // 2. 加载目录数据
        const directoryData = await loadShengJingDirectoryData();
        
        // 3. 查找对应的目录内容
        const directoryContent = directoryData[standardBook];
        
        if (!directoryContent) {
            console.log(`❌ 在目录中未找到: "${standardBook}"`);
            
            // 提供友好的错误提示
            const cleanedQuery = preprocessInput(query);
            const availableBooks = Object.keys(directoryData).filter(book => 
                book.includes(cleanedQuery.substring(0, 1))
            ).slice(0, 5);
            
            let errorMessage = `未找到"${standardBook}"的目录信息`;
            if (availableBooks.length > 0) {
                errorMessage += `\n\n相似的书卷包括：\n${availableBooks.join('\n')}`;
            }
            
            if (typeof appendMessage === 'function') {
                appendMessage('AI', errorMessage);
            }
            if (typeof appendCopyButton === 'function') {
                appendCopyButton();
            }
            return true;
        }
        
        console.log(`✅ 找到目录内容`);
        
        // 4. 格式化并显示目录内容
        const formattedTitle = `${standardBook}目录`;
        const formattedContent = typeof formatMessage === 'function' ? 
                                formatMessage(directoryContent) : directoryContent;
        
        // 5. 显示内容
        if (typeof showHymnModal === 'function') {
            showHymnModal(formattedTitle, formattedContent);
        }
        
        console.log(`✅ 目录内容显示成功: "${standardBook}"`);
        return true;
        
    } catch (error) {
        console.error('❌ 处理书名目录查询失败:', error);
        
        let errorMessage = `加载目录失败: ${error.message}`;
        
        if (error.message.includes('目录文件加载失败')) {
            errorMessage += '\n\n请确保目录文件存在：private/4_sheng_jing_fen_lei_mu_lu.json';
        }
        
        if (typeof appendMessage === 'function') {
            appendMessage('AI', errorMessage);
        }
        if (typeof appendCopyButton === 'function') {
            appendCopyButton();
        }
        return true;
    }
}

// ============ 导出函数 ============

// 导出新增的函数供测试和调试使用
if (typeof window !== 'undefined') {
    window.preprocessInput = preprocessInput;
    window.standardizeChapterInputEnhanced = standardizeChapterInputEnhanced;
    window.isBookNameOnlyEnhanced = isBookNameOnlyEnhanced;
    window.handleChapterFormatQuery = handleChapterFormatQuery;
    window.handleBookDirectoryQuery = handleBookDirectoryQuery;
    window.standardizeBookNameEnhanced = standardizeBookNameEnhanced;
    window.standardizeChapterNumberEnhanced = standardizeChapterNumberEnhanced;
    window.identifyAndExtractChapterInfo = identifyAndExtractChapterInfo;
}

console.log('✅ 经节分类增强功能已加载完成（全部带预处理）');
// ============ 经文整章，整卷查询处理逻辑============


// ============ 经文单节搜索功能处理模块 ==========
// 1. 书名映射表
// 完整的BOOK_NAME_MAP - 全称转简写（用于经节引用）
const BOOK_NAME_MAP = {

    // 旧约 - 全称转简写
    '创世记': '创世记',
    '出埃及记': '出埃及记', 
    '利未记': '利未记',
    '民数记': '民数记',
    '申命记': '申命记',
    '约书亚记': '约书亚记',
    '士师记': '士师记',
    '路得记': '路得记',
    '撒母耳记上': '撒母耳记上',
    '撒母耳记下': '撒母耳记下',
    '列王纪上': '列王纪上',
    '列王纪下': '列王纪下',
    '历代志上': '历代志上',
    '历代志下': '历代志下',
    '以斯拉记': '以斯拉记',
    '尼希米记': '尼希米记',
    '以斯帖记': '以斯帖记',
    '约伯记': '约伯记',
    '诗篇': '诗篇',
    '箴言': '箴言',
    '箴言书': '箴言',
    '传道书': '传道书',
    '雅歌': '雅歌',
    '雅歌书': '雅歌',
    '以赛亚书': '以赛亚书',
    '耶利米书': '耶利米书',
    '耶利米哀歌': '耶利米哀歌',
    '以西结书': '以西结书',
    '但以理书': '但以理书',
    '何西阿书': '何西阿书',
    '约珥书': '约珥书',
    '阿摩司书': '阿摩司书',
    '俄巴底亚书': '俄巴底亚书',
    '约拿书': '约拿书',
    '弥迦书': '弥迦书',
    '那鸿书': '那鸿书',
    '哈巴谷书': '哈巴谷书',
    '西番雅书': '西番雅书',
    '哈该书': '哈该书',
    '撒迦利亚书': '撒迦利亚书',
    '玛拉基书': '玛拉基书',
    '马太福音': '马太福音',
    '马可福音': '马可福音',
    '路加福音': '路加福音',
    '约翰福音': '约翰福音',
    '使徒行传': '使徒行传',
    '罗马书': '罗马书',
    '哥林多前书': '哥林多前书',
    '哥林多后书': '哥林多后书',
    '加拉太书': '加拉太书',
    '以弗所书': '以弗所书',
    '腓立比书': '腓立比书',
    '歌罗西书': '歌罗西书',
    '帖撒罗尼迦前书': '帖撒罗尼迦前书',
    '帖撒罗尼迦后书': '帖撒罗尼迦后书',
    '提摩太前书': '提摩太前书',
    '提摩太后书': '提摩太后书',
    '提多书': '提多书',
    '腓利门书': '腓利门书',
    '希伯来书': '希伯来书',
    '雅各书': '雅各书',
    '彼得前书': '彼得前书',
    '彼得后书': '彼得后书',
    '约翰一书': '约翰一书',
    '约翰二书': '约翰二书',
    '约翰三书': '约翰三书',
    '犹大书': '犹大书',
    '启示录': '启示录',
    '创世记': '创',
    '出埃及记': '出',
    '利未记': '利',
    '民数记': '民',
    '申命记': '申',
    '约书亚记': '书',
    '士师记': '士',
    '路得记': '得',
    '撒母耳记上': '撒上',
    '撒母耳记下': '撒下',
    '列王纪上': '王上',
    '列王纪下': '王下',
    '历代志上': '代上',
    '历代志下': '代下',
    '以斯拉记': '拉',
    '尼希米记': '尼',
    '以斯帖记': '斯',
    '约伯记': '伯',
    '诗篇': '诗',
    '箴言': '箴',
    '传道书': '传',
    '雅歌': '歌',
    '以赛亚书': '赛',
    '耶利米书': '耶',
    '耶利米哀歌': '哀',
    '以西结书': '结',
    '但以理书': '但',
    '何西阿书': '何',
    '约珥书': '珥',
    '阿摩司书': '摩',
    '俄巴底亚书': '俄',
    '约拿书': '拿',
    '弥迦书': '弥',
    '那鸿书': '鸿',
    '哈巴谷书': '哈',
    '西番雅书': '番',
    '哈该书': '该',
    '撒迦利亚书': '亚',
    '玛拉基书': '玛',
    '出埃及': '出',
    '路得': '得',
    '以斯拉': '拉',
    '尼希米': '尼',
    '以斯帖': '斯',
    '约伯': '伯',
    '诗篇': '诗',
    '箴言书': '箴',
    '雅歌书': '歌',
    '以赛亚': '赛',
    '耶利米': '耶',
    '以西结': '结',
    '但以理': '但',
    '何西阿': '何',
    '约珥': '珥',
    '阿摩司': '摩',
    '俄巴底亚': '俄',
    '约拿': '拿',
    '弥迦': '弥',
    '那鸿': '鸿',
    '哈巴谷': '哈',
    '西番雅': '番',
    '哈该': '该',
    '撒迦利亚': '亚',
    '玛拉基': '玛',
    
    // 新约 - 全称转简写
    '马太福音': '太',
    '马太': '太',
    '马可福音': '可',
    '马可': '可',
    '路加福音': '路',
    '路加': '路',
    '约翰福音': '约',
    '约翰': '约',
    '使徒行传': '徒',
    '使徒': '徒',
    '罗马书': '罗',
    '罗马': '罗',
    '哥林多前书': '林前',
    '哥林多后书': '林后',
    '加拉太书': '加',
    '以弗所书': '弗',
    '腓立比书': '腓',
    '歌罗西书': '西',
    '帖撒罗尼迦前书': '帖前',
    '帖撒罗尼迦后书': '帖后',
    '提摩太前书': '提前',
    '提摩太后书': '提后',
    '提多书': '多',
    '腓利门书': '门',
    '希伯来书': '来',
    '雅各书': '雅',
    '彼得前书': '彼前',
    '彼得后书': '彼后',
    '约翰一书': '约壹',
    '约翰二书': '约贰',
    '约翰三书': '约叁',
    '犹大书': '犹',
    '启示录': '启',
    '加拉太': '加',
    '以弗所': '弗',
    '腓立比': '腓',
    '歌罗西': '西',
    '提多书': '多',
    '腓利门': '门',
    '希伯来': '来',
    '雅各': '雅'
};

// 2. 阿拉伯数字转中文数字映射表
const ARABIC_TO_CHINESE = {
    1: '一', 2: '二', 3: '三', 4: '四', 5: '五',
    6: '六', 7: '七', 8: '八', 9: '九', 10: '十',
    11: '十一', 12: '十二', 13: '十三', 14: '十四', 15: '十五',
    16: '十六', 17: '十七', 18: '十八', 19: '十九', 20: '二十',
    21: '二十一', 22: '二十二', 23: '二十三', 24: '二十四', 25: '二十五',
    26: '二十六', 27: '二十七', 28: '二十八', 29: '二十九', 30: '三十',
    31: '三十一', 32: '三十二', 33: '三十三', 34: '三十四', 35: '三十五',
    36: '三十六', 37: '三十七', 38: '三十八', 39: '三十九', 40: '四十',
    41: '四十一', 42: '四十二', 43: '四十三', 44: '四十四', 45: '四十五',
    46: '四十六', 47: '四十七', 48: '四十八', 49: '四十九', 50: '五十',
    // 扩展到150章（诗篇有150章）
    51: '五十一', 52: '五十二', 53: '五十三', 54: '五十四', 55: '五十五',
    56: '五十六', 57: '五十七', 58: '五十八', 59: '五十九', 60: '六十',
    61: '六十一', 62: '六十二', 63: '六十三', 64: '六十四', 65: '六十五',
    66: '六十六', 67: '六十七', 68: '六十八', 69: '六十九', 70: '七十',
    71: '七十一', 72: '七十二', 73: '七十三', 74: '七十四', 75: '七十五',
    76: '七十六', 77: '七十七', 78: '七十八', 79: '七十九', 80: '八十',
    81: '八十一', 82: '八十二', 83: '八十三', 84: '八十四', 85: '八十五',
    86: '八十六', 87: '八十七', 88: '八十八', 89: '八十九', 90: '九十',
    91: '九十一', 92: '九十二', 93: '九十三', 94: '九十四', 95: '九十五',
    96: '九十六', 97: '九十七', 98: '九十八', 99: '九十九', 100: '一〇〇',
    101: '一〇一', 102: '一〇二', 103: '一〇三', 104: '一〇四', 105: '一〇五',
    106: '一〇六', 107: '一〇七', 108: '一〇八', 109: '一〇九', 110: '一一〇',
    111: '一一一', 112: '一一二', 113: '一一三', 114: '一一四', 115: '一一五',
    116: '一一六', 117: '一一七', 118: '一一八', 119: '一一九', 120: '一二〇',
    121: '一二一', 122: '一二二', 123: '一二三', 124: '一二四', 125: '一二五',
    126: '一二六', 127: '一二七', 128: '一二八', 129: '一二九', 130: '一三〇',
    131: '一三一', 132: '一三二', 133: '一三三', 134: '一三四', 135: '一三五',
    136: '一三六', 137: '一三七', 138: '一三八', 139: '一三九', 140: '一四〇',
    141: '一四一', 142: '一四二', 143: '一四三', 144: '一四四', 145: '一四五',
    146: '一四六', 147: '一四七', 148: '一四八', 149: '一四九', 150: '一五〇',
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15,
    '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20,
    
    // 二十以上两种格式
    '二十一': 21, '二一': 21, '二十二': 22, '二二': 22,
    '二十三': 23, '二三': 23, '二十四': 24, '二四': 24,
    '二十五': 25, '二五': 25, '二十六': 26, '二六': 26,
    '二十七': 27, '二七': 27, '二十八': 28, '二八': 28,
    '二十九': 29, '二九': 29, '三十': 30,
    '三十一': 31, '三一': 31, '三十二': 32, '三二': 32,
    '三十三': 33, '三三': 33, '三十四': 34, '三四': 34,
    '三十五': 35, '三五': 35, '三十六': 36, '三六': 36,
    '三十七': 37, '三七': 37, '三十八': 38, '三八': 38,
    '三十九': 39, '三九': 39, '四十': 40,
    '四十一': 41, '四一': 41, '四十二': 42, '四二': 42,
    '四十三': 43, '四三': 43, '四十四': 44, '四四': 44,
    '四十五': 45, '四五': 45, '四十六': 46, '四六': 46,
    '四十七': 47, '四七': 47, '四十八': 48, '四八': 48,
    '四十九': 49, '四九': 49, '五十': 50,
    '五十一': 51, '五一': 51, '五十二': 52, '五二': 52,
    '五十三': 53, '五三': 53, '五十四': 54, '五四': 54,
    '五十五': 55, '五五': 55, '五十六': 56, '五六': 56,
    '五十七': 57, '五七': 57, '五十八': 58, '五八': 58,
    '五十九': 59, '五九': 59, '六十': 60,
    '六十一': 61, '六一': 61, '六十二': 62, '六二': 62,
    '六十三': 63, '六三': 63, '六十四': 64, '六四': 64,
    '六十五': 65, '六五': 65, '六十六': 66, '六六': 66,
    '六十七': 67, '六七': 67, '六十八': 68, '六八': 68,
    '六十九': 69, '六九': 69, '七十': 70,
    '七十一': 71, '七一': 71, '七十二': 72, '七二': 72,
    '七十三': 73, '七三': 73, '七十四': 74, '七四': 74,
    '七十五': 75, '七五': 75, '七十六': 76, '七六': 76,
    '七十七': 77, '七七': 77, '七十八': 78, '七八': 78,
    '七十九': 79, '七九': 79, '八十': 80,
    '八十一': 81, '八一': 81, '八十二': 82, '八二': 82,
    '八十三': 83, '八三': 83, '八十四': 84, '八四': 84,
    '八十五': 85, '八五': 85, '八十六': 86, '八六': 86,
    '八十七': 87, '八七': 87, '八十八': 88, '八八': 88,
    '八十九': 89, '八九': 89, '九十': 90,
    '九十一': 91, '九一': 91, '九十二': 92, '九二': 92,
    '九十三': 93, '九三': 93, '九十四': 94, '九四': 94,
    '九十五': 95, '九五': 95, '九十六': 96, '九六': 96,
    '九十七': 97, '九七': 97, '九十八': 98, '九八': 98,
    '九十九': 99, '九九': 99,
    // 传统格式转换为简化格式
    '一百': '一〇〇', '一百零一': '一〇一', '一百零二': '一〇二', '一百零三': '一〇三', 
    '一百零四': '一〇四', '一百零五': '一〇五', '一百零六': '一〇六', '一百零七': '一〇七', 
    '一百零八': '一〇八', '一百零九': '一〇九', '一百一十': '一一〇', '一百一十一': '一一一', 
    '一百一十二': '一一二', '一百一十三': '一一三', '一百一十四': '一一四', '一百一十五': '一一五', 
    '一百一十六': '一一六', '一百一十七': '一一七', '一百一十八': '一一八', '一百一十九': '一一九', 
    '一百二十': '一二〇', '一百二十一': '一二一', '一百二十二': '一二二', '一百二十三': '一二三', 
    '一百二十四': '一二四', '一百二十五': '一二五', '一百二十六': '一二六', '一百二十七': '一二七', 
    '一百二十八': '一二八', '一百二十九': '一二九', '一百三十': '一三〇', '一百三十一': '一三一', 
    '一百三十二': '一三二', '一百三十三': '一三三', '一百三十四': '一三四', '一百三十五': '一三五', 
    '一百三十六': '一三六', '一百三十七': '一三七', '一百三十八': '一三八', '一百三十九': '一三九', 
    '一百四十': '一四〇', '一百四十一': '一四一', '一百四十二': '一四二', '一百四十三': '一四三', 
    '一百四十四': '一四四', '一百四十五': '一四五', '一百四十六': '一四六', '一百四十七': '一四七', 
    '一百四十八': '一四八', '一百四十九': '一四九', '一百五十': '一五〇',
    '一〇〇': 100, '一〇一': 101, '一〇二': 102, '一〇三': 103, '一〇四': 104,
    '一〇五': 105, '一〇六': 106, '一〇七': 107, '一〇八': 108, '一〇九': 109,
    '一一〇': 110, '一一一': 111, '一一二': 112, '一一三': 113, '一一四': 114,
    '一一五': 115, '一一六': 116, '一一七': 117, '一一八': 118, '一一九': 119,
    '一二〇': 120, '一二一': 121, '一二二': 122, '一二三': 123, '一二四': 124,
    '一二五': 125, '一二六': 126, '一二七': 127, '一二八': 128, '一二九': 129,
    '一三〇': 130, '一三一': 131, '一三二': 132, '一三三': 133, '一三四': 134,
    '一三五': 135, '一三六': 136, '一三七': 137, '一三八': 138, '一三九': 139,
    '一四〇': 140, '一四一': 141, '一四二': 142, '一四三': 143, '一四四': 144,
    '一四五': 145, '一四六': 146, '一四七': 147, '一四八': 148, '一四九': 149,
    '一五〇': 150, '一五一': 151, '一五二': 152, '一五三': 153, '一五四': 154,
    '一五五': 155, '一五六': 156, '一五七': 157, '一五八': 158, '一五九': 159,
    '一六〇': 160, '一六一': 161, '一六二': 162, '一六三': 163, '一六四': 164,
    '一六五': 165, '一六六': 166, '一六七': 167, '一六八': 168, '一六九': 169,
    '一七〇': 170, '一七一': 171, '一七二': 172, '一七三': 173, '一七四': 174,
    '一七五': 175, '一七六': 176, '一七七': 177, '一七八': 178, '一七九': 179,
    '一八〇': 180, '一八一': 181, '一八二': 182, '一八三': 183, '一八四': 184,
    '一八五': 185, '一八六': 186, '一八七': 187, '一八八': 188, '一八九': 189,
    '一九〇': 190, '一九一': 191, '一九二': 192, '一九三': 193, '一九四': 194,
    '一九五': 195, '一九六': 196, '一九七': 197, '一九八': 198, '一九九': 199,
    '二〇〇': 200
};
const B_ARABIC_TO_CHINESE = {
    // 传统格式转换为简化格式
    '一百': '一〇〇', '一百零一': '一〇一', '一百零二': '一〇二', '一百零三': '一〇三', 
    '一百零四': '一〇四', '一百零五': '一〇五', '一百零六': '一〇六', '一百零七': '一〇七', 
    '一百零八': '一〇八', '一百零九': '一〇九', '一百一十': '一一〇', '一百一十一': '一一一', 
    '一百一十二': '一一二', '一百一十三': '一一三', '一百一十四': '一一四', '一百一十五': '一一五', 
    '一百一十六': '一一六', '一百一十七': '一一七', '一百一十八': '一一八', '一百一十九': '一一九', 
    '一百二十': '一二〇', '一百二十一': '一二一', '一百二十二': '一二二', '一百二十三': '一二三', 
    '一百二十四': '一二四', '一百二十五': '一二五', '一百二十六': '一二六', '一百二十七': '一二七', 
    '一百二十八': '一二八', '一百二十九': '一二九', '一百三十': '一三〇', '一百三十一': '一三一', 
    '一百三十二': '一三二', '一百三十三': '一三三', '一百三十四': '一三四', '一百三十五': '一三五', 
    '一百三十六': '一三六', '一百三十七': '一三七', '一百三十八': '一三八', '一百三十九': '一三九', 
    '一百四十': '一四〇', '一百四十一': '一四一', '一百四十二': '一四二', '一百四十三': '一四三', 
    '一百四十四': '一四四', '一百四十五': '一四五', '一百四十六': '一四六', '一百四十七': '一四七', 
    '一百四十八': '一四八', '一百四十九': '一四九', '一百五十': '一五〇'
};

// 新增中文数字标准化映射表（将简化格式转为标准格式）
const C_ARABIC_TO_CHINESE = {
    // 标准格式保持不变（1-20）
    '一': '一', '二': '二', '三': '三', '四': '四', '五': '五',
    '六': '六', '七': '七', '八': '八', '九': '九', '十': '十',
    '十一': '十一', '十二': '十二', '十三': '十三', '十四': '十四', '十五': '十五',
    '十六': '十六', '十七': '十七', '十八': '十八', '十九': '十九', '二十': '二十',
    
    // 21-99: 简化格式转为标准格式
    '二一': '二十一', '二二': '二十二', '二三': '二十三', '二四': '二十四', '二五': '二十五',
    '二六': '二十六', '二七': '二十七', '二八': '二十八', '二九': '二十九',
    '三一': '三十一', '三二': '三十二', '三三': '三十三', '三四': '三十四', '三五': '三十五',
    '三六': '三十六', '三七': '三十七', '三八': '三十八', '三九': '三十九',
    '四一': '四十一', '四二': '四十二', '四三': '四十三', '四四': '四十四', '四五': '四十五',
    '四六': '四十六', '四七': '四十七', '四八': '四十八', '四九': '四十九',
    '五一': '五十一', '五二': '五十二', '五三': '五十三', '五四': '五十四', '五五': '五十五',
    '五六': '五十六', '五七': '五十七', '五八': '五十八', '五九': '五十九',
    '六一': '六十一', '六二': '六十二', '六三': '六十三', '六四': '六十四', '六五': '六十五',
    '六六': '六十六', '六七': '六十七', '六八': '六十八', '六九': '六十九',
    '七一': '七十一', '七二': '七十二', '七三': '七十三', '七四': '七十四', '七五': '七十五',
    '七六': '七十六', '七七': '七十七', '七八': '七十八', '七九': '七十九',
    '八一': '八十一', '八二': '八十二', '八三': '八十三', '八四': '八十四', '八五': '八十五',
    '八六': '八十六', '八七': '八十七', '八八': '八十八', '八九': '八十九',
    '九一': '九十一', '九二': '九十二', '九三': '九十三', '九四': '九十四', '九五': '九十five',
    '九六': '九十六', '九七': '九十七', '九八': '九十八', '九九': '九十九',
    
    // 整十数保持不变
    '三十': '三十', '四十': '四十', '五十': '五十', '六十': '六十',
    '七十': '七十', '八十': '八十', '九十': '九十',
    
    // 传统格式转换为标准格式（复制B_ARABIC_TO_CHINESE的内容）
    '一百': '一〇〇', '一百零一': '一〇一', '一百零二': '一〇二', '一百零三': '一〇三', 
    '一百零四': '一〇四', '一百零五': '一〇五', '一百零六': '一〇六', '一百零七': '一〇七', 
    '一百零八': '一〇八', '一百零九': '一〇九', '一百一十': '一一〇', '一百一十一': '一一一', 
    '一百一十二': '一一二', '一百一十三': '一一三', '一百一十四': '一一四', '一百一十五': '一一五', 
    '一百一十六': '一一六', '一百一十七': '一一七', '一百一十八': '一一八', '一百一十九': '一一九', 
    '一百二十': '一二〇', '一百二十一': '一二一', '一百二十二': '一二二', '一百二十三': '一二三', 
    '一百二十四': '一二四', '一百二十五': '一二五', '一百二十六': '一二六', '一百二十七': '一二七', 
    '一百二十八': '一二八', '一百二十九': '一二九', '一百三十': '一三〇', '一百三十一': '一三一', 
    '一百三十二': '一三二', '一百三十三': '一三三', '一百三十四': '一三四', '一百三十五': '一三五', 
    '一百三十六': '一三六', '一百三十七': '一三七', '一百三十八': '一三八', '一百三十九': '一三九', 
    '一百四十': '一四〇', '一百四十一': '一四一', '一百四十二': '一四二', '一百四十三': '一四三', 
    '一百四十四': '一四四', '一百四十五': '一四五', '一百四十六': '一四六', '一百四十七': '一四七', 
    '一百四十八': '一四八', '一百四十九': '一四九', '一百五十': '一五〇'
};
// 3. 中文数字转阿拉伯数字映射表
const CHINESE_TO_ARABIC = {};
Object.entries(ARABIC_TO_CHINESE).forEach(([arabic, chinese]) => {
    CHINESE_TO_ARABIC[chinese] = parseInt(arabic);
});

// 4. 经节引用格式识别函数
// 4. 检查是否为经节引用格式
function isBibleVerseReference(input) {
    console.log(`🔍 检查经节引用格式: "${input}"`);
    
    if (!input || typeof input !== 'string') {
        return false;
    }
    
    // 预处理：移除所有空格和标点符号
    const cleanedInput = input.replace(/[\s\u3000,.，。、；;！!？?""''「」『』（）()【】\[\]《》<>]/g, '').trim();
    console.log(`🧹 isBibleVerseReference 预处理: "${input}" -> "${cleanedInput}"`);
    
    if (!cleanedInput) {
        return false;
    }
    
    // 定义各种经节引用的正则表达式模式
    const patterns = [
        // 模式1: 创一1 (标准格式)
        { pattern: /^([^0-9\s:：第章节]+)([一二三四五六七八九十百〇]+)(\d+)$/, name: '标准格式(创一1)' },
        
        // 模式2: 约1章14节 (带"章"字的格式)
        { pattern: /^([^0-9第章节]+)(\d+)章(\d+)节?$/, name: '带章字格式(约1章14节)' },
        
        // 模式3: 创11 (连续数字格式)
        { pattern: /^([^0-9第章节]+)(\d+)[：:](\d+)$/, name: '连续数字格式(创11)' },
        
        // 模式4: 创世记一章1节、创世记第一章一节等 - 支持简化和传统格式
        { pattern: /^([^0-9第章节]+)(?:第?)([一二三四五六七八九十百〇零]+|\d+)章(?:第?([一二三四五六七八九十百〇零]+|\d+)节?)?$/, name: '章节格式' },
        
        // 模式5: 创世记第一章第1节
        { pattern: /^([^0-9第章节]+)第([一二三四五六七八九十百〇零]+|\d+)章第(\d+)节$/, name: '完整格式1' },
        
        // 模式6: 创世记第一章第一节
        { pattern: /^([^0-9第章节]+)第([一二三四五六七八九十百〇零]+|\d+)章第([一二三四五六七八九十百〇零]+)节$/, name: '完整格式2' },
        
        // 模式7: 仅书名格式
        { pattern: /^([^0-9第章节一二三四五六七八九十百〇零]+)$/, name: '仅书名格式' }
    ];
        
    for (const { pattern, name } of patterns) {
        if (pattern.test(cleanedInput)) {  // ✅ 修复：使用 cleanedInput 而不是 trimmedInput
            console.log(`✅ 匹配成功: ${name}`);
            return true;
        }
    }
    
    console.log(`❌ 未匹配任何经节引用格式`);
    return false;
}

// 5. 核心转换函数：将各种格式转换为标准格式
function convertToStandardFormat(input) {
    if (!input || typeof input !== 'string') {
        console.warn('convertToStandardFormat: 无效输入');
        return null;
    }
    
    // 预处理：移除所有空格和标点符号
    const cleanedInput = input.replace(/[\s\u3000,.，。、；;！!？?""''「」『』（）()【】\[\]《》<>]/g, '').trim();
    console.log(`🧹 convertToStandardFormat 预处理: "${input}" -> "${cleanedInput}"`);
    
    if (!cleanedInput) {
        console.warn('convertToStandardFormat: 预处理后为空');
        return null;
    }
    
    console.log(`🔄 开始转换: "${cleanedInput}"`);
    
    // 模式1: 创一1 (已经是标准格式)
    let match = cleanedInput.match(/^([^0-9\s:：第章节]+)([一二三四五六七八九十百]+)(\d+)$/);
    if (match) {
        const bookName = BOOK_NAME_MAP[match[1]] || match[1];
        const chapterChinese = match[2]; // 保持中文数字
        const verse = match[3];
        const result = `${bookName}${chapterChinese}${verse}`;
        console.log(`✅ 标准格式(已标准): "${cleanedInput}" -> "${result}"`);
        return result;
    }
    
    // 模式2: 约1章14节 (带"章"字的格式)
    match = cleanedInput.match(/^([^0-9第章节]+)(\d+)章(\d+)节?$/);
    if (match) {
        const bookName = BOOK_NAME_MAP[match[1]] || match[1];
        const chapterNum = parseInt(match[2]);
        const chapterChinese = ARABIC_TO_CHINESE[chapterNum] || match[2];
        const verse = match[3];
        const result = `${bookName}${chapterChinese}${verse}`;
        console.log(`✅ 带章字格式转换: "${cleanedInput}" -> "${result}"`);
        console.log(`🔍 转换详细: 书名="${match[1]}" -> "${bookName}", 章="${match[2]}" -> "${chapterChinese}", 节="${verse}"`);
        return result;
    }
    
    // 模式3: 创11 (连续数字格式)
    match = cleanedInput.match(/^([^0-9第章节]+)(\d+)[：:](\d+)$/);
    if (match) {
        const bookName = BOOK_NAME_MAP[match[1]] || match[1];
        const chapterNum = parseInt(match[2]);
        const verseNum = parseInt(match[3]);
        
        if (chapterNum > 0 && chapterNum <= 150 && verseNum > 0) {
            const chapterChinese = ARABIC_TO_CHINESE[chapterNum] || match[2];
            const result = `${bookName}${chapterChinese}${match[3]}`;
            console.log(`✅ 冒号格式转换: "${cleanedInput}" -> "${result}"`);
            console.log(`🔍 转换详细: 书名="${match[1]}" -> "${bookName}", 章="${match[2]}" -> "${chapterChinese}", 节="${match[3]}"`);
            return result;
        }
    }
    
    // 模式4: 创世记一章1节、创世记第一章一节等 (最复杂的格式)
    match = cleanedInput.match(/^([^\d第章节一二三四五六七八九十百〇零]+)(?:第?)([一二三四五六七八九十百〇零]+|\d+)章(?:第?([一二三四五六七八九十百〇零]+|\d+)节?)?$/);
    if (match) {
        const bookName = BOOK_NAME_MAP[match[1]] || match[1];
        
        // 处理章节 - 添加传统格式转简化格式的转换
        let chapterChinese;
        if (isNaN(match[2])) {
            // 已经是中文数字，检查是否需要转换为简化格式
            chapterChinese = B_ARABIC_TO_CHINESE[match[2]] || match[2];
        } else {
            // 阿拉伯数字转中文
            const chapterNum = parseInt(match[2]);
            chapterChinese = ARABIC_TO_CHINESE[chapterNum] || match[2];
        }
        
        // 处理节数
        let verse = '1'; // 默认第1节
        if (match[3]) {
            if (isNaN(match[3])) {
                // 中文数字节，需要转为阿拉伯数字
                verse = String(CHINESE_TO_ARABIC[match[3]] || match[3]);
            } else {
                // 阿拉伯数字节，直接使用
                verse = match[3];
            }
        }
        
        const result = `${bookName}${chapterChinese}${verse}`;
        console.log(`✅ 章节格式转换: "${cleanedInput}" -> "${result}"`);
        return result;
    }
    
    // 模式5: 创世记第一章第1节
    match = cleanedInput.match(/^([^0-9第章节]+)第([一二三四五六七八九十百]+|\d+)章第(\d+)节$/);
    if (match) {
        const bookName = BOOK_NAME_MAP[match[1]] || match[1];
        
        let chapterChinese;
        if (isNaN(match[2])) {
            chapterChinese = match[2];
        } else {
            const chapterNum = parseInt(match[2]);
            chapterChinese = ARABIC_TO_CHINESE[chapterNum] || match[2];
        }
        
        const verse = match[3];
        const result = `${bookName}${chapterChinese}${verse}`;
        console.log(`✅ 完整格式1转换: "${cleanedInput}" -> "${result}"`);
        return result;
    }
    
    // 模式6: 创世记第一章第一节
    match = cleanedInput.match(/^([^0-9第章节]+)第([一二三四五六七八九十百]+|\d+)章第([一二三四五六七八九十百]+)节$/);
    if (match) {
        const bookName = BOOK_NAME_MAP[match[1]] || match[1];
        
        let chapterChinese;
        if (isNaN(match[2])) {
            chapterChinese = match[2];
        } else {
            const chapterNum = parseInt(match[2]);
            chapterChinese = ARABIC_TO_CHINESE[chapterNum] || match[2];
        }
        
        // 节数从中文转阿拉伯数字
        const verse = String(CHINESE_TO_ARABIC[match[3]] || match[3]);
        
        const result = `${bookName}${chapterChinese}${verse}`;
        console.log(`✅ 完整格式2转换: "${cleanedInput}" -> "${result}"`);
        return result;
    }
    
    // 模式7: 处理只有书名的情况（默认第一章第一节）
    match = cleanedInput.match(/^([^0-9第章节一二三四五六七八九十百〇零]+)$/);
    if (match) {
        const bookName = BOOK_NAME_MAP[match[1]] || match[1];
        const result = `${bookName}一1`;
        console.log(`✅ 仅书名格式转换: "${cleanedInput}" -> "${result}"`);
        return result;
    }
    
    console.log(`❌ 无法转换: "${cleanedInput}"`);
    return null;
}

// 6. 优先查找经节引用的完整函数
function prioritizeBibleVerse(userInput) {
    console.log(`🔍 prioritizeBibleVerse 开始处理: "${userInput}"`);
    
    if (!userInput || typeof userInput !== 'string') {
        console.warn('prioritizeBibleVerse: 无效的输入');
        return { found: false };
    }
    
    try {
        // 检查是否为经节引用格式
        if (isBibleVerseReference(userInput)) {
            const standardKey = convertToStandardFormat(userInput);
            console.log(`🔄 标准化结果: "${userInput}" -> "${standardKey}"`);
            
            // 检查数据源状态
            if (!window.bibleVerse) {
                console.warn('⚠️ window.bibleVerse 不存在');
                return { found: false };
            }
            
            if (typeof window.bibleVerse !== 'object') {
                console.warn('⚠️ window.bibleVerse 不是对象:', typeof window.bibleVerse);
                return { found: false };
            }
            
            // 安全检查并查找
            if (standardKey && Object.prototype.hasOwnProperty.call(window.bibleVerse, standardKey)) {
                const content = window.bibleVerse[standardKey];
                if (content) {
                    console.log(`✅ 找到匹配的经节: ${standardKey}`);
                    return {
                        found: true,
                        key: standardKey,
                        content: content,
                        source: 'bible_verse'
                    };
                }
            }
            
            // 调试信息
            console.log(`❌ 未找到匹配的经节: ${standardKey}`);
            console.log('📚 bibleVerse状态:', {
                exists: !!window.bibleVerse,
                type: typeof window.bibleVerse,
                keysCount: window.bibleVerse ? Object.keys(window.bibleVerse).length : 0,
                hasStandardKey: window.bibleVerse ? standardKey in window.bibleVerse : false
            });
            
            // 显示相似的键作为调试
            if (window.bibleVerse && standardKey) {
                const allKeys = Object.keys(window.bibleVerse);
                const bookPart = standardKey.substring(0, 1); // 书名部分
                const similarKeys = allKeys.filter(k => 
                    k.startsWith(bookPart)
                ).slice(0, 10);
                console.log('🔍 相似的键:', similarKeys);
            }
        } else {
            console.log(`❌ 不是经节引用格式: "${userInput}"`);
        }
    } catch (error) {
        console.error('prioritizeBibleVerse 出错:', error);
    }
    
    return { found: false };
}

// 7. 测试函数
function testBibleVerseStandardization() {
    const testCases = [
        '创一1',           // 标准格式
        '创 1:1',          // 带空格冒号
        '创1:1',           // 冒号格式
        '创世记一章1节',    // 章节格式
        '创世记第一章一节', // 完整格式
        '创世记第一章第1节',// 混合格式
        '创世记第一章第一节',// 全中文格式
        '太一1',
        '太1:1',
        '马太福音第一章第一节'
    ];
    
    console.log('=== 经节标准化测试 ===');
    testCases.forEach(testCase => {
        console.log(`\n测试: "${testCase}"`);
        const isRecognized = isBibleVerseReference(testCase);
        console.log(`识别: ${isRecognized ? '✅' : '❌'}`);
        
        if (isRecognized) {
            const standardFormat = convertToStandardFormat(testCase);
            console.log(`标准格式: ${standardFormat || 'N/A'}`);
            
            if (standardFormat && window.bibleVerse) {
                const hasContent = window.bibleVerse[standardFormat];
                console.log(`数据存在: ${hasContent ? '✅' : '❌'}`);
                if (hasContent) {
                    console.log(`✅ 成功: "${testCase}" -> "${standardFormat}"`);
                }
            }
        }
    });
    console.log('=== 测试完成 ===');
}

// 8. 导出函数供全局使用
window.isBibleVerseReference = isBibleVerseReference;
window.convertToStandardFormat = convertToStandardFormat;
window.prioritizeBibleVerse = prioritizeBibleVerse;
window.testBibleVerseStandardization = testBibleVerseStandardization;
// ========== 经文单节搜索功能处理模块 ==========

// ============ 注解引用格式处理模块 ==========

/**
 * 检查是否为注解引用格式或纯经节格式
 * @param {string} input - 用户输入
 * @returns {boolean} - 是否为注解引用格式或纯经节格式
 */
/**
 * 检查是否为注解引用格式或纯经节格式
 * @param {string} input - 用户输入
 * @returns {boolean} - 是否为注解引用格式或纯经节格式
 */
function isBibleAnnotationReference(input) {
    console.log(`🔍 检查注解引用格式或纯经节格式: "${input}"`);
    
    if (!input || typeof input !== 'string') {
        return false;
    }
    
    const cleanedInput = preprocessInput(input);
    if (!cleanedInput) {
        return false;
    }
    
    // 定义6种引用的正则表达式模式（支持节、节注、节注[数字]、注[数字]等多种格式）
    const referencePatterns = [
        // 模式1: 创一1[节][注[数字]] (标准格式 + 可选节注)
        { pattern: /^([^0-9\s:：第章节]+)([一二三四五六七八九十百〇]+)(\d+)(?:节?注?(\d+)?)?$/, name: '标准格式' },
        
        // 模式2: 约1章14[节][注[数字]] (带章字格式 + 可选节注)
        { pattern: /^([^0-9第章节]+)(\d+)章(\d+)(?:节?注?(\d+)?)?$/, name: '带章字格式' },
        
        // 模式3: 创11[节][注[数字]] (冒号格式 + 可选节注)
        { pattern: /^([^0-9第章节]+)(\d+)[：:](\d+)(?:节?注?(\d+)?)?$/, name: '冒号格式' },
        
        // 模式4: 创世记一章1[节][注[数字]] (章节格式 + 可选节注)
        { pattern: /^([^0-9第章节]+)(?:第?)([一二三四五六七八九十百〇零]+|\d+)章(?:第?([一二三四五六七八九十百〇零]+|\d+)(?:节?注?(\d+)?)?)?$/, name: '章节格式' },
        
        // 模式5: 创世记第一章第1[节][注[数字]] (完整格式1 + 可选节注)
        { pattern: /^([^0-9第章节]+)第([一二三四五六七八九十百〇零]+|\d+)章第(\d+)(?:节?注?(\d+)?)?$/, name: '完整格式1' },
        
        // 模式6: 创世记第一章第一[节][注[数字]] (完整格式2 + 可选节注)
        { pattern: /^([^0-9第章节]+)第([一二三四五六七八九十百〇零]+|\d+)章第([一二三四五六七八九十百〇零]+)(?:节?注?(\d+)?)?$/, name: '完整格式2' }
    ];
    
    for (const { pattern, name } of referencePatterns) {
        if (pattern.test(cleanedInput)) {
            console.log(`✅ 匹配格式: ${name}`);
            return true;
        }
    }
    
    console.log(`❌ 未匹配任何引用格式`);
    return false;
}

/**
 * 解析注解节址引用，返回注号与短标题（用于单个注解库）
 */
function parseAnnotationReferenceDetails(userInput) {
    const cleanedInput = preprocessInput(userInput);
    if (!cleanedInput) return null;

    const bookNames = Object.keys(BOOK_VARIANT_COMPLETE_MAP).sort((a, b) => b.length - a.length);
    const bookNamesPattern = bookNames.map(name => name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');

    const referencePatterns = [
        {
            pattern: new RegExp(`^(${bookNamesPattern})([一二三四五六七八九十百〇]+)(\\d+)(?:节?注?(\\d+)?)?$`),
            extract: (match) => ({
                book: match[1],
                chapter: C_ARABIC_TO_CHINESE[match[2]] || match[2],
                verse: match[3],
                noteNum: match[4] || null,
            }),
        },
        {
            pattern: new RegExp(`^(${bookNamesPattern})(\\d+)章(\\d+)(?:节?注?(\\d+)?)?$`),
            extract: (match) => ({
                book: match[1],
                chapter: ARABIC_TO_CHINESE[parseInt(match[2])] || match[2],
                verse: match[3],
                noteNum: match[4] || null,
            }),
        },
        {
            pattern: new RegExp(`^(${bookNamesPattern})(\\d+)[：:](\\d+)(?:节?注?(\\d+)?)?$`),
            extract: (match) => {
                const chapterNum = parseInt(match[2]);
                const verseNum = parseInt(match[3]);
                if (chapterNum > 0 && chapterNum <= 150 && verseNum > 0) {
                    return {
                        book: match[1],
                        chapter: ARABIC_TO_CHINESE[chapterNum] || match[2],
                        verse: match[3],
                        noteNum: match[4] || null,
                    };
                }
                return null;
            },
        },
        {
            pattern: new RegExp(`^(${bookNamesPattern})(?:第?)([一二三四五六七八九十百〇零]+|\\d+)章(?:第?([一二三四五六七八九十百〇零]+|\\d+)(?:节?注?(\\d+)?)?)?$`),
            extract: (match) => {
                let chapterChinese;
                if (isNaN(match[2])) {
                    chapterChinese = C_ARABIC_TO_CHINESE[match[2]] || match[2];
                } else {
                    chapterChinese = ARABIC_TO_CHINESE[parseInt(match[2])] || match[2];
                }
                let verse = '1';
                if (match[3]) {
                    verse = isNaN(match[3])
                        ? String(CHINESE_TO_ARABIC[match[3]] || match[3])
                        : match[3];
                }
                return {
                    book: match[1],
                    chapter: chapterChinese,
                    verse,
                    noteNum: match[4] || null,
                };
            },
        },
        {
            pattern: new RegExp(`^(${bookNamesPattern})第([一二三四五六七八九十百〇零]+|\\d+)章第(\\d+)(?:节?注?(\\d+)?)?$`),
            extract: (match) => ({
                book: match[1],
                chapter: isNaN(match[2]) ? (C_ARABIC_TO_CHINESE[match[2]] || match[2]) : (ARABIC_TO_CHINESE[parseInt(match[2])] || match[2]),
                verse: match[3],
                noteNum: match[4] || null,
            }),
        },
        {
            pattern: new RegExp(`^(${bookNamesPattern})第([一二三四五六七八九十百〇零]+|\\d+)章第([一二三四五六七八九十百〇零]+)(?:节?注?(\\d+)?)?$`),
            extract: (match) => ({
                book: match[1],
                chapter: isNaN(match[2]) ? (C_ARABIC_TO_CHINESE[match[2]] || match[2]) : (ARABIC_TO_CHINESE[parseInt(match[2])] || match[2]),
                verse: String(CHINESE_TO_ARABIC[match[3]] || match[3]),
                noteNum: match[4] || null,
            }),
        },
    ];

    for (const patternInfo of referencePatterns) {
        const match = cleanedInput.match(patternInfo.pattern);
        if (!match) continue;

        const extracted = patternInfo.extract(match);
        if (!extracted) continue;

        let noteNum = extracted.noteNum;
        if (!noteNum) {
            const noteM = cleanedInput.match(/注(\d+)\s*$/);
            if (noteM) noteNum = noteM[1];
        }

        const shortTitle = `${extracted.book}${extracted.chapter}${extracted.verse}注${noteNum || ''}`.replace(/注$/, '');
        const lookupKeys = noteNum
            ? [shortTitle, `恢复本圣经　${shortTitle}`, `恢复本圣经，${shortTitle}`]
            : [];

        return {
            matched: true,
            noteNum: noteNum || null,
            shortTitle: noteNum ? shortTitle : null,
            lookupKeys,
        };
    }

    return null;
}

/**
 * 转换注解引用或纯经节为索引查找格式
 * @param {string} userInput - 用户输入的引用
 * @returns {string|null} - 索引格式或null
 */
function convertToAnnotationIndexKey(userInput) {
    console.log(`🔄 转换引用为索引格式: "${userInput}"`);
    
    const cleanedInput = preprocessInput(userInput);
    if (!cleanedInput) return null;
    
    // 动态构建书名正则模式（按长度降序排列，避免短名称优先匹配）
    const bookNames = Object.keys(BOOK_VARIANT_COMPLETE_MAP).sort((a, b) => b.length - a.length);
    const bookNamesPattern = bookNames.map(name => name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
    
    // 定义6种模式及其对应的解析逻辑（支持节、节注、节注[数字]、注[数字]等多种格式）
    const referencePatterns = [
        {
            pattern: new RegExp(`^(${bookNamesPattern})([一二三四五六七八九十百〇]+)(\\d+)(?:节?注?(\\d+)?)?$`),
            name: '标准格式',
            extract: (match) => ({
                book: match[1],
                chapter: C_ARABIC_TO_CHINESE[match[2]] || match[2],
                verse: match[3]
            })
        },
        {
            pattern: new RegExp(`^(${bookNamesPattern})(\\d+)章(\\d+)(?:节?注?(\\d+)?)?$`),
            name: '带章字格式',
            extract: (match) => ({
                book: match[1],
                chapter: ARABIC_TO_CHINESE[parseInt(match[2])] || match[2],
                verse: match[3]
            })
        },
        {
            pattern: new RegExp(`^(${bookNamesPattern})(\\d+)[：:](\\d+)(?:节?注?(\\d+)?)?$`),
            name: '冒号格式',
            extract: (match) => {
                const chapterNum = parseInt(match[2]);
                const verseNum = parseInt(match[3]);
                if (chapterNum > 0 && chapterNum <= 150 && verseNum > 0) {
                    return {
                        book: match[1],
                        chapter: ARABIC_TO_CHINESE[chapterNum] || match[2],
                        verse: match[3]
                    };
                }
                return null;
            }
        },
        {
            pattern: new RegExp(`^(${bookNamesPattern})(?:第?)([一二三四五六七八九十百〇零]+|\\d+)章(?:第?([一二三四五六七八九十百〇零]+|\\d+)(?:节?注?(\\d+)?)?)?$`),
            name: '章节格式',
            extract: (match) => {
                let chapterChinese;
                if (isNaN(match[2])) {
                    // 如果是中文数字，使用C_ARABIC_TO_CHINESE进行标准化
                    chapterChinese = C_ARABIC_TO_CHINESE[match[2]] || match[2];
                } else {
                    // 如果是阿拉伯数字，转为中文数字
                    chapterChinese = ARABIC_TO_CHINESE[parseInt(match[2])] || match[2];
                }
                
                let verse = '1'; // 默认第1节
                if (match[3]) {
                    if (isNaN(match[3])) {
                        // 中文数字节，需要转为阿拉伯数字
                        verse = String(CHINESE_TO_ARABIC[match[3]] || match[3]);
                    } else {
                        // 阿拉伯数字节，直接使用
                        verse = match[3];
                    }
                }
                
                return {
                    book: match[1],
                    chapter: chapterChinese,
                    verse: verse
                };
            }
        },
        {
            pattern: new RegExp(`^(${bookNamesPattern})第([一二三四五六七八九十百〇零]+|\\d+)章第(\\d+)(?:节?注?(\\d+)?)?$`),
            name: '完整格式1',
            extract: (match) => ({
                book: match[1],
                chapter: isNaN(match[2]) ? (C_ARABIC_TO_CHINESE[match[2]] || match[2]) : (ARABIC_TO_CHINESE[parseInt(match[2])] || match[2]),
                verse: match[3]
            })
        },
        {
            pattern: new RegExp(`^(${bookNamesPattern})第([一二三四五六七八九十百〇零]+|\\d+)章第([一二三四五六七八九十百〇零]+)(?:节?注?(\\d+)?)?$`),
            name: '完整格式2',
            extract: (match) => ({
                book: match[1],
                chapter: isNaN(match[2]) ? (C_ARABIC_TO_CHINESE[match[2]] || match[2]) : (ARABIC_TO_CHINESE[parseInt(match[2])] || match[2]),
                verse: String(CHINESE_TO_ARABIC[match[3]] || match[3])
            })
        }
    ];
    
    // 尝试匹配各种模式
    for (const patternInfo of referencePatterns) {
        const match = cleanedInput.match(patternInfo.pattern);
        if (match) {
            console.log(`✅ 匹配模式: ${patternInfo.name}`);
            
            const extracted = patternInfo.extract(match);
            if (!extracted) continue;
            
            // 转换为索引格式：书名全称第章节注（统一格式）
            let bookFull;

            // 先尝试从BOOK_VARIANT_COMPLETE_MAP获取完整书名
            if (typeof BOOK_VARIANT_COMPLETE_MAP !== 'undefined' && BOOK_VARIANT_COMPLETE_MAP[extracted.book]) {
                bookFull = BOOK_VARIANT_COMPLETE_MAP[extracted.book];
            } else if (BOOK_NAME_MAP[extracted.book]) {
                bookFull = BOOK_NAME_MAP[extracted.book];
                // 如果BOOK_NAME_MAP返回的还是简写，保持原书名
                if (bookFull.length <= 2) {
                    bookFull = extracted.book;
                }
            } else {
                bookFull = extracted.book;
            }

            // 统一索引格式：无论输入是否包含"注"，都生成带"注"的索引格式
            const indexFormat = `${bookFull}第${extracted.chapter}章${extracted.verse}节注`;
            
            console.log(`🎯 转换完成: "${userInput}" -> "${indexFormat}"`);
            return indexFormat;
        }
    }
    
    console.log(`❌ 无法转换: "${userInput}"`);
    return null;
}

/**
 * 处理注解格式或纯经节格式查询
 * @param {string} query - 查询字符串
 * @returns {boolean} - 是否处理成功
 */
async function handleAnnotationFormatQuery(query) {
    console.log(`📝 处理引用格式查询: "${query}"`);

    const parsed = parseAnnotationReferenceDetails(query);
    if (!parsed || !parsed.matched) {
        console.log(`❌ 非注解节址格式: "${query}"`);
        return false;
    }

    if (!parsed.noteNum) {
        console.log(`ℹ️ 节址无注号，按规则不返回结果: "${query}"`);
        const selectedLang = window.selectedLang || 'zh-CN';
        const noAnswerText = translations[selectedLang]?.noAnswer || '暂时未找到您要的答案，您可以尝试其他问题！';
        if (typeof appendMessage === 'function') {
            appendMessage('AI', noAnswerText);
        }
        if (typeof appendCopyButton === 'function') {
            appendCopyButton();
        }
        return true;
    }

    try {
        console.log(`🎯 单个注解查询: ${parsed.shortTitle} (注${parsed.noteNum})`);

        const indexResponse = await fetch('private/foo_jie_single/title_index.json');
        if (!indexResponse.ok) {
            throw new Error('单个注解索引未部署，请先运行 build_foo_jie_index.js');
        }

        const indexData = await indexResponse.json();
        let fileName = null;
        for (const key of parsed.lookupKeys) {
            if (indexData[key]) {
                fileName = indexData[key];
                break;
            }
        }

        if (!fileName) {
            const msg = `未找到「${parsed.shortTitle}」的注解`;
            if (typeof appendMessage === 'function') appendMessage('AI', msg);
            if (typeof appendCopyButton === 'function') appendCopyButton();
            return true;
        }

        const fileResponse = await fetch(`private/foo_jie_single/files/${fileName}`);
        if (!fileResponse.ok) {
            throw new Error(`注解文件加载失败: ${fileName}`);
        }

        let htmlContent = await fileResponse.text();
        try {
            const jsonParsed = JSON.parse(htmlContent);
            if (typeof jsonParsed === 'string') htmlContent = jsonParsed;
        } catch (_) { /* 已是 HTML 字符串 */ }

        const displayTitle = parsed.lookupKeys[1] || parsed.shortTitle;
        if (typeof showHymnModalRaw === 'function') {
            showHymnModalRaw(displayTitle, htmlContent);
        }

        console.log(`✅ 单个注解显示成功: ${fileName}`);
        return true;
    } catch (error) {
        console.error('❌ 单个注解查询失败:', error);
        if (typeof appendMessage === 'function') {
            appendMessage('AI', `加载注解失败: ${error.message}`);
        }
        if (typeof appendCopyButton === 'function') {
            appendCopyButton();
        }
        return true;
    }
}

// 导出新增的函数供全局使用
if (typeof window !== 'undefined') {
    window.isBibleAnnotationReference = isBibleAnnotationReference;
    window.convertToAnnotationIndexKey = convertToAnnotationIndexKey;
    window.handleAnnotationFormatQuery = handleAnnotationFormatQuery;
}

console.log('✅ 注解搜索功能处理模块已加载完成');



// ============ 图表的显示逻辑============
// 在现有的事件委托代码中添加（在scripts.js文件末尾添加）

document.addEventListener('click', function(event) {
    const chartBtn = event.target.closest('.chart-image-btn');
    if (!chartBtn) return;
    
    event.stopPropagation();
    event.preventDefault();
    
    const chartName = chartBtn.dataset.chartName;
    console.log('🖼️ 点击图表按钮:', chartName);
    
    fetchChartImage(chartName);
});

// ============ 图表图片获取和显示函数 ============


async function fetchChartImage(chartName) {
    console.log(`🖼️ 开始加载图表: "${chartName}"`);
    
    try {
        const imagePath = `private/tu_biiao-tu_pian/${chartName}.jpeg`;
        
        // 先检查图片是否存在
        const response = await fetch(imagePath);
        if (!response.ok) {
            throw new Error(`图片文件不存在或无法访问: ${response.status}`);
        }
        
        // 构建图片HTML内容
        const imageContent = `
            <div style="text-align: center; padding: 20px;">
                <img src="${imagePath}" 
                     alt="${chartName}" 
                     style="max-width: 100%; 
                            height: auto; 
                            border-radius: 8px; 
                            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                            cursor: zoom-in;"
                     onclick="this.style.transform = this.style.transform ? '' : 'scale(1.5)'; this.style.transition = 'transform 0.3s ease';">
                <p style="margin-top: 15px; color: #666; font-size: 14px;">点击图片可放大查看</p>
            </div>
        `;
        
        // 使用现有的模态框显示图片
        if (typeof showHymnModalRaw === 'function') {
            showHymnModalRaw(chartName, imageContent);
        } else {
            console.error('❌ showHymnModalRaw 函数不存在');
            alert('显示功能暂不可用');
        }
        
        console.log(`✅ 图表显示成功: "${chartName}"`);
        
    } catch (error) {
        console.error('❌ 加载图表失败:', error);
        
        let errorMessage = `无法加载图表：${chartName}`;
        
        if (error.message.includes('图片文件不存在')) {
            errorMessage += `\n\n请确保图片文件存在：\nprivate/tu_biiao-tu_pian/${chartName}.jpeg`;
        } else {
            errorMessage += `\n\n错误信息: ${error.message}`;
        }
        
        alert(errorMessage);
    }
}

// ============ 图表的显示逻辑============