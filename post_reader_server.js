const state = {
    sourceFolderName: "",
    threadTitle: "",
    currentPage: 1,
    pageSize: Number(localStorage.getItem("post_reader_page_size") || 20),
    theme: localStorage.getItem(window.ThreadReaderAuth.THEME_STORAGE_KEY) || "day",
    filterScope: localStorage.getItem("post_reader_filter_scope") || "all",
    filterChangeBehavior: localStorage.getItem("post_reader_filter_change_behavior") || "keep-page",
    pageSizeBehavior: localStorage.getItem("post_reader_page_size_behavior") || "keep-first-item",
    currentPosts: [],
    postCache: new Map(),
    rawTotalPosts: 0,
    rawTotalPages: 0,
    filteredTotalPosts: 0,
    filteredTotalPages: 0,
    activeTotalPages: 0,
    currentRawPagePosts: 0,
    loading: false,
    filterDebounceTimer: null,
    jumpFilterBypassed: false,
    pendingScrollPostNo: "",
    bookmarks: [],
    bookmarkSet: new Set(),
    read: false,
    sessionUsername: "",
    sidebarOpen: false,
    mobileToolsExpanded: false,
};

const mobileSidebarMediaQuery = window.matchMedia("(max-width: 1080px)");

const elements = {
    logoutButton: document.getElementById("logoutButton"),
    threadTitle: document.getElementById("threadTitle"),
    threadFolder: document.getElementById("threadFolder"),
    imageModeSummary: document.getElementById("imageModeSummary"),
    sourceSummary: document.getElementById("sourceSummary"),
    bookmarkSummary: document.getElementById("bookmarkSummary"),
    bookmarkList: document.getElementById("bookmarkList"),
    toggleReadButton: document.getElementById("toggleReadButton"),
    themeSelect: document.getElementById("themeSelect"),
    userFilterInput: document.getElementById("userFilterInput"),
    poFilterSelect: document.getElementById("poFilterSelect"),
    filterScopeSelect: document.getElementById("filterScopeSelect"),
    filterChangeBehaviorSelect: document.getElementById("filterChangeBehaviorSelect"),
    pageSizeBehaviorSelect: document.getElementById("pageSizeBehaviorSelect"),
    pageSizeSelect: document.getElementById("pageSizeSelect"),
    toolbarPageSizeSelect: document.getElementById("toolbarPageSizeSelect"),
    resetFiltersButton: document.getElementById("resetFiltersButton"),
    jumpPageInput: document.getElementById("jumpPageInput"),
    jumpPageButton: document.getElementById("jumpPageButton"),
    toolbarJumpPageInput: document.getElementById("toolbarJumpPageInput"),
    toolbarJumpPageButton: document.getElementById("toolbarJumpPageButton"),
    prevPageButton: document.getElementById("prevPageButton"),
    nextPageButton: document.getElementById("nextPageButton"),
    mobilePrevPageButton: document.getElementById("mobilePrevPageButton"),
    mobileNextPageButton: document.getElementById("mobileNextPageButton"),
    statsLine: document.getElementById("statsLine"),
    pageInfo: document.getElementById("pageInfo"),
    mobilePageInfo: document.getElementById("mobilePageInfo"),
    renderHint: document.getElementById("renderHint"),
    mobileRenderHint: document.getElementById("mobileRenderHint"),
    emptyState: document.getElementById("emptyState"),
    postList: document.getElementById("postList"),
    sidebarPanel: document.getElementById("sidebarPanel"),
    sidebarBackdrop: document.getElementById("sidebarBackdrop"),
    mobileReaderFloat: document.getElementById("mobileReaderFloat"),
    mobileReaderPanel: document.getElementById("mobileReaderPanel"),
    mobileReaderMenuButton: document.getElementById("mobileReaderMenuButton"),
    mobileJumpPageInput: document.getElementById("mobileJumpPageInput"),
    mobileJumpPageButton: document.getElementById("mobileJumpPageButton"),
    mobileSidebarOpenButton: document.getElementById("mobileSidebarOpenButton"),
};

initializeReader();

