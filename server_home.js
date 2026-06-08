const homeState = {
    allRecords: [],
    filteredRecords: [],
    currentPage: 1,
    pageSize: 10,
    theme: localStorage.getItem(window.ThreadReaderAuth.THEME_STORAGE_KEY) || "day",
    seriesOptions: [],
    genreOptions: [],
    sessionUsername: "",
    sidebarOpen: false,
    mobileToolsExpanded: false,
};

const homeSidebarMediaQuery = window.matchMedia("(max-width: 1080px)");

const homeElements = {
    sessionUser: document.getElementById("sessionUser"),
    logoutButton: document.getElementById("logoutButton"),
    keywordInput: document.getElementById("keywordInput"),
    authorInput: document.getElementById("authorInput"),
    seriesInput: document.getElementById("seriesInput"),
    seriesSelect: document.getElementById("seriesSelect"),
    genreInput: document.getElementById("genreInput"),
    genreSelect: document.getElementById("genreSelect"),
    statusFilterSelect: document.getElementById("statusFilterSelect"),
    sortSelect: document.getElementById("sortSelect"),
    themeSelect: document.getElementById("themeSelect"),
    resetFiltersButton: document.getElementById("resetFiltersButton"),
    summaryLine: document.getElementById("summaryLine"),
    pageSizeInput: document.getElementById("pageSizeInput"),
    mobilePageSizeInput: document.getElementById("mobilePageSizeInput"),
    pageInfo: document.getElementById("pageInfo"),
    mobilePageInfo: document.getElementById("mobilePageInfo"),
    jumpPageInput: document.getElementById("jumpPageInput"),
    mobileJumpPageInput: document.getElementById("mobileJumpPageInput"),
    jumpPageButton: document.getElementById("jumpPageButton"),
    mobileJumpPageButton: document.getElementById("mobileJumpPageButton"),
    prevPageButton: document.getElementById("prevPageButton"),
    nextPageButton: document.getElementById("nextPageButton"),
    mobilePrevPageButton: document.getElementById("mobilePrevPageButton"),
    mobileNextPageButton: document.getElementById("mobileNextPageButton"),
    emptyState: document.getElementById("emptyState"),
    emptyMessage: document.getElementById("emptyMessage"),
    catalogList: document.getElementById("catalogList"),
    portalSidebar: document.getElementById("portalSidebar"),
    portalSidebarBackdrop: document.getElementById("portalSidebarBackdrop"),
    portalSidebarToggleButton: document.getElementById("portalSidebarToggleButton"),
    mobileHomeFloat: document.getElementById("mobileHomeFloat"),
    mobileHomePanel: document.getElementById("mobileHomePanel"),
    mobileHomeMenuButton: document.getElementById("mobileHomeMenuButton"),
};

initializeHome();

