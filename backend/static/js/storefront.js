(() => {
    "use strict";

    const form = document.getElementById("searchForm");
    const input = document.getElementById("searchInput");
    const grid = document.getElementById("productGrid");
    const count = document.getElementById("resultCount");
    const message = document.getElementById("searchMessage");

    if (!form || !input || !grid) return;

    const cards = Array.from(grid.querySelectorAll(".product-item"));

    form.addEventListener("submit", (event) => {
        event.preventDefault();

        const query = input.value.trim().toLocaleLowerCase();
        let visible = 0;

        cards.forEach((card) => {
            const matches = card.textContent.toLocaleLowerCase().includes(query);
            card.classList.toggle("d-none", !matches);
            if (matches) visible += 1;
        });

        count.textContent = `${visible} product${visible === 1 ? "" : "s"}`;

        if (visible === 0) {
            message.textContent = "No matching products found in the products currently displayed.";
            message.classList.remove("d-none");
        } else {
            message.classList.add("d-none");
        }
    });
})();
