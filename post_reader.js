const state = {
    sourceName: "",
    sourceType: "",
    allPosts: [],
    filteredPosts: [],
    postIndex: new Map(),
    currentPage: 1,
    pageSize: Number(localStorage.getItem("post_reader_page_size") || 20),
    theme: localStorage.getItem("post_reader_theme") || "day",
    filterScope: localStorage.getItem("post_reader_filter_scope") || "all",
    filterChangeBehavior: localStorage.getItem("post_reader_filter_change_behavior") || "keep-page",
    pageSizeBehavior: localStorage.getItem("post_reader_page_size_behavior") || "keep-first-item",
    imageDirHandle: null,
    imageDirName: "",
    imageMode: "none",
    imageMap: new Map(),
    imageUrlCache: new Map(),
    objectUrls: [],
};

const IMAGE_EXTENSION_CANDIDATES = ["jpg", "jpeg", "png", "gif", "webp", "bmp"];

const elements = {
    dataFileInput: document.getElementById("dataFileInput"),
    pickImageDirectoryButton: document.getElementById("pickImageDirectoryButton"),
    imageFolderInput: document.getElementById("imageFolderInput"),
    imageModeSummary: document.getElementById("imageModeSummary"),
    themeSelect: document.getElementById("themeSelect"),
    userFilterInput: document.getElementById("userFilterInput"),
    poFilterSelect: document.getElementById("poFilterSelect"),
    filterScopeSelect: document.getElementById("filterScopeSelect"),
    filterChangeBehaviorSelect: document.getElementById("filterChangeBehaviorSelect"),
    pageSizeBehaviorSelect: document.getElementById("pageSizeBehaviorSelect"),
    pageSizeSelect: document.getElementById("pageSizeSelect"),
    resetFiltersButton: document.getElementById("resetFiltersButton"),
    jumpPageInput: document.getElementById("jumpPageInput"),
    jumpPageButton: document.getElementById("jumpPageButton"),
    prevPageButton: document.getElementById("prevPageButton"),
    nextPageButton: document.getElementById("nextPageButton"),
    sourceSummary: document.getElementById("sourceSummary"),
    statsLine: document.getElementById("statsLine"),
    pageInfo: document.getElementById("pageInfo"),
    renderHint: document.getElementById("renderHint"),
    emptyState: document.getElementById("emptyState"),
    postList: document.getElementById("postList"),
};

elements.pageSizeSelect.value = String(state.pageSize);
elements.themeSelect.value = state.theme;
elements.filterScopeSelect.value = state.filterScope;
elements.filterChangeBehaviorSelect.value = state.filterChangeBehavior;
elements.pageSizeBehaviorSelect.value = state.pageSizeBehavior;
applyTheme();

elements.dataFileInput.addEventListener("change", handleDataFileChange);
elements.pickImageDirectoryButton.addEventListener("click", pickImageDirectory);
elements.imageFolderInput.addEventListener("change", handleImageFolderChange);
elements.themeSelect.addEventListener("change", handleThemeChange);
elements.userFilterInput.addEventListener("input", applyFilters);
elements.poFilterSelect.addEventListener("change", applyFilters);
elements.filterScopeSelect.addEventListener("change", handleFilterScopeChange);
elements.filterChangeBehaviorSelect.addEventListener("change", handleFilterChangeBehavior);
elements.pageSizeBehaviorSelect.addEventListener("change", handlePageSizeBehavior);
elements.pageSizeSelect.addEventListener("change", handlePageSizeChange);
elements.resetFiltersButton.addEventListener("click", resetFilters);
elements.jumpPageButton.addEventListener("click", jumpToPage);
elements.jumpPageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
        jumpToPage();
    }
});
elements.prevPageButton.addEventListener("click", () => changePage(-1));
elements.nextPageButton.addEventListener("click", () => changePage(1));
elements.postList.addEventListener("click", handlePostListClick);

updateSummary();
render();