async function initializeReader() {
    const session = await window.ThreadReaderAuth.requireAuth();
    if (!session) {
        return;
    }

    state.sessionUsername = String(session.username || "").trim();
    state.sourceFolderName = String(new URLSearchParams(window.location.search).get("folder") || "").trim();

    elements.pageSizeSelect.value = String(state.pageSize);
    elements.toolbarPageSizeSelect.value = String(state.pageSize);
    elements.themeSelect.value = state.theme;
    elements.filterScopeSelect.value = state.filterScope;
    elements.filterChangeBehaviorSelect.value = state.filterChangeBehavior;
    elements.pageSizeBehaviorSelect.value = state.pageSizeBehavior;
    applyTheme();

    bindEvents();
    setSidebarOpen(false);
    setMobileToolsExpanded(false);
    updateSummary();
    renderBookmarks();
    render();

    if (!state.sourceFolderName) {
        showEmptyState("缺少帖子目录", "请从目录页进入，或者在地址栏附带 ?folder=帖子文件夹名。");
        return;
    }

    await Promise.all([
        loadView({ reason: "data-load" }),
        loadBookmarks(),
        loadReadState(),
    ]);
}

function bindEvents() {
    elements.logoutButton.addEventListener("click", () => {
        window.ThreadReaderAuth.logout("./index.html");
    });
    elements.themeSelect.addEventListener("change", handleThemeChange);
    elements.userFilterInput.addEventListener("input", () => scheduleFilterApply({ reason: "filter-change" }));
    elements.poFilterSelect.addEventListener("change", () => loadView({ reason: "filter-change" }));
    elements.filterScopeSelect.addEventListener("change", handleFilterScopeChange);
    elements.filterChangeBehaviorSelect.addEventListener("change", handleFilterChangeBehavior);
    elements.pageSizeBehaviorSelect.addEventListener("change", handlePageSizeBehavior);
    elements.pageSizeSelect.addEventListener("change", handlePageSizeChange);
    elements.toolbarPageSizeSelect.addEventListener("change", handlePageSizeChange);
    elements.resetFiltersButton.addEventListener("click", resetFilters);
    elements.jumpPageButton.addEventListener("click", () => jumpToPage("panel"));
    elements.toolbarJumpPageButton.addEventListener("click", () => jumpToPage("toolbar"));
    elements.mobileJumpPageButton.addEventListener("click", () => jumpToPage("mobile"));
    elements.jumpPageInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            jumpToPage("panel");
        }
    });
    elements.toolbarJumpPageInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            jumpToPage("toolbar");
        }
    });
    elements.mobileJumpPageInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            jumpToPage("mobile");
        }
    });
    elements.prevPageButton.addEventListener("click", () => changePage(-1));
    elements.nextPageButton.addEventListener("click", () => changePage(1));
    elements.mobilePrevPageButton.addEventListener("click", () => changePage(-1));
    elements.mobileNextPageButton.addEventListener("click", () => changePage(1));
    elements.postList.addEventListener("click", handlePostListClick);
    elements.postList.addEventListener("error", handlePostImageError, true);
    elements.bookmarkList.addEventListener("click", handleBookmarkListClick);
    elements.toggleReadButton.addEventListener("click", toggleReadState);
    elements.mobileReaderMenuButton.addEventListener("click", toggleMobileTools);
    elements.mobileSidebarOpenButton.addEventListener("click", openSidebarFromMobileTools);
    elements.sidebarBackdrop.addEventListener("click", () => setSidebarOpen(false));
    window.addEventListener("keydown", handleGlobalKeydown);
    window.addEventListener("pointerdown", handleGlobalPointerDown);
    mobileSidebarMediaQuery.addEventListener("change", handleSidebarViewportChange);
}

function handleGlobalKeydown(event) {
    if (event.key === "Escape" && isMobileSidebar()) {
        if (state.sidebarOpen) {
            setSidebarOpen(false);
            return;
        }
        setMobileToolsExpanded(false);
    }
}

function isMobileSidebar() {
    return mobileSidebarMediaQuery.matches;
}

