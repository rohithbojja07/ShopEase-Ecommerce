(() => {
    "use strict";

    const form = document.getElementById("searchForm");
    const input = document.getElementById("searchInput");
    const filterForm = document.getElementById("filterForm");
    const grid = document.getElementById("productGrid");
    const count = document.getElementById("resultCount");
    const pageInfo = document.getElementById("pageInfo");
    const message = document.getElementById("searchMessage");
    const pagination = document.getElementById("pagination");

    const categoryFilter = document.getElementById("categoryFilter");
    const brandFilter = document.getElementById("brandFilter");
    const subcategoryFilter = document.getElementById("subcategoryFilter");
    const colorFilter = document.getElementById("colorFilter");
    const sizeFilter = document.getElementById("sizeFilter");
    const ratingFilter = document.getElementById("ratingFilter");
    const stockFilterSelect = document.getElementById("stockFilterSelect");
    const minPrice = document.getElementById("minPrice");
    const maxPrice = document.getElementById("maxPrice");
    const sortFilter = document.getElementById("sortFilter");
    const stockFilter = document.getElementById("stockFilter");
    const featuredFilter = document.getElementById("featuredFilter");
    const clearButton = document.getElementById("clearFilters");
    const applyButton = document.getElementById("applyFilters");

    if (!form || !input || !filterForm || !grid) return;

    let currentPage = 1;
    let requestNumber = 0;

    function showMessage(text) {
        message.textContent = text;
        message.classList.remove("d-none");
    }

    function hideMessage() {
        message.textContent = "";
        message.classList.add("d-none");
    }

    async function getJSON(url) {
        const response = await fetch(url, {
            headers: { Accept: "application/json" }
        });

        if (!response.ok) {
            throw new Error(`Request failed (${response.status})`);
        }

        return response.json();
    }

    function fillOptions(select, items) {
        items.forEach((item) => {
            const option = document.createElement("option");
            option.value = item.slug;
            option.textContent = item.name;
            select.appendChild(option);
        });
    }

    async function loadOptions() {
        try {
            const [categories, brands] = await Promise.all([
                getJSON("/api/categories/"),
                getJSON("/api/brands/")
            ]);

            const categoryItems = Array.isArray(categories)
                ? categories
                : (categories.results || categories.value || []);

            const brandItems = Array.isArray(brands)
                ? brands
                : (brands.results || brands.value || []);

            fillOptions(categoryFilter, categoryItems);
            fillOptions(brandFilter, brandItems);
        } catch (error) {
            console.error("Unable to load filter options:", error);
            showMessage("Filter options could not be loaded. You can still search products.");
        }
    }

    function makeElement(tag, className, text) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined && text !== null) element.textContent = text;
        return element;
    }

    function renderProduct(product) {
        const column = makeElement("div", "col-12 col-sm-6 col-lg-4 col-xl-3 product-item");
        const card = makeElement("article", "card product-card h-100");

        if (product.image) {
            const image = makeElement("img", "card-img-top product-image");
            image.src = product.image;
            image.alt = product.name || "Product";
            image.loading = "lazy";
            image.onerror = () => {
                image.remove();
                card.prepend(makeElement("div", "product-placeholder", "Image unavailable"));
            };
            card.appendChild(image);
        } else {
            card.appendChild(makeElement("div", "product-placeholder", "No image available"));
        }

        const body = makeElement("div", "card-body d-flex flex-column");
        body.appendChild(makeElement("p", "small text-secondary mb-1", product.brand || "ShopEase"));
        body.appendChild(makeElement("h3", "h6 fw-bold", product.name));
        body.appendChild(makeElement("p", "text-secondary small", product.category || ""));

        const priceArea = makeElement("div", "mt-auto");
        const price = Number(product.final_min_price);

        priceArea.appendChild(makeElement(
            "p",
            "price",
            Number.isFinite(price)
                ? `₹${price.toLocaleString("en-IN", {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                })}`
                : "Price unavailable"
        ));

        if (Number(product.discount_percent) > 0) {
            priceArea.appendChild(makeElement(
                "span",
                "badge text-bg-success mb-2",
                `${Math.round(Number(product.discount_percent))}% off`
            ));
        }

        if (product.in_stock === false) {
            priceArea.appendChild(makeElement("span", "badge text-bg-secondary mb-2", "Out of stock"));
        }

        if (product.average_rating !== null && product.average_rating !== undefined) {
            priceArea.appendChild(makeElement(
                "p",
                "small text-secondary",
                `★ ${Number(product.average_rating).toFixed(1)} (${Number(product.review_count || 0)} reviews)`
            ));
        }

        const link = makeElement("a", "btn btn-outline-primary w-100", "View Product");
        link.href = `/products/${encodeURIComponent(product.id)}/`;
        priceArea.appendChild(link);

        body.appendChild(priceArea);
        card.appendChild(body);
        column.appendChild(card);
        return column;
    }

    function getQueryParams() {
        const params = new URLSearchParams();
        const search = input.value.trim();

        if (search) params.set("search", search);
        if (categoryFilter.value) params.set("category", categoryFilter.value);
        if (brandFilter.value) params.set("brand", brandFilter.value);
        if (subcategoryFilter && subcategoryFilter.value) params.set("subcategory", subcategoryFilter.value);
        if (colorFilter && colorFilter.value.trim()) params.set("color", colorFilter.value.trim());
        if (sizeFilter && sizeFilter.value.trim()) params.set("size", sizeFilter.value.trim());
        if (ratingFilter && ratingFilter.value) params.set("min_rating", ratingFilter.value);
        if (stockFilterSelect && stockFilterSelect.value) params.set("in_stock", stockFilterSelect.value);
        if (minPrice.value.trim()) params.set("min_price", minPrice.value.trim());
        if (maxPrice.value.trim()) params.set("max_price", maxPrice.value.trim());
        if (stockFilter && stockFilter.checked) params.set("in_stock", "true");
        if (featuredFilter.checked) params.set("featured", "true");
        if (sortFilter.value) params.set("ordering", sortFilter.value);

        params.set("page", String(currentPage));
        return params;
    }

    async function loadProducts() {
        const thisRequest = ++requestNumber;
        hideMessage();
        grid.replaceChildren(makeElement("div", "col-12", "Loading products..."));
        pagination.replaceChildren();
        pageInfo.textContent = "";

        const minimum = minPrice.value.trim() ? Number(minPrice.value) : null;
        const maximum = maxPrice.value.trim() ? Number(maxPrice.value) : null;

        if (minimum !== null && (!Number.isFinite(minimum) || minimum < 0)) {
            grid.replaceChildren();
            count.textContent = "Invalid filter";
            showMessage("Enter a valid minimum price.");
            return;
        }

        if (maximum !== null && (!Number.isFinite(maximum) || maximum < 0)) {
            grid.replaceChildren();
            count.textContent = "Invalid filter";
            showMessage("Enter a valid maximum price.");
            return;
        }

        if (minimum !== null && maximum !== null && minimum > maximum) {
            grid.replaceChildren();
            count.textContent = "Invalid filter";
            showMessage("Minimum price cannot exceed maximum price.");
            return;
        }

        try {
            const params = getQueryParams();
            const data = await getJSON(`/api/products/?${params.toString()}`);

            if (thisRequest !== requestNumber) return;

            const products = Array.isArray(data.results) ? data.results : data;
            grid.replaceChildren();

            if (!Array.isArray(products) || products.length === 0) {
                count.textContent = "0 products found";
                showMessage("No products match your search and filters. Try changing your criteria.");
                return;
            }

            products.forEach((product) => grid.appendChild(renderProduct(product)));

            count.textContent = typeof data.count === "number"
                ? `${data.count} product${data.count === 1 ? "" : "s"} found`
                : `${products.length} products found`;

            renderPagination(data, products.length);
        } catch (error) {
            if (thisRequest !== requestNumber) return;
            grid.replaceChildren();
            count.textContent = "Products could not be loaded";
            showMessage(error.message || "Unable to load products. Please try again.");
        }
    }

    function renderPagination(data, pageSize) {
        pagination.replaceChildren();

        if (!data || typeof data.count !== "number" || !Array.isArray(data.results)) return;

        const totalPages = Math.ceil(data.count / 12);
        pageInfo.textContent = totalPages > 0 ? `Page ${currentPage} of ${totalPages}` : "";

        if (totalPages <= 1) return;

        function addPage(label, target, disabled, active) {
            const item = makeElement(
                "li",
                `page-item${disabled ? " disabled" : ""}${active ? " active" : ""}`
            );
            const button = makeElement("button", "page-link", label);
            button.type = "button";
            button.disabled = disabled;
            button.addEventListener("click", () => {
                currentPage = target;
                loadProducts();
                document.getElementById("products").scrollIntoView({ behavior: "smooth" });
            });
            item.appendChild(button);
            pagination.appendChild(item);
        }

        addPage("Previous", currentPage - 1, currentPage <= 1, false);

        const start = Math.max(1, currentPage - 2);
        const end = Math.min(totalPages, currentPage + 2);

        for (let number = start; number <= end; number++) {
            addPage(String(number), number, number === currentPage, number === currentPage);
        }

        addPage("Next", currentPage + 1, currentPage >= totalPages, false);
    }

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        currentPage = 1;
        loadProducts();
    });

    if (applyButton) {
        applyButton.addEventListener("click", (event) => {
            event.preventDefault();
            currentPage = 1;
            loadProducts();
        });
    }
    filterForm.addEventListener("submit", (event) => {
        event.preventDefault();
        currentPage = 1;
        loadProducts();
    });

    clearButton.addEventListener("click", () => {
        input.value = "";
        categoryFilter.value = "";
        brandFilter.value = "";
        minPrice.value = "";
        maxPrice.value = "";
        sortFilter.value = "-created_at";
        if (stockFilter) stockFilter.checked = false;
        featuredFilter.checked = false;
        currentPage = 1;
        loadProducts();
    });

    loadOptions().finally(loadProducts);
})();