async function handleDataFileChange(event) {
    const file = event.target.files[0];
    if (!file) {
        return;
    }

    try {
        const text = await file.text();
        const lowerName = file.name.toLowerCase();
        let posts = [];
        let sourceType = "";

        if (lowerName.endsWith(".json")) {
            posts = parseJsonPosts(text);
            sourceType = "json";
        } else if (lowerName.endsWith(".md")) {
            posts = parseMarkdownPosts(text);
            sourceType = "md";
        } else {
            throw new Error("仅支持 .json 或 .md 文件。");
        }

        state.sourceName = file.name;
        state.sourceType = sourceType;
        state.allPosts = normalizePosts(posts);
        rebuildPostIndex();
        state.currentPage = 1;
        applyFilters();
    } catch (error) {
        window.alert(`读取文件失败: ${error.message}`);
    }
}

function handleImageFolderChange(event) {
    clearImageSources();

    state.imageMap.clear();

    const files = Array.from(event.target.files || []);
    for (const file of files) {
        if (!file.type.startsWith("image/")) {
            continue;
        }
        const url = URL.createObjectURL(file);
        state.objectUrls.push(url);
        state.imageMap.set(file.name.toLowerCase(), url);
    }

    state.imageMode = state.imageMap.size ? "legacy" : "none";
    state.imageDirName = state.imageMap.size ? "已导入目录文件列表" : "";
    updateSummary();
    render();
}

async function pickImageDirectory() {
    if (typeof window.showDirectoryPicker !== "function") {
        window.alert("当前浏览器不支持按路径选择目录，请改用“兼容模式导入目录”。");
        return;
    }

    try {
        clearImageSources();
        const handle = await window.showDirectoryPicker({ mode: "read" });
        state.imageDirHandle = handle;
        state.imageDirName = handle.name || "";
        state.imageMode = "handle";
        updateSummary();
        render();
    } catch (error) {
        if (error && error.name === "AbortError") {
            return;
        }
        window.alert(`选择图片目录失败: ${error.message}`);
    }
}

function handlePageSizeChange() {
    const anchorPost = getCurrentAnchorPost();
    state.pageSize = Number(elements.pageSizeSelect.value);
    localStorage.setItem("post_reader_page_size", String(state.pageSize));
    applyFilters({ reason: "page-size-change", anchorPost });
}

function handleThemeChange() {
    state.theme = elements.themeSelect.value;
    localStorage.setItem("post_reader_theme", state.theme);
    applyTheme();
}

function handleFilterScopeChange() {
    state.filterScope = elements.filterScopeSelect.value;
    localStorage.setItem("post_reader_filter_scope", state.filterScope);
    applyFilters({ reason: "filter-change" });
}

function handleFilterChangeBehavior() {
    state.filterChangeBehavior = elements.filterChangeBehaviorSelect.value;
    localStorage.setItem("post_reader_filter_change_behavior", state.filterChangeBehavior);
}

function handlePageSizeBehavior() {
    state.pageSizeBehavior = elements.pageSizeBehaviorSelect.value;
    localStorage.setItem("post_reader_page_size_behavior", state.pageSizeBehavior);
}

function resetFilters() {
    elements.userFilterInput.value = "";
    elements.poFilterSelect.value = "all";
    applyFilters({ reason: "filter-change" });
}

function applyTheme() {
    document.body.dataset.theme = state.theme;
}

function clearImageSources() {
    revokeObjectUrls();
    state.imageDirHandle = null;
    state.imageDirName = "";
    state.imageMode = "none";
    state.imageMap.clear();
    state.imageUrlCache.clear();
}

function parseJsonPosts(text) {
    const data = JSON.parse(text);
    if (!Array.isArray(data)) {
        throw new Error("JSON 顶层必须是数组。");
    }
    return data;
}