function handleSidebarViewportChange() {
    if (!isMobileSidebar()) {
        state.sidebarOpen = false;
        state.mobileToolsExpanded = false;
    }
    updateSidebarUI();
    updateMobileToolsUI();
}

function handleGlobalPointerDown(event) {
    if (!isMobileSidebar() || !state.mobileToolsExpanded) {
        return;
    }

    const target = event.target;
    if (!(target instanceof Node)) {
        return;
    }

    if (elements.mobileReaderFloat?.contains(target) || elements.sidebarPanel?.contains(target)) {
        return;
    }

    setMobileToolsExpanded(false);
}

function scheduleFilterApply(options) {
    clearTimeout(state.filterDebounceTimer);
    state.filterDebounceTimer = window.setTimeout(() => {
        loadView(options);
    }, 180);
}

async function loadView(options = {}) {
    if (!state.sourceFolderName || state.loading) {
        return;
    }

    const reason = options.reason || "filter-change";
    const anchorPost = options.anchorPost || null;
    state.pendingScrollPostNo = anchorPost?.post_no || "";

    if (reason === "filter-change" && state.filterChangeBehavior === "first-page") {
        state.currentPage = 1;
    }
    if (reason === "page-size-change" && state.pageSizeBehavior === "first-page") {
        state.currentPage = 1;
    }

    state.loading = true;
    state.jumpFilterBypassed = false;
    updateSummary();
    render();

    try {
        const params = new URLSearchParams({
            page: String(state.currentPage),
            page_size: String(state.pageSize),
            user_filter: elements.userFilterInput.value,
            po_mode: elements.poFilterSelect.value,
            filter_scope: state.filterScope,
            reason,
            filter_change_behavior: state.filterChangeBehavior,
            page_size_behavior: state.pageSizeBehavior,
        });

        if (anchorPost?.post_no) {
            params.set("anchor_post_no", anchorPost.post_no);
        }

        const response = await window.ThreadReaderAuth.apiRequest(
            `/api/thread/${encodeURIComponent(state.sourceFolderName)}/view?${params.toString()}`,
        );

        state.threadTitle = String(response.thread_title || state.sourceFolderName).trim();
        state.currentPage = Number(response.page || 1);
        state.pageSize = Number(response.page_size || state.pageSize);
        state.currentPosts = Array.isArray(response.posts) ? response.posts.map(normalizePost) : [];
        state.rawTotalPosts = Number(response.raw_total_posts || 0);
        state.rawTotalPages = Number(response.raw_total_pages || 0);
        state.filteredTotalPosts = Number(response.filtered_total_posts || 0);
        state.filteredTotalPages = Number(response.filtered_total_pages || 0);
        state.activeTotalPages = Number(response.active_total_pages || 0);
        state.currentRawPagePosts = Number(response.current_raw_page_posts || 0);
        state.jumpFilterBypassed = Boolean(response.jump_filter_bypassed);

        state.postCache.clear();
        for (const post of state.currentPosts) {
            cachePost(post);
        }

        syncReaderPagingControls();
    } catch (error) {
        state.pendingScrollPostNo = "";
        showEmptyState("加载失败", error.message || "读取帖子失败。");
    } finally {
        state.loading = false;
        updateSummary();
        render();
        scrollToPendingPostIfNeeded();
    }
}

async function loadBookmarks() {
    if (!state.sourceFolderName) {
        return;
    }

    try {
        const response = await window.ThreadReaderAuth.apiRequest(
            `/api/thread/${encodeURIComponent(state.sourceFolderName)}/bookmarks`,
        );
        setBookmarks(Array.isArray(response.bookmarks) ? response.bookmarks.map(normalizePost) : []);
    } catch {
        setBookmarks([]);
    }
}

async function loadReadState() {
    if (!state.sourceFolderName) {
        return;
    }

    try {
        const response = await window.ThreadReaderAuth.apiRequest(
            `/api/thread/${encodeURIComponent(state.sourceFolderName)}/read-state`,
        );
        state.read = Boolean(response.read);
    } catch {
        state.read = false;
    } finally {
        render();
    }
}