async function initializeHome() {
    const session = await window.ThreadReaderAuth.requireAuth();
    if (!session) {
        return;
    }

    homeElements.sessionUser.textContent = session.username || "已登录";
    homeElements.themeSelect.value = homeState.theme;
    homeElements.pageSizeInput.value = String(homeState.pageSize);
    homeElements.mobilePageSizeInput.value = String(homeState.pageSize);
    applyHomeTheme();

    homeElements.logoutButton.addEventListener("click", () => {
        window.ThreadReaderAuth.logout("./index.html");
    });
    homeElements.keywordInput.addEventListener("input", applyHomeFilters);
    homeElements.authorInput.addEventListener("input", applyHomeFilters);
    homeElements.seriesInput.addEventListener("input", syncSeriesSelectFromInput);
    homeElements.seriesSelect.addEventListener("change", syncSeriesInputFromSelect);
    homeElements.genreInput.addEventListener("input", syncGenreSelectFromInput);
    homeElements.genreSelect.addEventListener("change", syncGenreInputFromSelect);
    homeElements.statusFilterSelect.addEventListener("change", applyHomeFilters);
    homeElements.sortSelect.addEventListener("change", applyHomeFilters);
    homeElements.themeSelect.addEventListener("change", handleHomeThemeChange);
    homeElements.resetFiltersButton.addEventListener("click", resetHomeFilters);
    homeElements.pageSizeInput.addEventListener("change", handlePageSizeChange);
    homeElements.pageSizeInput.addEventListener("blur", handlePageSizeChange);
    homeElements.mobilePageSizeInput.addEventListener("change", handlePageSizeChange);
    homeElements.mobilePageSizeInput.addEventListener("blur", handlePageSizeChange);
    homeElements.jumpPageButton.addEventListener("click", () => jumpHomePage("desktop"));
    homeElements.mobileJumpPageButton.addEventListener("click", () => jumpHomePage("mobile"));
    homeElements.jumpPageInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            jumpHomePage("desktop");
        }
    });
    homeElements.mobileJumpPageInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            jumpHomePage("mobile");
        }
    });
    homeElements.prevPageButton.addEventListener("click", () => changeHomePage(-1));
    homeElements.nextPageButton.addEventListener("click", () => changeHomePage(1));
    homeElements.mobilePrevPageButton.addEventListener("click", () => changeHomePage(-1));
    homeElements.mobileNextPageButton.addEventListener("click", () => changeHomePage(1));
    homeElements.catalogList.addEventListener("click", handleCatalogListClick);
    homeElements.portalSidebarToggleButton.addEventListener("click", openHomeSidebarFromTools);
    homeElements.mobileHomeMenuButton.addEventListener("click", toggleHomeMobileTools);
    homeElements.portalSidebarBackdrop.addEventListener("click", () => setHomeSidebarOpen(false));
    window.addEventListener("keydown", handleHomeGlobalKeydown);
    window.addEventListener("pointerdown", handleHomePointerDown);
    homeSidebarMediaQuery.addEventListener("change", handleHomeSidebarViewportChange);
    setHomeSidebarOpen(false);
    setHomeMobileToolsExpanded(false);

    try {
        const data = await window.ThreadReaderAuth.apiRequest("/api/index");
        if (!Array.isArray(data)) {
            throw new Error("目录索引格式不正确。");
        }

        homeState.allRecords = data.map(normalizeRecord);
        rebuildSeriesOptions(homeState.allRecords);
        rebuildGenreOptions(homeState.allRecords);
        rebuildStatusOptions(homeState.allRecords);
        applyHomeFilters();
    } catch (error) {
        homeElements.summaryLine.textContent = "目录读取失败";
        homeElements.emptyMessage.textContent = error.message || "读取目录失败。";
        homeElements.emptyState.hidden = false;
        homeElements.catalogList.innerHTML = "";
        updatePager(0);
    }
}

function normalizeRecord(record) {
    return {
        id: String(record.id || "").trim(),
        title: String(record.title || "").trim(),
        folder: String(record.folder || "").trim(),
        po_user_id: String(record.po_user_id || "").trim(),
        post_count: Number(record.post_count || 0),
        image_count: Number(record.image_count || 0),
        updated_at: String(record.updated_at || "").trim(),
        tags: Array.isArray(record.tags)
            ? record.tags.map((item) => String(item || "").trim()).filter(Boolean)
            : [],
        series: String(record.series || "").trim(),
        installment: record.installment ?? "",
        genre: String(record.genre || "").trim(),
        status: String(record.status || "").trim(),
        read: Boolean(record.read),
    };
}

function rebuildStatusOptions(records) {
    const statuses = Array.from(new Set(
        records.map((record) => record.status).filter(Boolean),
    )).sort((a, b) => a.localeCompare(b, "zh-CN"));

    homeElements.statusFilterSelect.innerHTML = [
        '<option value="">全部</option>',
        ...statuses.map((status) => `<option value="${escapeHtml(status)}">${escapeHtml(status)}</option>`),
    ].join("");
}

function rebuildSeriesOptions(records) {
    homeState.seriesOptions = Array.from(new Set(
        records.map((record) => record.series).filter(Boolean),
    )).sort((a, b) => a.localeCompare(b, "zh-CN"));

    homeElements.seriesSelect.innerHTML = [
        '<option value="">全部</option>',
        ...homeState.seriesOptions.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`),
    ].join("");
}

function rebuildGenreOptions(records) {
    homeState.genreOptions = Array.from(new Set(
        records.map((record) => record.genre).filter(Boolean),
    )).sort((a, b) => a.localeCompare(b, "zh-CN"));

    homeElements.genreSelect.innerHTML = [
        '<option value="">全部</option>',
        ...homeState.genreOptions.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`),
    ].join("");
}

function handleHomeThemeChange() {
    homeState.theme = homeElements.themeSelect.value;
    localStorage.setItem(window.ThreadReaderAuth.THEME_STORAGE_KEY, homeState.theme);
    applyHomeTheme();
}

function applyHomeTheme() {
    document.body.dataset.theme = homeState.theme;
}

function isHomeSidebarMobile() {
    return homeSidebarMediaQuery.matches;
}