function parseMarkdownPosts(text) {
    const normalized = text.replace(/\r\n/g, "\n");
    const blocks = normalized
        .split(/(?=^#\s+No\.)/m)
        .map((block) => block.trim())
        .filter((block) => block.startsWith("# No."));

    return blocks.map(parseMarkdownBlock).filter(Boolean);
}

function parseMarkdownBlock(block) {
    const postNoMatch = block.match(/^#\s+(No\.[^\n]+)$/m);
    if (!postNoMatch) {
        return null;
    }

    const userLine = block.match(/^\*\*ID.*$/m)?.[0] || "";
    const userMatches = userLine.match(/[A-Za-z0-9]{4,}/g) || [];
    const userId = userMatches.length ? userMatches[userMatches.length - 1] : "";
    const isPO = /\(PO\)/.test(userLine);
    const timeLine = block.match(/^post_time.*$/m)?.[0] || "";
    const time = timeLine.replace(/^post_time[^A-Za-z0-9\u4e00-\u9fa5]*/u, "").trim();
    const content = block.match(/```markdown\s*([\s\S]*?)\n```/m)?.[1]?.trim() || "";
    const imgUrl = block.match(/!\[Image\]\(([^)]+)\)/)?.[1] || "";

    return {
        post_no: postNoMatch[1].trim(),
        user_id: userId,
        PO: isPO ? "PO" : "",
        time,
        content,
        img_url: imgUrl,
    };
}

function normalizePosts(posts) {
    return posts
        .filter((post) => post && typeof post === "object")
        .map((post) => ({
            post_no: String(post.post_no || "").trim(),
            user_id: String(post.user_id || "").trim(),
            PO: String(post.PO || "").trim(),
            time: String(post.time || "").trim(),
            title: String(post.title || "").trim(),
            email: String(post.email || "").trim(),
            content: String(post.content || "").replace(/\r\n/g, "\n").trim(),
            img_url: String(post.img_url || "").trim(),
        }))
        .filter((post) => post.post_no || post.content || post.user_id);
}

function rebuildPostIndex() {
    state.postIndex.clear();

    for (const post of state.allPosts) {
        for (const key of getLookupKeysFromPostNo(post.post_no)) {
            state.postIndex.set(key, post);
        }
    }
}

function getLookupKeysFromPostNo(postNo) {
    const value = String(postNo || "").trim();
    if (!value) {
        return [];
    }

    const keys = new Set([value.toLowerCase()]);
    const noMatch = value.match(/^No\.(\d+)$/i);
    const poMatch = value.match(/^Po\.(\d+)$/i);
    const hashMatch = value.match(/^#(\d+)$/);

    if (noMatch) {
        keys.add(`no.${noMatch[1]}`.toLowerCase());
    }
    if (poMatch) {
        keys.add(`po.${poMatch[1]}`.toLowerCase());
    }
    if (hashMatch) {
        keys.add(`#${hashMatch[1]}`.toLowerCase());
        keys.add(`po.${hashMatch[1]}`.toLowerCase());
    }

    return Array.from(keys);
}

function normalizeReferenceToken(token) {
    return String(token || "")
        .replace(/^>>\s*/i, "")
        .trim()
        .toLowerCase();
}

function findReferencedPost(token) {
    const normalized = normalizeReferenceToken(token);
    const direct = state.postIndex.get(normalized);
    if (direct) {
        return direct;
    }

    const poMatch = normalized.match(/^po\.(\d+)$/i);
    if (poMatch) {
        return state.postIndex.get(`#${poMatch[1]}`.toLowerCase()) || state.postIndex.get(`no.${poMatch[1]}`.toLowerCase()) || null;
    }

    const noMatch = normalized.match(/^no\.(\d+)$/i);
    if (noMatch) {
        return state.postIndex.get(`#${noMatch[1]}`.toLowerCase()) || null;
    }

    return null;
}

function parseUserFilterTokens(rawValue) {
    return rawValue
        .split(/[\s,，]+/u)
        .map((token) => token.trim().toLowerCase())
        .filter(Boolean);
}

function matchesActiveFilters(post, userTokens, poMode) {
    const normalizedUserId = post.user_id.toLowerCase();
    const userOk = !userTokens.length || userTokens.some((token) => normalizedUserId.includes(token));
    const isPO = Boolean(post.PO);

    let poOk = true;
    if (poMode === "po") {
        poOk = isPO;
    } else if (poMode === "non-po") {
        poOk = !isPO;
    }

    return userOk && poOk;
}

function getRawTotalPages() {
    if (!state.allPosts.length) {
        return 0;
    }
    return Math.ceil(state.allPosts.length / state.pageSize);
}

function getCurrentRawPagePosts() {
    const start = (state.currentPage - 1) * state.pageSize;
    const end = start + state.pageSize;
    return state.allPosts.slice(start, end);
}

function getPageForPostInList(posts, targetPostNo) {
    if (!targetPostNo) {
        return 1;
    }

    const index = posts.findIndex((post) => post.post_no === targetPostNo);
    if (index < 0) {
        return 1;
    }

    return Math.floor(index / state.pageSize) + 1;
}

function getCurrentAnchorPost() {
    const currentPosts = getCurrentPagePosts();
    return currentPosts.length ? currentPosts[0] : null;
}

function getFilteredPostsForPage(pageNo, userTokens, poMode) {
    const start = (pageNo - 1) * state.pageSize;
    const end = start + state.pageSize;
    const pagePosts = state.allPosts.slice(start, end);
    return pagePosts.filter((post) => matchesActiveFilters(post, userTokens, poMode));
}

function getFilteredPostsForAll(userTokens, poMode) {
    return state.allPosts.filter((post) => matchesActiveFilters(post, userTokens, poMode));
}

function applyFilters(options = {}) {
    const reason = options.reason || "filter-change";
    const anchorPost = options.anchorPost || null;
    const userTokens = parseUserFilterTokens(elements.userFilterInput.value);
    const poMode = elements.poFilterSelect.value;

    if (reason === "filter-change" && state.filterChangeBehavior === "first-page") {
        state.currentPage = 1;
    }

    if (reason === "page-size-change") {
        if (state.pageSizeBehavior === "first-page") {
            state.currentPage = 1;
        } else if (anchorPost?.post_no) {
            state.currentPage = getPageForPostInList(state.allPosts, anchorPost.post_no);
        }
    }

    const rawTotalPages = getRawTotalPages();
    if (rawTotalPages > 0) {
        state.currentPage = Math.min(Math.max(1, state.currentPage), rawTotalPages);
    } else {
        state.currentPage = 1;
    }

    if (state.filterScope === "page") {
        state.filteredPosts = getFilteredPostsForPage(state.currentPage, userTokens, poMode);
        render();
        return;
    }

    state.filteredPosts = getFilteredPostsForAll(userTokens, poMode);

    if (reason === "page-size-change" && state.pageSizeBehavior === "keep-first-item" && anchorPost?.post_no) {
        state.currentPage = getPageForPostInList(state.filteredPosts, anchorPost.post_no);
    }

    const filteredTotalPages = Math.ceil(state.filteredPosts.length / state.pageSize);
    if (filteredTotalPages > 0) {
        state.currentPage = Math.min(Math.max(1, state.currentPage), filteredTotalPages);
    } else {
        state.currentPage = 1;
    }

    render();
}

function changePage(offset) {
    const totalPages = getActiveTotalPages();
    const nextPage = Math.min(Math.max(1, state.currentPage + offset), totalPages || 1);
    if (nextPage === state.currentPage) {
        return;
    }
    state.currentPage = nextPage;
    applyFilters({ reason: "page-change" });
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function jumpToPage() {
    const totalPages = getActiveTotalPages();
    const requested = Number(elements.jumpPageInput.value);
    if (!requested || requested < 1 || requested > totalPages) {
        return;
    }
    state.currentPage = requested;
    applyFilters({ reason: "page-change" });
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function getTotalPages() {
    if (!state.filteredPosts.length) {
        return 0;
    }
    return Math.ceil(state.filteredPosts.length / state.pageSize);
}

function getActiveTotalPages() {
    if (state.filterScope === "page") {
        return getRawTotalPages();
    }
    return getTotalPages();
}

function getCurrentPagePosts() {
    if (state.filterScope === "page") {
        return state.filteredPosts;
    }

    const start = (state.currentPage - 1) * state.pageSize;
    const end = start + state.pageSize;
    return state.filteredPosts.slice(start, end);
}

function updateSummary() {
    const imageCount = state.imageMap.size;
    const hasHandle = state.imageMode === "handle" && state.imageDirHandle;
    if (hasHandle) {
        elements.imageModeSummary.textContent = `已选择目录: ${state.imageDirName}（按需读取）`;
    } else if (state.imageMode === "legacy" && imageCount) {
        elements.imageModeSummary.textContent = `已导入 ${imageCount} 张图片（兼容模式）`;
    } else {
        elements.imageModeSummary.textContent = "未选择图片目录";
    }

    if (!state.sourceName) {
        elements.sourceSummary.textContent = hasHandle
            ? "未加载数据，图片目录已就绪"
            : imageCount
                ? `未加载数据，已载入 ${imageCount} 张本地图片`
                : "未加载数据";
        return;
    }

    const typeLabel = state.sourceType === "md" ? "Markdown" : "JSON";
    const imageLabel = hasHandle
        ? `，图片目录 ${state.imageDirName}（按需读取）`
        : imageCount
            ? `，本地图片 ${imageCount} 张`
            : "，未选择本地图片文件夹";
    elements.sourceSummary.textContent = `${state.sourceName} · ${typeLabel}${imageLabel}`;
}

function render() {
    updateSummary();

    const total = state.filteredPosts.length;
    const rawTotalPages = getRawTotalPages();
    const filteredTotalPages = getTotalPages();
    const activeTotalPages = getActiveTotalPages();
    const currentPage = activeTotalPages ? Math.min(state.currentPage, activeTotalPages) : 0;
    if (activeTotalPages && state.currentPage !== currentPage) {
        state.currentPage = currentPage;
    }

    if (state.filterScope === "page") {
        const currentRawCount = getCurrentRawPagePosts().length;
        elements.statsLine.textContent = `当前页筛选后 ${total} / ${currentRawCount} 条，原文件共 ${state.allPosts.length} 条，${rawTotalPages} 页`;
    } else {
        elements.statsLine.textContent = `全文件筛选后 ${total} 条，共 ${filteredTotalPages} 页`;
    }

    elements.pageInfo.textContent = `第 ${currentPage} / ${activeTotalPages} 页`;
    elements.renderHint.textContent = state.sourceName
        ? `当前数据源: ${state.sourceName} · ${state.filterScope === "page" ? "仅当前页筛选" : "全文件筛选"}`
        : "加载文件后开始阅读";

    elements.prevPageButton.disabled = currentPage <= 1;
    elements.nextPageButton.disabled = !activeTotalPages || currentPage >= activeTotalPages;
    elements.jumpPageButton.disabled = !activeTotalPages;
    elements.jumpPageInput.disabled = !activeTotalPages;

    if (!total) {
        elements.emptyState.hidden = false;
        elements.postList.hidden = true;
        elements.emptyState.innerHTML = state.sourceName
            ? "<h2>没有匹配结果</h2><p>换一个筛选条件，或者重新加载数据。</p>"
            : "<h2>等待载入</h2><p>先选择一个合并后的 JSON，或者一个导出的 Markdown 文件。</p>";
        return;
    }

    elements.emptyState.hidden = true;
    elements.postList.hidden = false;

    const posts = getCurrentPagePosts();
    elements.postList.innerHTML = posts.map((post) => renderPostCard(post)).join("");
    hydratePostImages();
}

function renderPostCard(post, options = {}) {
    const nested = Boolean(options.nested);
    const trail = Array.isArray(options.trail) ? options.trail : [];
    const escapedPostNo = escapeHtml(post.post_no);
    const escapedUserId = escapeHtml(post.user_id);
    const escapedTitle = escapeHtml(post.title);
    const escapedTime = escapeHtml(post.time);
    const contentHtml = renderPostContent(post, trail);
    const poChip = post.PO ? `<span class="po-chip">PO</span>` : "";
    const titleChip = post.title ? `<span class="title-chip">${escapedTitle}</span>` : "";
    const imageHtml = renderImage(post);
    const trailValue = escapeAttribute(JSON.stringify([...trail, post.post_no].filter(Boolean)));
    const cardClass = nested ? "post-card embedded-post-card" : "post-card";

    return `
        <article class="${cardClass}" data-post-id="${escapedPostNo}" data-post-trail="${trailValue}">
            <div class="post-head">
                <span class="post-no">${escapedPostNo}</span>
                <span class="user-chip">ID: ${escapedUserId || "未知"}</span>
                ${poChip}
                ${titleChip}
                <span class="post-time">${escapedTime || ""}</span>
            </div>
            <div class="post-body">
                <div class="post-content">${contentHtml || "(无内容)"}</div>
                ${imageHtml}
            </div>
        </article>
    `;
}

function renderPostContent(post, trail = []) {
    const content = String(post.content || "");
    if (!content) {
        return "";
    }

    const pattern = />>\s*(?:No|Po)\.\d+|\[h\][\s\S]*?\[\/h\]/gi;
    let lastIndex = 0;
    let html = "";

    for (const match of content.matchAll(pattern)) {
        const matchedText = match[0];
        const index = match.index ?? 0;
        html += formatContentText(content.slice(lastIndex, index));
        html += matchedText.toLowerCase().startsWith("[h]")
            ? renderHiddenText(matchedText)
            : renderReferenceButton(matchedText, trail, post.post_no);
        lastIndex = index + matchedText.length;
    }

    html += formatContentText(content.slice(lastIndex));
    return html;
}

function formatContentText(text) {
    return escapeHtml(text).replace(/\n/g, "<br>");
}

function renderReferenceButton(referenceText, trail, sourcePostNo) {
    return `<button type="button" class="post-ref-link" data-ref-target="${escapeAttribute(referenceText)}" data-source-post="${escapeAttribute(sourcePostNo || "")}" data-ref-trail="${escapeAttribute(JSON.stringify(trail))}">${escapeHtml(referenceText)}</button>`;
}

function renderHiddenText(hiddenText) {
    const innerText = String(hiddenText || "").replace(/^\[h\]/i, "").replace(/\[\/h\]$/i, "");
    return `<button type="button" class="post-hidden-text" data-hidden-revealed="false">${formatContentText(innerText)}</button>`;
}

function handlePostListClick(event) {
    const hiddenTextButton = event.target.closest(".post-hidden-text");
    if (hiddenTextButton) {
        event.preventDefault();
        toggleHiddenText(hiddenTextButton);
        return;
    }

    const button = event.target.closest(".post-ref-link");
    if (!button) {
        return;
    }

    event.preventDefault();
    toggleReferencedPost(button);
}

function toggleHiddenText(button) {
    const nextRevealed = button.dataset.hiddenRevealed !== "true";
    button.dataset.hiddenRevealed = String(nextRevealed);
    button.classList.toggle("is-revealed", nextRevealed);
}

function toggleReferencedPost(button) {
    const referenceText = button.dataset.refTarget || "";
    const post = findReferencedPost(referenceText);
    const hostCard = button.closest(".post-card");
    const contentContainer = button.closest(".post-content");
    if (!hostCard || !contentContainer) {
        return;
    }

    const normalizedTarget = normalizeReferenceToken(referenceText);
    const existing = button.previousElementSibling;
    if (existing && existing.dataset && existing.dataset.inlineRefKey === normalizedTarget) {
        existing.remove();
        return;
    }

    const previousInlineRef = button.previousElementSibling;
    if (previousInlineRef && previousInlineRef.dataset && previousInlineRef.dataset.inlineRefKey) {
        previousInlineRef.remove();
    }

    const inlineWrapper = document.createElement("div");
    inlineWrapper.className = "embedded-inline-post";
    inlineWrapper.dataset.inlineRefKey = normalizedTarget;

    const trail = parseTrail(hostCard.dataset.postTrail);
    if (!post) {
        inlineWrapper.innerHTML = `<div class="embedded-post-empty">未找到 ${escapeHtml(referenceText)} 对应的条目</div>`;
        button.insertAdjacentElement("beforebegin", inlineWrapper);
        return;
    }

    if (trail.includes(post.post_no)) {
        inlineWrapper.innerHTML = `<div class="embedded-post-empty">检测到循环引用：${escapeHtml(referenceText)}</div>`;
        button.insertAdjacentElement("beforebegin", inlineWrapper);
        return;
    }

    inlineWrapper.innerHTML = renderPostCard(post, { nested: true, trail });
    button.insertAdjacentElement("beforebegin", inlineWrapper);
    hydratePostImages();
}

function parseTrail(rawTrail) {
    try {
        const parsed = JSON.parse(rawTrail || "[]");
        return Array.isArray(parsed) ? parsed : [];
    } catch {
        return [];
    }
}

function renderImage(post) {
    if (!post.img_url) {
        return "";
    }

    const localSrc = resolveLocalImageSync(post);
    const remoteSrc = post.img_url;
    const src = localSrc || remoteSrc;
    const showFallback = !localSrc;
    const fallback = showFallback
        ? `<p class="post-image-fallback">未匹配到本地图片，回退到远程地址：<a href="${escapeAttribute(remoteSrc)}" target="_blank" rel="noreferrer">打开原图</a></p>`
        : "";

    return `
        <div class="post-image-wrap">
            <img
                class="post-image"
                src="${escapeAttribute(src)}"
                alt="${escapeAttribute(post.post_no)}"
                data-post-no="${escapeAttribute(post.post_no)}"
                data-img-url="${escapeAttribute(post.img_url)}"
            >
            ${fallback}
        </div>
    `;
}

function resolveLocalImageSync(post) {
    if (!state.imageMap.size || !post.post_no || !post.img_url) {
        return "";
    }

    const candidates = getLocalImageCandidates(post.post_no, post.img_url);
    for (const candidate of candidates) {
        const matched = state.imageMap.get(candidate.toLowerCase());
        if (matched) {
            return matched;
        }
    }
    return "";
}

function getLocalImageCandidates(postNo, imgUrl) {
    const cleanNo = String(postNo || "").replace(/^No\./, "");
    const extMatch = String(imgUrl || "").toLowerCase().match(/\.([a-z0-9]+)(?:[?#]|$)/);
    const ext = extMatch ? extMatch[1] : "";
    const candidates = [];

    function pushCandidate(value) {
        if (!value) {
            return;
        }
        const normalized = value.toLowerCase();
        if (candidates.some((item) => item.toLowerCase() === normalized)) {
            return;
        }
        candidates.push(value);
    }

    if (cleanNo && ext) {
        pushCandidate(`${cleanNo}.${ext}`);
    }
    for (const fallbackExt of IMAGE_EXTENSION_CANDIDATES) {
        if (cleanNo) {
            pushCandidate(`${cleanNo}.${fallbackExt}`);
        }
    }
    if (cleanNo) {
        pushCandidate(cleanNo);
    }
    return candidates;
}

async function hydratePostImages() {
    if (state.imageMode !== "handle" || !state.imageDirHandle) {
        return;
    }

    const images = Array.from(document.querySelectorAll(".post-image[data-post-no][data-img-url]"));
    for (const img of images) {
        const postNo = img.dataset.postNo || "";
        const imgUrl = img.dataset.imgUrl || "";
        const localUrl = await resolveLocalImageFromHandle(postNo, imgUrl);
        if (!localUrl) {
            continue;
        }

        img.src = localUrl;
        const fallback = img.parentElement?.querySelector(".post-image-fallback");
        if (fallback) {
            fallback.remove();
        }
    }
}

async function resolveLocalImageFromHandle(postNo, imgUrl) {
    if (!state.imageDirHandle) {
        return "";
    }

    const candidates = getLocalImageCandidates(postNo, imgUrl);
    for (const candidate of candidates) {
        const cacheKey = candidate.toLowerCase();
        if (state.imageUrlCache.has(cacheKey)) {
            return state.imageUrlCache.get(cacheKey);
        }

        try {
            const fileHandle = await state.imageDirHandle.getFileHandle(candidate);
            const file = await fileHandle.getFile();
            const url = URL.createObjectURL(file);
            state.objectUrls.push(url);
            state.imageUrlCache.set(cacheKey, url);
            return url;
        } catch (error) {
            if (error && error.name !== "NotFoundError") {
                console.error("读取本地图片失败", candidate, error);
            }
        }
    }

    return "";
}

function escapeHtml(value) {
    return value
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
    return escapeHtml(value);
}

function revokeObjectUrls() {
    for (const url of state.objectUrls) {
        URL.revokeObjectURL(url);
    }
    state.objectUrls = [];
}