function setBookmarks(bookmarks) {
    state.bookmarks = bookmarks;
    state.bookmarkSet = new Set(bookmarks.map((item) => item.post_no));
    renderBookmarks();
    render();
}

async function toggleBookmark(post) {
    if (!post?.post_no || !post?.folder) {
        return;
    }

    try {
        const response = await window.ThreadReaderAuth.apiRequest(
            `/api/thread/${encodeURIComponent(post.folder)}/bookmark`,
            {
                method: "POST",
                body: JSON.stringify({ post_no: post.post_no }),
                headers: { "Content-Type": "application/json" },
            },
        );
        setBookmarks(Array.isArray(response.bookmarks) ? response.bookmarks.map(normalizePost) : []);
    } catch (error) {
        window.alert(error.message || "更新书签失败。");
    }
}

async function toggleReadState() {
    if (!state.sourceFolderName) {
        return;
    }

    try {
        const response = await window.ThreadReaderAuth.apiRequest(
            `/api/thread/${encodeURIComponent(state.sourceFolderName)}/read-state`,
            { method: "POST" },
        );
        state.read = Boolean(response.read);
        render();
    } catch (error) {
        window.alert(error.message || "更新已读状态失败。");
    }
}

function normalizePost(post) {
    return {
        folder: String(post.folder || state.sourceFolderName || "").trim(),
        thread_title: String(post.thread_title || "").trim(),
        post_no: String(post.post_no || "").trim(),
        user_id: String(post.user_id || "").trim(),
        PO: String(post.PO || "").trim(),
        time: String(post.time || "").trim(),
        title: String(post.title || "").trim(),
        email: String(post.email || "").trim(),
        content: String(post.content || "").replace(/\r\n/g, "\n").trim(),
        img_url: String(post.img_url || "").trim(),
        image_ext: normalizeImageExt(post.image_ext || ""),
        bookmarked_at: Number(post.bookmarked_at || 0),
    };
}

function normalizeImageExt(value) {
    const text = String(value || "").trim().toLowerCase();
    if (!text) {
        return "";
    }
    if (text.includes(".")) {
        const parts = text.split(".");
        return String(parts[parts.length - 1] || "").trim().toLowerCase();
    }
    return text;
}

function cachePost(post) {
    for (const key of getLookupKeysFromPostNo(post.post_no)) {
        state.postCache.set(key, post);
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
        keys.add(`no.${poMatch[1]}`.toLowerCase());
    }
    if (hashMatch) {
        keys.add(`#${hashMatch[1]}`.toLowerCase());
        keys.add(`po.${hashMatch[1]}`.toLowerCase());
        keys.add(`no.${hashMatch[1]}`.toLowerCase());
    }

    return Array.from(keys);
}

function normalizeReferenceToken(token) {
    return String(token || "").replace(/^>>\s*/i, "").trim().toLowerCase();
}

async function fetchReferencedPost(token) {
    const normalized = normalizeReferenceToken(token);
    const cached = state.postCache.get(normalized);
    if (cached) {
        return cached;
    }

    const response = await window.ThreadReaderAuth.apiRequest(
        `/api/thread/${encodeURIComponent(state.sourceFolderName)}/post?token=${encodeURIComponent(token)}`,
    );
    const post = response?.post ? normalizePost(response.post) : null;
    if (post) {
        cachePost(post);
    }
    return post;
}

function handlePageSizeChange() {
    const anchorPost = getCurrentAnchorPost();
    const source = document.activeElement === elements.toolbarPageSizeSelect
        ? elements.toolbarPageSizeSelect
        : elements.pageSizeSelect;
    state.pageSize = Number(source.value);
    localStorage.setItem("post_reader_page_size", String(state.pageSize));
    syncReaderPagingControls();
    loadView({ reason: "page-size-change", anchorPost });
}

function handleThemeChange() {
    state.theme = elements.themeSelect.value;
    localStorage.setItem(window.ThreadReaderAuth.THEME_STORAGE_KEY, state.theme);
    applyTheme();
}