function setHomeSidebarOpen(open) {
    homeState.sidebarOpen = Boolean(open) && isHomeSidebarMobile();
    updateHomeSidebarUI();
}

function openHomeSidebarFromTools() {
    if (!isHomeSidebarMobile()) {
        return;
    }
    setHomeMobileToolsExpanded(false);
    setHomeSidebarOpen(true);
}

function updateHomeSidebarUI() {
    const mobile = isHomeSidebarMobile();
    const isOpen = mobile && homeState.sidebarOpen;
    homeElements.portalSidebar.classList.toggle("is-open", isOpen);
    homeElements.portalSidebarBackdrop.hidden = !isOpen;
}

function handleHomeSidebarViewportChange() {
    if (!isHomeSidebarMobile()) {
        homeState.sidebarOpen = false;
        homeState.mobileToolsExpanded = false;
    }
    updateHomeSidebarUI();
    updateHomeMobileToolsUI();
}

function handleHomeGlobalKeydown(event) {
    if (event.key === "Escape" && isHomeSidebarMobile()) {
        if (homeState.sidebarOpen) {
            setHomeSidebarOpen(false);
            return;
        }
        setHomeMobileToolsExpanded(false);
    }
}

function handleHomePointerDown(event) {
    if (!isHomeSidebarMobile() || !homeState.mobileToolsExpanded) {
        return;
    }

    const target = event.target;
    if (!(target instanceof Node)) {
        return;
    }

    if (homeElements.mobileHomeFloat?.contains(target) || homeElements.portalSidebar?.contains(target)) {
        return;
    }

    setHomeMobileToolsExpanded(false);
}

function setHomeMobileToolsExpanded(open) {
    homeState.mobileToolsExpanded = Boolean(open) && isHomeSidebarMobile();
    updateHomeMobileToolsUI();
}

function toggleHomeMobileTools() {
    if (!isHomeSidebarMobile()) {
        return;
    }
    setHomeMobileToolsExpanded(!homeState.mobileToolsExpanded);
}

function updateHomeMobileToolsUI() {
    const expanded = isHomeSidebarMobile() && homeState.mobileToolsExpanded;
    if (homeElements.mobileHomePanel) {
        homeElements.mobileHomePanel.hidden = !expanded;
        homeElements.mobileHomePanel.classList.toggle("is-open", expanded);
    }
    if (homeElements.mobileHomeFloat) {
        homeElements.mobileHomeFloat.classList.toggle("is-expanded", expanded);
    }
    if (homeElements.mobileHomeMenuButton) {
        homeElements.mobileHomeMenuButton.setAttribute("aria-expanded", String(expanded));
        homeElements.mobileHomeMenuButton.classList.toggle("is-active", expanded);
    }
}

function handlePageSizeChange() {
    const activeInput = document.activeElement === homeElements.mobilePageSizeInput
        ? homeElements.mobilePageSizeInput
        : homeElements.pageSizeInput;
    const parsed = Number(activeInput.value || homeElements.pageSizeInput.value || homeElements.mobilePageSizeInput.value);
    homeState.pageSize = Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : 10;
    homeElements.pageSizeInput.value = String(homeState.pageSize);
    homeElements.mobilePageSizeInput.value = String(homeState.pageSize);
    homeState.currentPage = 1;
    setHomeMobileToolsExpanded(false);
    renderHome();
}

function resetHomeFilters() {
    homeElements.keywordInput.value = "";
    homeElements.authorInput.value = "";
    homeElements.seriesInput.value = "";
    homeElements.seriesSelect.value = "";
    homeElements.genreInput.value = "";
    homeElements.genreSelect.value = "";
    homeElements.statusFilterSelect.value = "";
    homeElements.sortSelect.value = "updated-desc";
    homeState.currentPage = 1;
    homeState.pageSize = 10;
    homeElements.pageSizeInput.value = "10";
    homeElements.mobilePageSizeInput.value = "10";
    applyHomeFilters();
}

function applyHomeFilters() {
    const keyword = homeElements.keywordInput.value.trim().toLowerCase();
    const author = homeElements.authorInput.value.trim().toLowerCase();
    const series = (homeElements.seriesInput.value.trim() || homeElements.seriesSelect.value.trim()).toLowerCase();
    const genre = (homeElements.genreInput.value.trim() || homeElements.genreSelect.value.trim()).toLowerCase();
    const status = homeElements.statusFilterSelect.value.trim();
    const sortMode = homeElements.sortSelect.value;

    let records = homeState.allRecords.filter((record) => matchesHomeFilters(record, keyword, author, series, genre, status));
    records = sortRecords(records, sortMode);
    homeState.filteredRecords = records;
    homeState.currentPage = 1;
    renderHome();
}