function handleFilterScopeChange() {
    state.filterScope = elements.filterScopeSelect.value;
    localStorage.setItem("post_reader_filter_scope", state.filterScope);
    loadView({ reason: "filter-change" });
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
    loadView({ reason: "filter-change" });
}

function applyTheme() {
    document.body.dataset.theme = state.theme;
}

function setSidebarOpen(open) {
    state.sidebarOpen = Boolean(open) && isMobileSidebar();
    updateSidebarUI();
}

function openSidebarFromMobileTools() {
    if (!isMobileSidebar()) {
        return;
    }
    setMobileToolsExpanded(false);
    setSidebarOpen(true);
}

function updateSidebarUI() {
    const mobile = isMobileSidebar();
    const isOpen = mobile && state.sidebarOpen;
    elements.sidebarPanel.classList.toggle("is-open", isOpen);
    elements.sidebarBackdrop.hidden = !isOpen;
}

function setMobileToolsExpanded(open) {
    state.mobileToolsExpanded = Boolean(open) && isMobileSidebar();
    updateMobileToolsUI();
}

function toggleMobileTools() {
    if (!isMobileSidebar()) {
        return;
    }
    setMobileToolsExpanded(!state.mobileToolsExpanded);
}

function updateMobileToolsUI() {
    const expanded = isMobileSidebar() && state.mobileToolsExpanded;
    if (elements.mobileReaderPanel) {
        elements.mobileReaderPanel.hidden = !expanded;
        elements.mobileReaderPanel.classList.toggle("is-open", expanded);
    }
    if (elements.mobileReaderFloat) {
        elements.mobileReaderFloat.classList.toggle("is-expanded", expanded);
    }
    if (elements.mobileReaderMenuButton) {
        elements.mobileReaderMenuButton.setAttribute("aria-expanded", String(expanded));
        elements.mobileReaderMenuButton.classList.toggle("is-active", expanded);
    }
}

function getCurrentAnchorPost() {
    return state.currentPosts.length ? state.currentPosts[0] : null;
}

function changePage(offset) {
    const totalPages = state.activeTotalPages || 1;
    const nextPage = Math.min(Math.max(1, state.currentPage + offset), totalPages);
    if (nextPage === state.currentPage) {
        return;
    }
    state.currentPage = nextPage;
    setMobileToolsExpanded(false);
    loadView({ reason: "page-change" });
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function jumpToPage(source = "") {
    const totalPages = state.activeTotalPages;
    const requested = Number(getJumpInputElement(source)?.value);
    if (!requested || requested < 1 || requested > totalPages) {
        return;
    }
    state.currentPage = requested;
    setJumpInputValues(requested);
    setMobileToolsExpanded(false);
    loadView({ reason: "page-change" });
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function syncReaderPagingControls() {
    const pageSize = String(state.pageSize);
    elements.pageSizeSelect.value = pageSize;
    elements.toolbarPageSizeSelect.value = pageSize;
}

function setJumpInputValues(value) {
    const text = value ? String(value) : "";
    elements.jumpPageInput.value = text;
    elements.toolbarJumpPageInput.value = text;
    elements.mobileJumpPageInput.value = text;
}

function getJumpInputElement(source = "") {
    switch (source) {
        case "mobile":
            return elements.mobileJumpPageInput;
        case "toolbar":
            return elements.toolbarJumpPageInput;
        case "panel":
            return elements.jumpPageInput;
        default:
            return [elements.toolbarJumpPageInput, elements.jumpPageInput, elements.mobileJumpPageInput]
                .find((input) => document.activeElement === input)
                || elements.toolbarJumpPageInput;
    }
}

function jumpToPost(postNo) {
    const existing = findRenderedPostCard(postNo);
    if (existing) {
        existing.scrollIntoView({ behavior: "smooth", block: "center" });
        flashPostCard(existing);
        return;
    }

    loadView({
        reason: "bookmark-jump",
        anchorPost: { post_no: postNo },
    });
}

function updateSummary() {
    elements.threadTitle.textContent = state.threadTitle || "阅读页";
    elements.threadFolder.textContent = state.sourceFolderName
        ? `文件夹：${state.sourceFolderName}`
        : "文件夹：未指定";
    elements.imageModeSummary.textContent = state.sourceFolderName
        ? `图片通过后端按需读取：${state.sourceFolderName}`
        : "图片将通过后端鉴权后读取";

    if (!state.sourceFolderName) {
        elements.sourceSummary.textContent = "尚未指定帖子目录";
        return;
    }

    elements.sourceSummary.textContent = "当前阅读页按需读取元数据分片，正文内容通过 SQLite 数据库查询。";
}

function showEmptyState(title, description) {
    elements.emptyState.hidden = false;
    elements.postList.hidden = true;
    elements.emptyState.innerHTML = `<h2>${escapeHtml(title)}</h2><p>${escapeHtml(description)}</p>`;
}

function render() {
    const currentPage = state.activeTotalPages ? Math.min(state.currentPage, state.activeTotalPages) : 0;

    if (state.filterScope === "page") {
        elements.statsLine.textContent = `当前页筛选后 ${state.filteredTotalPosts} / ${state.currentRawPagePosts} 条，原文件共 ${state.rawTotalPosts} 条，${state.rawTotalPages} 页。`;
    } else {
        elements.statsLine.textContent = `整个文件筛选后 ${state.filteredTotalPosts} 条，共 ${state.filteredTotalPages} 页。`;
    }

    const pageInfoText = `第 ${currentPage} / ${state.activeTotalPages} 页`;
    elements.pageInfo.textContent = pageInfoText;
    elements.mobilePageInfo.textContent = pageInfoText;

    let renderHintText = "";
    if (state.loading) {
        renderHintText = "正在按页读取数据…";
    } else if (state.jumpFilterBypassed) {
        renderHintText = "当前筛选隐藏了目标书签，已临时跳到原始分页。";
    } else if (state.sourceFolderName) {
        renderHintText = `当前目录：${state.sourceFolderName} / ${state.filterScope === "page" ? "仅当前页筛选" : "整个文件筛选"}`;
    } else {
        renderHintText = "正在等待目录参数";
    }
    elements.renderHint.textContent = renderHintText;
    elements.mobileRenderHint.textContent = renderHintText;

    const prevDisabled = currentPage <= 1 || state.loading;
    const nextDisabled = !state.activeTotalPages || currentPage >= state.activeTotalPages || state.loading;
    const jumpDisabled = !state.activeTotalPages || state.loading;
    elements.prevPageButton.disabled = prevDisabled;
    elements.nextPageButton.disabled = nextDisabled;
    elements.mobilePrevPageButton.disabled = prevDisabled;
    elements.mobileNextPageButton.disabled = nextDisabled;
    elements.jumpPageButton.disabled = jumpDisabled;
    elements.jumpPageInput.disabled = jumpDisabled;
    elements.toolbarJumpPageButton.disabled = jumpDisabled;
    elements.toolbarJumpPageInput.disabled = jumpDisabled;
    elements.mobileJumpPageButton.disabled = jumpDisabled;
    elements.mobileJumpPageInput.disabled = jumpDisabled;
    elements.toggleReadButton.textContent = state.read ? "取消已阅读" : "标记为已阅读";

    if (!state.filteredTotalPosts) {
        if (state.sourceFolderName && state.rawTotalPosts) {
            showEmptyState("没有匹配结果", "可以换个筛选条件试试。");
        } else if (state.sourceFolderName && !state.loading) {
            showEmptyState("当前帖子没有内容", "服务端已读取线程元数据，但里面没有可显示的条目。");
        }
        return;
    }

    elements.emptyState.hidden = true;
    elements.postList.hidden = false;
    elements.postList.innerHTML = state.currentPosts.map((post) => renderPostCard(post)).join("");
}

function renderBookmarks() {
    const count = state.bookmarks.length;
    elements.bookmarkSummary.textContent = count
        ? `当前 thread 共有 ${count} 个书签`
        : "当前 thread 暂无书签";

    if (!count) {
        elements.bookmarkList.innerHTML = '<p class="bookmark-empty">还没有书签。</p>';
        return;
    }

    elements.bookmarkList.innerHTML = state.bookmarks.map(renderBookmarkItem).join("");
}

function renderBookmarkItem(post) {
    const preview = escapeHtml(buildBookmarkPreview(post));
    const timeText = escapeHtml(post.time || "无时间");
    return `
        <button
            type="button"
            class="bookmark-item"
            data-bookmark-post-no="${escapeAttribute(post.post_no)}"
        >
            <strong>${escapeHtml(post.post_no)}</strong>
            <span>ID: ${escapeHtml(post.user_id || "未知")}</span>
            <span>时间: ${timeText}</span>
            <span>${preview}</span>
        </button>
    `;
}

function buildBookmarkPreview(post) {
    const text = String(post.content || "").replace(/\s+/g, " ").trim();
    return text ? text.slice(0, 60) : "无正文";
}

function renderPostCard(post, options = {}) {
    const nested = Boolean(options.nested);
    const trail = Array.isArray(options.trail) ? options.trail : [];
    const escapedPostNo = escapeHtml(post.post_no);
    const escapedUserId = escapeHtml(post.user_id);
    const escapedTitle = escapeHtml(post.title);
    const escapedTime = escapeHtml(post.time);
    const contentHtml = renderPostContent(post, trail);
    const poChip = post.PO ? '<span class="po-chip">PO</span>' : "";
    const titleChip = post.title ? `<span class="title-chip">${escapedTitle}</span>` : "";
    const imageHtml = renderImage(post);
    const timeHtml = escapedTime ? `<span class="post-time">${escapedTime}</span>` : "";
    const trailValue = escapeAttribute(JSON.stringify([...trail, post.post_no].filter(Boolean)));
    const cardClass = nested ? "post-card embedded-post-card" : "post-card";
    const bookmarkButton = !nested && post.folder === state.sourceFolderName
        ? renderBookmarkButton(post)
        : "";

    return `
        <article class="${cardClass}" data-post-id="${escapeAttribute(post.post_no)}" data-post-trail="${trailValue}">
            <div class="post-head">
                <span class="post-no">${escapedPostNo}</span>
                <span class="user-chip">ID: ${escapedUserId || "未知"}</span>
                ${poChip}
                ${titleChip}
                ${timeHtml}
                ${bookmarkButton}
            </div>
            <div class="post-body">
                <div class="post-content">${contentHtml || "(无内容)"}</div>
                ${imageHtml}
            </div>
        </article>
    `;
}

function renderBookmarkButton(post) {
    const active = state.bookmarkSet.has(post.post_no);
    return `
        <button
            type="button"
            class="post-bookmark-button${active ? " is-active" : ""}"
            data-bookmark-toggle="${escapeAttribute(post.post_no)}"
        >
            ${active ? "已书签" : "加书签"}
        </button>
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
    const bookmarkButton = event.target.closest(".post-bookmark-button");
    if (bookmarkButton) {
        const postNo = String(bookmarkButton.dataset.bookmarkToggle || "").trim();
        const post = state.currentPosts.find((item) => item.post_no === postNo);
        if (post) {
            event.preventDefault();
            toggleBookmark(post);
        }
        return;
    }

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

function handleBookmarkListClick(event) {
    const button = event.target.closest(".bookmark-item");
    if (!button) {
        return;
    }

    const postNo = String(button.dataset.bookmarkPostNo || "").trim();
    if (postNo) {
        jumpToPost(postNo);
    }
}

async function toggleReferencedPost(button) {
    const referenceText = button.dataset.refTarget || "";
    const hostCard = button.closest(".post-card");
    if (!hostCard) {
        return;
    }

    const normalizedTarget = normalizeReferenceToken(referenceText);
    const existing = button.previousElementSibling;
    if (existing?.dataset?.inlineRefKey === normalizedTarget) {
        existing.remove();
        return;
    }

    const previousInlineRef = button.previousElementSibling;
    if (previousInlineRef?.dataset?.inlineRefKey) {
        previousInlineRef.remove();
    }

    const inlineWrapper = document.createElement("div");
    inlineWrapper.className = "embedded-inline-post";
    inlineWrapper.dataset.inlineRefKey = normalizedTarget;
    inlineWrapper.innerHTML = '<div class="embedded-post-empty">正在读取引用…</div>';
    button.insertAdjacentElement("beforebegin", inlineWrapper);

    const trail = parseTrail(hostCard.dataset.postTrail);

    try {
        const post = await fetchReferencedPost(referenceText);
        if (!post) {
            inlineWrapper.innerHTML = `<div class="embedded-post-empty">未找到 ${escapeHtml(referenceText)} 对应的条目。</div>`;
            return;
        }
        if (trail.includes(post.post_no)) {
            inlineWrapper.innerHTML = `<div class="embedded-post-empty">检测到循环引用：${escapeHtml(referenceText)}</div>`;
            return;
        }
        inlineWrapper.innerHTML = renderPostCard(post, { nested: true, trail });
    } catch (error) {
        inlineWrapper.innerHTML = `<div class="embedded-post-empty">读取引用失败：${escapeHtml(error.message || "未知错误")}</div>`;
    }
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
    if (!post.image_ext) {
        return "";
    }

    const candidates = getServerImageCandidates(post);
    if (!candidates.length) {
        return "";
    }

    const localSrc = candidates[0];
    return `
        <div class="post-image-wrap">
            <img
                class="post-image"
                src="${escapeAttribute(localSrc)}"
                alt="${escapeAttribute(post.post_no)}"
                loading="lazy"
                data-image-candidates="${escapeAttribute(JSON.stringify(candidates))}"
                data-image-index="0"
            >
            <p class="post-image-fallback">
                查看原图：
                <a href="${escapeAttribute(localSrc)}" target="_blank" rel="noreferrer">打开</a>
            </p>
        </div>
    `;
}

function getServerImageCandidates(post) {
    const cleanNo = String(post.post_no || "").replace(/^No\./i, "").replace(/^#/, "");
    const folder = encodeURIComponent(post.folder || state.sourceFolderName || "");
    const candidates = [];

    function pushCandidate(candidateExt) {
        const filename = encodeURIComponent(`${cleanNo}.${candidateExt}`);
        const path = `/api/thread/${folder}/image/${filename}`;
        if (!candidates.includes(path)) {
            candidates.push(path);
        }
    }

    const ext = normalizeImageExt(post.image_ext);
    if (!cleanNo || !ext) {
        return candidates;
    }

    pushCandidate(ext);
    return candidates;
}

function handlePostImageError(event) {
    const img = event.target;
    if (!(img instanceof HTMLImageElement) || !img.dataset.imageCandidates) {
        return;
    }

    let candidates = [];
    try {
        candidates = JSON.parse(img.dataset.imageCandidates);
    } catch {
        candidates = [];
    }

    const currentIndex = Number(img.dataset.imageIndex || "0");
    const nextIndex = currentIndex + 1;
    if (!Array.isArray(candidates) || nextIndex >= candidates.length) {
        return;
    }

    img.dataset.imageIndex = String(nextIndex);
    img.src = candidates[nextIndex];

    const fallbackLink = img.parentElement?.querySelector(".post-image-fallback a");
    if (fallbackLink) {
        fallbackLink.href = candidates[nextIndex];
    }
}

function scrollToPendingPostIfNeeded() {
    if (!state.pendingScrollPostNo) {
        return;
    }

    const postNo = state.pendingScrollPostNo;
    state.pendingScrollPostNo = "";
    window.setTimeout(() => {
        const card = findRenderedPostCard(postNo);
        if (!card) {
            return;
        }
        card.scrollIntoView({ behavior: "smooth", block: "center" });
        flashPostCard(card);
    }, 0);
}

function findRenderedPostCard(postNo) {
    const cards = elements.postList.querySelectorAll(".post-card");
    for (const card of cards) {
        if (card.dataset.postId === postNo) {
            return card;
        }
    }
    return null;
}

function flashPostCard(card) {
    card.classList.add("post-card-highlight");
    window.setTimeout(() => {
        card.classList.remove("post-card-highlight");
    }, 1400);
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
    return escapeHtml(value);
}