function matchesHomeFilters(record, keyword, author, series, genre, status) {
    if (status && record.status !== status) {
        return false;
    }

    if (author && !record.po_user_id.toLowerCase().includes(author)) {
        return false;
    }

    if (series && !record.series.toLowerCase().includes(series)) {
        return false;
    }

    if (genre && !record.genre.toLowerCase().includes(genre)) {
        return false;
    }

    if (!keyword) {
        return true;
    }

    const haystack = [
        record.title,
        record.folder,
        record.po_user_id,
        record.series,
        String(record.installment ?? ""),
        record.genre,
        record.status,
        ...record.tags,
    ].join(" ").toLowerCase();

    return haystack.includes(keyword);
}

function sortRecords(records, sortMode) {
    const cloned = [...records];
    cloned.sort((left, right) => compareRecords(left, right, sortMode));
    return cloned;
}

function compareRecords(left, right, sortMode) {
    const readOrder = compareReadStatus(left, right);
    if (readOrder !== 0) {
        return readOrder;
    }

    switch (sortMode) {
        case "updated-asc":
            return compareText(left.updated_at, right.updated_at) || compareText(left.title, right.title);
        case "post-desc":
            return compareNumber(right.post_count, left.post_count) || compareText(left.title, right.title);
        case "image-desc":
            return compareNumber(right.image_count, left.image_count) || compareText(left.title, right.title);
        case "title-asc":
            return compareText(left.title, right.title);
        case "title-desc":
            return compareText(right.title, left.title);
        case "updated-desc":
        default:
            return compareText(right.updated_at, left.updated_at) || compareText(left.title, right.title);
    }
}

function compareReadStatus(left, right) {
    if (Boolean(left.read) === Boolean(right.read)) {
        return 0;
    }
    return left.read ? 1 : -1;
}

function compareText(left, right) {
    return String(left || "").localeCompare(String(right || ""), "zh-CN");
}

function compareNumber(left, right) {
    return Number(left || 0) - Number(right || 0);
}

function renderHome() {
    const total = homeState.allRecords.length;
    const matched = homeState.filteredRecords.length;
    const totalPages = matched ? Math.ceil(matched / homeState.pageSize) : 0;
    const safeTotalPages = Math.max(totalPages, 1);
    homeState.currentPage = Math.min(Math.max(1, homeState.currentPage), safeTotalPages);

    const startIndex = (homeState.currentPage - 1) * homeState.pageSize;
    const pageRecords = homeState.filteredRecords.slice(startIndex, startIndex + homeState.pageSize);

    homeElements.summaryLine.textContent = `共 ${total} 条目录记录，当前匹配 ${matched} 条`;
    updatePager(totalPages);

    if (!matched) {
        homeElements.emptyMessage.textContent = "当前检索条件下没有结果。";
        homeElements.emptyState.hidden = false;
        homeElements.catalogList.innerHTML = "";
        return;
    }

    homeElements.emptyState.hidden = true;
    homeElements.catalogList.innerHTML = pageRecords.map(renderCatalogCard).join("");
}

function updatePager(totalPages) {
    const displayPage = totalPages ? homeState.currentPage : 0;
    const pageInfoText = `第 ${displayPage} / ${totalPages} 页`;
    const jumpDisabled = !totalPages;
    const prevDisabled = !totalPages || homeState.currentPage <= 1;
    const nextDisabled = !totalPages || homeState.currentPage >= totalPages;

    homeElements.pageInfo.textContent = pageInfoText;
    homeElements.mobilePageInfo.textContent = pageInfoText;
    homeElements.jumpPageButton.disabled = jumpDisabled;
    homeElements.jumpPageInput.disabled = jumpDisabled;
    homeElements.mobileJumpPageButton.disabled = jumpDisabled;
    homeElements.mobileJumpPageInput.disabled = jumpDisabled;
    homeElements.prevPageButton.disabled = prevDisabled;
    homeElements.nextPageButton.disabled = nextDisabled;
    homeElements.mobilePrevPageButton.disabled = prevDisabled;
    homeElements.mobileNextPageButton.disabled = nextDisabled;
}

function changeHomePage(offset) {
    const totalPages = Math.ceil(homeState.filteredRecords.length / homeState.pageSize);
    if (!totalPages) {
        return;
    }

    const nextPage = Math.min(Math.max(1, homeState.currentPage + offset), totalPages);
    if (nextPage === homeState.currentPage) {
        return;
    }

    homeState.currentPage = nextPage;
    setHomeMobileToolsExpanded(false);
    renderHome();
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function jumpHomePage(source = "") {
    const totalPages = Math.ceil(homeState.filteredRecords.length / homeState.pageSize);
    const requested = Number(getHomeJumpInput(source).value);
    if (!totalPages || !requested || requested < 1 || requested > totalPages) {
        return;
    }

    homeState.currentPage = requested;
    homeElements.jumpPageInput.value = String(requested);
    homeElements.mobileJumpPageInput.value = String(requested);
    setHomeMobileToolsExpanded(false);
    renderHome();
    window.scrollTo({ top: 0, behavior: "smooth" });
}

function getHomeJumpInput(source = "") {
    if (source === "mobile") {
        return homeElements.mobileJumpPageInput;
    }
    return homeElements.jumpPageInput;
}

function handleCatalogListClick(event) {
    const button = event.target.closest("[data-toggle-read-folder]");
    if (!button) {
        return;
    }

    const folder = String(button.dataset.toggleReadFolder || "").trim();
    if (!folder) {
        return;
    }

    event.preventDefault();
    toggleFolderReadState(folder);
}

async function toggleFolderReadState(folder) {
    try {
        const response = await window.ThreadReaderAuth.apiRequest(
            `/api/thread/${encodeURIComponent(folder)}/read-state`,
            { method: "POST" },
        );
        const nextRead = Boolean(response.read);
        for (const record of homeState.allRecords) {
            if (record.folder === folder) {
                record.read = nextRead;
            }
        }
        for (const record of homeState.filteredRecords) {
            if (record.folder === folder) {
                record.read = nextRead;
            }
        }
        homeState.filteredRecords = sortRecords(homeState.filteredRecords, homeElements.sortSelect.value);
        renderHome();
    } catch (error) {
        window.alert(error.message || "?????????");
    }
}

function syncSeriesSelectFromInput() {
    const value = homeElements.seriesInput.value.trim();
    homeElements.seriesSelect.value = homeState.seriesOptions.includes(value) ? value : "";
    applyHomeFilters();
}

function syncSeriesInputFromSelect() {
    homeElements.seriesInput.value = homeElements.seriesSelect.value;
    applyHomeFilters();
}

function syncGenreSelectFromInput() {
    const value = homeElements.genreInput.value.trim();
    homeElements.genreSelect.value = homeState.genreOptions.includes(value) ? value : "";
    applyHomeFilters();
}

function syncGenreInputFromSelect() {
    homeElements.genreInput.value = homeElements.genreSelect.value;
    applyHomeFilters();
}

function renderCatalogCard(record) {
    const tags = record.tags.length
        ? `<div class="catalog-tags">${record.tags.map((tag) => `<span class="catalog-tag">${escapeHtml(tag)}</span>`).join("")}</div>`
        : "";

    const seriesLine = record.series
        ? `<p class="catalog-meta">系列：${escapeHtml(record.series)}${record.installment !== "" ? ` / 第 ${escapeHtml(String(record.installment))} 部` : ""}</p>`
        : "";

    const statusLine = record.status
        ? `<span class="catalog-badge">${escapeHtml(record.status)}</span>`
        : "";

    const readerUrl = `./post_reader_server.html?folder=${encodeURIComponent(record.folder)}`;

    return `
        <article class="catalog-card">
            <div class="catalog-card-head">
                <div>
                    <h3>${escapeHtml(record.title || record.folder || "未命名帖子")}</h3>
                    <p class="catalog-meta">文件夹：${escapeHtml(record.folder)}</p>
                </div>
                ${statusLine}
            </div>
            <p class="catalog-meta">PO：${escapeHtml(record.po_user_id || "未知")}</p>
            <p class="catalog-meta">帖子数：${record.post_count} / 图片数：${record.image_count}</p>
            <p class="catalog-meta">更新时间：${escapeHtml(record.updated_at || "未知")}</p>
            ${seriesLine}
            ${record.genre ? `<p class="catalog-meta">类型：${escapeHtml(record.genre)}</p>` : ""}
            ${tags}
            <div class="catalog-card-actions">
                <a class="portal-button" href="${readerUrl}">进入阅读页</a>
            </div>
        </article>
    `;
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}
